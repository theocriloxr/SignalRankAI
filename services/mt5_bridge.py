"""Fail-closed native MetaTrader 5 bridge.

The Railway deployment uses MetaApi/remote broker adapters.  This module is a
local Windows-terminal adapter only and is disabled unless explicitly enabled.
It intentionally refuses to guess balances, symbol specifications, prices, or
lot sizes.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import math
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, ROUND_DOWN
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("MT5Bridge")

_mt5_connections: Dict[str, Any] = {}
_mt5_lock = asyncio.Lock()

_TRUE = {"1", "true", "yes", "on"}


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in _TRUE


def _running_on_railway() -> bool:
    return any(
        bool(os.getenv(name))
        for name in (
            "RAILWAY_ENVIRONMENT",
            "RAILWAY_ENVIRONMENT_ID",
            "RAILWAY_PROJECT_ID",
            "RAILWAY_SERVICE_ID",
        )
    )


@dataclass(slots=True)
class MT5Config:
    server: str = ""
    login: int = 0
    password: str = ""
    platform: str = "MetaTrader 5"
    timeout: int = 30_000
    max_retry: int = 3
    retry_delay: float = 2.0


@dataclass(slots=True)
class MT5Order:
    symbol: str
    volume: float
    order_type: str
    price: float
    stop_loss: float
    take_profit: float
    comment: str = ""
    magic: int = 234000

    def to_mt5_type(self) -> int:
        direction = self.order_type.strip().lower()
        if direction in {"long", "buy"}:
            return 0
        if direction in {"short", "sell"}:
            return 1
        raise ValueError("direction must be long/buy or short/sell")


@dataclass(slots=True)
class MT5Position:
    ticket: int
    symbol: str
    volume: float
    type: str
    entry_price: float
    current_price: float
    profit: float
    stop_loss: float
    take_profit: float
    comment: str
    open_time: datetime

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ticket": self.ticket,
            "symbol": self.symbol,
            "volume": self.volume,
            "type": self.type,
            "entry_price": self.entry_price,
            "current_price": self.current_price,
            "profit": self.profit,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "comment": self.comment,
            "open_time": self.open_time.isoformat() if self.open_time else None,
        }


class MT5Bridge:
    """Local native-terminal adapter; MetaApi is canonical on Railway."""

    def __init__(self) -> None:
        self._initialized = False
        self._mt5: Any = None
        self._config: Dict[str, MT5Config] = {}
        self._active_account: Optional[str] = None
        self._idempotency: set[str] = set()
        self._idempotency_lock = asyncio.Lock()

    @staticmethod
    def _native_enabled() -> bool:
        # Standard MetaTrader5 Python package needs a local Windows terminal.
        # Never pretend it works in the Railway Linux container.
        return _env_bool("NATIVE_MT5_BRIDGE_ENABLED", False) and not _running_on_railway()

    async def initialize(self) -> bool:
        if self._initialized:
            return True
        if not self._native_enabled():
            logger.info("[MT5] Native bridge disabled; use MetaApi/remote bridge")
            return False
        try:
            import MetaTrader5 as mt5  # type: ignore

            self._mt5 = mt5
            initialized = await asyncio.to_thread(mt5.initialize)
            if not initialized:
                logger.error("[MT5] Initialize failed: %s", mt5.last_error())
                return False
            self._initialized = True
            logger.info("[MT5] Native terminal initialized")
            return True
        except ImportError:
            logger.warning("[MT5] MetaTrader5 library not installed")
            return False
        except Exception:
            logger.exception("[MT5] Initialize error")
            return False

    async def connect(self, account_id: str, config: Optional[MT5Config] = None) -> bool:
        if not await self.initialize():
            return False
        cfg = config or self._load_config(account_id)
        if not cfg.server or cfg.login <= 0 or not cfg.password:
            logger.warning("[MT5] Incomplete config for account %s", account_id)
            return False
        self._config[account_id] = cfg
        try:
            logged_in = await asyncio.to_thread(
                self._mt5.login,
                login=int(cfg.login),
                password=cfg.password,
                server=cfg.server,
                timeout=int(cfg.timeout),
            )
            if not logged_in:
                logger.error("[MT5] Login failed: %s", self._mt5.last_error())
                return False
            account_info = await asyncio.to_thread(self._mt5.account_info)
            if account_info is None or int(getattr(account_info, "login", 0)) != int(cfg.login):
                logger.error("[MT5] Account identity could not be verified")
                return False
            self._active_account = account_id
            _mt5_connections[account_id] = int(cfg.login)
            logger.info("[MT5] Connected to configured account %s", cfg.login)
            return True
        except Exception:
            logger.exception("[MT5] Account connection failed")
            return False

    def _load_config(self, account_id: str) -> MT5Config:
        prefix = f"MT5_{account_id}_"
        try:
            login = int(os.getenv(f"{prefix}LOGIN", "0") or 0)
            timeout = int(os.getenv(f"{prefix}TIMEOUT_MS", "30000") or 30000)
        except ValueError:
            login, timeout = 0, 30000
        return MT5Config(
            server=os.getenv(f"{prefix}SERVER", ""),
            login=login,
            password=os.getenv(f"{prefix}PASSWORD", ""),
            platform=os.getenv(f"{prefix}PLATFORM", "MetaTrader 5"),
            timeout=max(1_000, timeout),
        )

    async def disconnect(self) -> None:
        if self._mt5 and self._initialized:
            await asyncio.to_thread(self._mt5.shutdown)
        self._initialized = False
        self._active_account = None
        _mt5_connections.clear()
        logger.info("[MT5] Disconnected")

    @staticmethod
    def _parse_first_target(signal: Dict[str, Any]) -> float:
        value = signal.get("take_profit")
        if value is None:
            value = signal.get("targets")
        if isinstance(value, dict):
            value = value.get("price") or value.get("tp") or value.get("target")
        if isinstance(value, (list, tuple)):
            value = value[0] if value else None
            if isinstance(value, dict):
                value = value.get("price") or value.get("tp") or value.get("target")
        try:
            result = float(value)
        except (TypeError, ValueError):
            return 0.0
        return result if math.isfinite(result) and result > 0 else 0.0

    @staticmethod
    def _validate_geometry(direction: str, entry: float, stop: float, target: float) -> bool:
        values = (entry, stop, target)
        if not all(math.isfinite(value) and value > 0 for value in values):
            return False
        if direction in {"long", "buy"}:
            return stop < entry < target
        if direction in {"short", "sell"}:
            return target < entry < stop
        return False

    @staticmethod
    def _normalise_direction(direction: Any) -> str:
        raw = str(direction or "").strip().lower()
        if raw in {"long", "buy"}:
            return "buy"
        if raw in {"short", "sell"}:
            return "sell"
        return ""

    @staticmethod
    def _round_volume_down(value: float, step: float) -> float:
        step_d = Decimal(str(step))
        return float(
            (Decimal(str(value)) / step_d).to_integral_value(rounding=ROUND_DOWN) * step_d
        )

    def _calculate_volume(self, signal: Dict[str, Any], *, symbol_info: Any, account_info: Any) -> float:
        """Return broker-compliant lot size, or zero when truth is incomplete."""
        try:
            min_volume = float(getattr(symbol_info, "volume_min"))
            max_volume = float(getattr(symbol_info, "volume_max"))
            step = float(getattr(symbol_info, "volume_step"))
            if not all(math.isfinite(v) and v > 0 for v in (min_volume, max_volume, step)):
                return 0.0

            explicit = signal.get("position_size")
            if explicit is not None:
                requested = float(explicit)
                if not math.isfinite(requested) or requested <= 0:
                    return 0.0
                rounded = self._round_volume_down(min(requested, max_volume), step)
                return rounded if min_volume <= rounded <= max_volume else 0.0

            risk_pct = float(signal.get("risk_pct") or 0)
            equity = float(getattr(account_info, "equity"))
            entry = float(signal.get("entry") or 0)
            stop = float(signal.get("stop_loss") or signal.get("stop") or 0)
            tick_size = float(
                getattr(symbol_info, "trade_tick_size", 0)
                or getattr(symbol_info, "point", 0)
            )
            tick_value = float(
                getattr(symbol_info, "trade_tick_value_loss", 0)
                or getattr(symbol_info, "trade_tick_value", 0)
            )
            max_risk = float(os.getenv("MAX_LIVE_RISK_PCT", "5") or 5)
            values = (risk_pct, equity, entry, stop, tick_size, tick_value, max_risk)
            if not all(math.isfinite(value) for value in values):
                return 0.0
            if risk_pct <= 0 or risk_pct > max_risk or equity <= 0 or tick_size <= 0 or tick_value <= 0:
                return 0.0
            stop_distance = abs(entry - stop)
            if stop_distance <= 0:
                return 0.0
            risk_per_lot = (stop_distance / tick_size) * tick_value
            if risk_per_lot <= 0 or not math.isfinite(risk_per_lot):
                return 0.0
            raw = min((equity * risk_pct / 100.0) / risk_per_lot, max_volume)
            rounded = self._round_volume_down(raw, step)
            return rounded if min_volume <= rounded <= max_volume else 0.0
        except (AttributeError, TypeError, ValueError, ArithmeticError):
            return 0.0

    async def _reserve_once(self, key: str) -> bool:
        async with self._idempotency_lock:
            if key in self._idempotency:
                return False
            self._idempotency.add(key)
            return True

    async def execute_signal(
        self,
        signal: Dict[str, Any],
        account_id: str = "default",
        *,
        execution_authorized: bool = False,
        idempotency_key: Optional[str] = None,
    ) -> Tuple[bool, str, Optional[int]]:
        if not execution_authorized or not str(idempotency_key or "").strip():
            return False, "ExecutionGate authorization is required", None
        if self._active_account != account_id and not await self.connect(account_id):
            return False, "MT5 account not connected", None
        direction = self._normalise_direction(signal.get("direction") or signal.get("side"))
        symbol = self._normalize_symbol(str(signal.get("asset") or signal.get("symbol") or ""))
        if not direction or not symbol:
            return False, "Invalid symbol or direction", None
        try:
            signal_entry = float(signal.get("entry") or 0)
            stop_loss = float(signal.get("stop_loss") or signal.get("stop") or 0)
        except (TypeError, ValueError):
            return False, "Entry and stop must be numeric", None
        take_profit = self._parse_first_target(signal)
        if not self._validate_geometry(direction, signal_entry, stop_loss, take_profit):
            return False, "Invalid entry/stop/target geometry", None

        dedup_key = hashlib.sha256(
            f"{account_id}:{idempotency_key}".encode("utf-8")
        ).hexdigest()
        if not await self._reserve_once(dedup_key):
            return False, "Duplicate execution request", None

        try:
            selected = await asyncio.to_thread(self._mt5.symbol_select, symbol, True)
            if selected is False:
                return False, f"Symbol {symbol} is not selectable", None
            symbol_info = await asyncio.to_thread(self._mt5.symbol_info, symbol)
            tick = await asyncio.to_thread(self._mt5.symbol_info_tick, symbol)
            account_info = await asyncio.to_thread(self._mt5.account_info)
            if symbol_info is None or tick is None or account_info is None:
                return False, "Fresh quote, symbol specification and account information are required", None
            if getattr(symbol_info, "trade_mode", 0) == getattr(self._mt5, "SYMBOL_TRADE_MODE_DISABLED", -1):
                return False, f"Trading disabled for {symbol}", None

            market_price = float(tick.ask if direction == "buy" else tick.bid)
            if not math.isfinite(market_price) or market_price <= 0:
                return False, "Fresh broker quote is invalid", None
            max_slippage_bps = float(os.getenv("NATIVE_MT5_MAX_SLIPPAGE_BPS", "25") or 25)
            slippage_bps = abs(market_price - signal_entry) / signal_entry * 10_000
            if not math.isfinite(slippage_bps) or slippage_bps > max_slippage_bps:
                return False, f"Quote drift {slippage_bps:.2f}bps exceeds limit", None

            volume = self._calculate_volume(signal, symbol_info=symbol_info, account_info=account_info)
            if volume <= 0:
                return False, "Broker-compliant position size could not be calculated", None

            order = MT5Order(
                symbol=symbol,
                volume=volume,
                order_type=direction,
                price=market_price,
                stop_loss=stop_loss,
                take_profit=take_profit,
                comment=f"SignalRank:{signal.get('signal_id', '')}"[:31],
            )
            request = {
                "action": self._mt5.TRADE_ACTION_DEAL,
                "symbol": order.symbol,
                "volume": order.volume,
                "type": order.to_mt5_type(),
                "price": order.price,
                "sl": order.stop_loss,
                "tp": order.take_profit,
                "deviation": max(0, int(os.getenv("NATIVE_MT5_DEVIATION_POINTS", "20") or 20)),
                "comment": order.comment,
                "magic": order.magic,
                "type_time": getattr(self._mt5, "ORDER_TIME_GTC", 0),
                "type_filling": getattr(self._mt5, "ORDER_FILLING_IOC", 1),
            }
            result = await asyncio.to_thread(self._mt5.order_send, request)
            if result is None:
                return False, f"Order failed: {self._mt5.last_error()}", None
            if result.retcode != self._mt5.TRADE_RETCODE_DONE:
                return False, f"Order rejected: {result.retcode}", None
            return True, "Order executed", int(result.order)
        except Exception as exc:
            logger.exception("[MT5] Execute error")
            return False, str(exc), None

    def _normalize_symbol(self, symbol: str) -> str:
        canonical = symbol.upper().replace("/", "").strip()
        aliases = {
            "BTCUSDT": "BTCUSDt",
            "ETHUSDT": "ETHUSDt",
            "XAUUSD": "GOLD",
            "XAGUSD": "SILVER",
        }
        configured = os.getenv(f"MT5_SYMBOL_{canonical}")
        return str(configured or aliases.get(canonical, canonical)).strip()

    async def get_positions(self, account_id: str = "default") -> List[MT5Position]:
        if self._active_account != account_id and not await self.connect(account_id):
            return []
        try:
            raw = await asyncio.to_thread(self._mt5.positions_get)
            result: List[MT5Position] = []
            for pos in raw or []:
                opened = datetime.fromtimestamp(float(pos.time), tz=timezone.utc)
                result.append(
                    MT5Position(
                        ticket=int(pos.ticket),
                        symbol=str(pos.symbol),
                        volume=float(pos.volume),
                        type="buy" if int(pos.type) == 0 else "sell",
                        entry_price=float(pos.price_open),
                        current_price=float(pos.price_current),
                        profit=float(pos.profit),
                        stop_loss=float(pos.sl),
                        take_profit=float(pos.tp),
                        comment=str(pos.comment or ""),
                        open_time=opened,
                    )
                )
            return result
        except Exception:
            logger.exception("[MT5] Get positions error")
            return []

    async def close_position(self, ticket: int, volume: Optional[float] = None) -> Tuple[bool, str]:
        if not self._initialized:
            return False, "MT5 not initialized"
        try:
            positions = await asyncio.to_thread(self._mt5.positions_get, ticket=int(ticket))
            if not positions:
                return False, "Position not found"
            pos = positions[0]
            close_volume = float(volume if volume is not None else pos.volume)
            info = await asyncio.to_thread(self._mt5.symbol_info, pos.symbol)
            tick = await asyncio.to_thread(self._mt5.symbol_info_tick, pos.symbol)
            if info is None or tick is None:
                return False, "Fresh symbol quote required"
            step = float(info.volume_step)
            rounded = self._round_volume_down(close_volume, step)
            if rounded < float(info.volume_min) or rounded > float(pos.volume):
                return False, "Invalid close volume"
            close_type = 1 if int(pos.type) == 0 else 0
            price = float(tick.bid if int(pos.type) == 0 else tick.ask)
            result = await asyncio.to_thread(
                self._mt5.order_send,
                {
                    "action": self._mt5.TRADE_ACTION_DEAL,
                    "symbol": pos.symbol,
                    "volume": rounded,
                    "type": close_type,
                    "position": int(ticket),
                    "price": price,
                    "comment": f"Close SignalRank:{ticket}"[:31],
                    "magic": 234000,
                },
            )
            if result is None or result.retcode != self._mt5.TRADE_RETCODE_DONE:
                return False, f"Close failed: {getattr(result, 'retcode', self._mt5.last_error())}"
            return True, "Position closed"
        except Exception as exc:
            logger.exception("[MT5] Close error")
            return False, str(exc)

    async def modify_position(
        self,
        ticket: int,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
    ) -> Tuple[bool, str]:
        if not self._initialized:
            return False, "MT5 not initialized"
        if stop_loss is None and take_profit is None:
            return False, "No modification supplied"
        try:
            result = await asyncio.to_thread(
                self._mt5.order_send,
                {
                    "action": self._mt5.TRADE_ACTION_SLTP,
                    "position": int(ticket),
                    "sl": float(stop_loss or 0),
                    "tp": float(take_profit or 0),
                    "magic": 234000,
                },
            )
            if result is None or result.retcode != self._mt5.TRADE_RETCODE_DONE:
                return False, f"Modify failed: {getattr(result, 'retcode', self._mt5.last_error())}"
            return True, "Position modified"
        except Exception as exc:
            logger.exception("[MT5] Modify error")
            return False, str(exc)

    async def get_account_info(self) -> Optional[Dict[str, Any]]:
        if not self._initialized:
            return None
        try:
            info = await asyncio.to_thread(self._mt5.account_info)
            if info is None:
                return None
            return {
                "login": int(info.login),
                "balance": float(info.balance),
                "equity": float(info.equity),
                "margin": float(info.margin),
                "free_margin": float(info.margin_free),
                "profit": float(info.profit),
                "currency": str(info.currency),
                "server": str(info.server),
            }
        except Exception:
            logger.exception("[MT5] Account info error")
            return None


class MT5AccountManager:
    def __init__(self) -> None:
        self._accounts: Dict[str, MT5Bridge] = {}

    async def add_account(self, user_id: int, account_id: str, config: MT5Config) -> bool:
        bridge = MT5Bridge()
        if not await bridge.connect(account_id, config):
            return False
        self._accounts[f"{user_id}:{account_id}"] = bridge
        return True

    async def get_bridge(self, user_id: int, account_id: str = "default") -> Optional[MT5Bridge]:
        return self._accounts.get(f"{user_id}:{account_id}")

    async def remove_account(self, user_id: int, account_id: str = "default") -> None:
        bridge = self._accounts.pop(f"{user_id}:{account_id}", None)
        if bridge:
            await bridge.disconnect()


mt5_bridge = MT5Bridge()
account_manager = MT5AccountManager()


async def execute_signal(
    signal: Dict[str, Any],
    account_id: str = "default",
    *,
    execution_authorized: bool = False,
    idempotency_key: Optional[str] = None,
) -> Tuple[bool, str, Optional[int]]:
    return await mt5_bridge.execute_signal(
        signal,
        account_id,
        execution_authorized=execution_authorized,
        idempotency_key=idempotency_key,
    )


async def get_positions(account_id: str = "default") -> List[MT5Position]:
    return await mt5_bridge.get_positions(account_id)
