"""
MT5 Signal Router - Signal to MT5 Execution Routing

This module provides:
- Routes signals from signal generator to MT5 for automated execution
- Handles tier-based execution (manual, auto, none)
- Returns trade sync back to paper ledger
- Multi-account support per user (VIP)
- Position sizing based on account equity and risk parameters

Usage:
    from services.mt5_signal_router import MT5SignalRouter
    
    router = MT5SignalRouter()
    result = await router.route_signal(signal, user_id, execution_mode="auto")
"""

import logging
import os
import hashlib
import math
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_DOWN
import asyncio
import json

logger = logging.getLogger("MT5SignalRouter")

# Execution modes
class ExecutionMode:
    MANUAL = "manual"   # User executes manually
    AUTO = "auto"       # Auto-execute via MT5
    COPY_TRADE = "copy_trade"
    NONE = "none"       # No execution, just signals


@dataclass
class ExecutionRequest:
    """Signal execution request."""
    signal_id: str
    user_id: int
    asset: str
    direction: str  # long/short
    entry: float
    stop_loss: float
    take_profit: List[float]
    volume: float
    execution_mode: str
    tier: str  # user's tier at time of execution
    created_at: datetime


@dataclass
class ExecutionResult:
    """Result of execution attempt."""
    success: bool
    message: str
    order_id: Optional[str] = None
    executed_at: Optional[datetime] = None
    error: Optional[str] = None


class MT5SignalRouter:
    """
    Routes signals to MT5 for automated execution.
    
    Features:
    - Tier-based execution control (manual/auto/none)
    - Position sizing based on account equity
    - Risk-based lot calculation
    - Paper ledger sync for non-executed trades
    - Multi-account support (VIP)
    """
    
    def __init__(self, *, execution_gate: Any | None = None):
        from execution.service import ExecutionGate

        self._execution_queue: asyncio.Queue = asyncio.Queue()
        self._processing = False
        self._execution_gate = execution_gate or ExecutionGate()

    @staticmethod
    def _utc_now_naive() -> datetime:
        return datetime.now(timezone.utc).replace(tzinfo=None)

    @staticmethod
    def _parse_take_profit(value: Any) -> list[float]:
        if value is None:
            return []
        if isinstance(value, str):
            raw = value.strip()
            if not raw:
                return []
            try:
                return MT5SignalRouter._parse_take_profit(json.loads(raw))
            except Exception:
                parts = [p.strip() for p in raw.split(",") if p.strip()]
                out = []
                for part in parts:
                    try:
                        out.append(float(part))
                    except Exception:
                        continue
                return out
        if isinstance(value, dict):
            candidate = value.get("price") or value.get("tp") or value.get("target") or value.get("value")
            try:
                return [float(candidate)] if candidate is not None else []
            except Exception:
                return []
        if isinstance(value, (list, tuple)):
            out: list[float] = []
            for item in value:
                out.extend(MT5SignalRouter._parse_take_profit(item))
            return out
        try:
            return [float(value)]
        except Exception:
            return []

    @staticmethod
    def _validate_signal(signal: Dict[str, Any]) -> tuple[bool, str]:
        asset = str(signal.get("asset") or signal.get("symbol") or "").upper().strip()
        direction = str(signal.get("direction") or signal.get("side") or "").lower().strip()
        try:
            entry = float(signal.get("entry") or 0)
            stop_loss = float(signal.get("stop_loss") or signal.get("stop") or 0)
        except Exception:
            return False, "entry and stop_loss must be numeric"
        tps = MT5SignalRouter._parse_take_profit(signal.get("take_profit") or signal.get("targets"))
        if not asset:
            return False, "asset is required"
        if direction not in {"long", "short", "buy", "sell"}:
            return False, "direction must be long/short"
        if entry <= 0:
            return False, "entry must be positive"
        if stop_loss <= 0:
            return False, "broker execution requires a hard stop_loss"
        if not tps or tps[0] <= 0:
            return False, "at least one take_profit is required"
        if direction in {"long", "buy"} and stop_loss >= entry:
            return False, "long stop_loss must be below entry"
        if direction in {"short", "sell"} and stop_loss <= entry:
            return False, "short stop_loss must be above entry"
        return True, ""

    @staticmethod
    def _reservation_key(idempotency_key: str) -> str:
        digest = hashlib.sha256(str(idempotency_key).encode("utf-8")).hexdigest()
        return f"broker_exec:{digest}"

    async def _reserve_execution_once(
        self,
        idempotency_key: str,
        *,
        user_id: int,
        signal_id: str,
    ) -> bool:
        """Atomically reserve a broker request in PostgreSQL.

        A cache get followed by cache set races under concurrent callbacks.
        ``runtime_state.key`` is a primary key, so this one-statement upsert is
        atomic across coroutines, workers, and restarts. Database uncertainty
        blocks execution.
        """
        if not str(idempotency_key or "").strip() or not str(signal_id or "").strip():
            return False
        try:
            ttl = max(
                300,
                int(os.getenv("BROKER_EXEC_IDEMPOTENCY_SECONDS", "86400") or 86400),
            )
        except (TypeError, ValueError):
            ttl = 86400
        expires_at = self._utc_now_naive() + timedelta(seconds=ttl)
        payload = json.dumps(
            {
                "status": "reserved",
                "user_id": int(user_id),
                "signal_id": str(signal_id),
                "idempotency_key": str(idempotency_key),
                "reserved_at": self._utc_now_naive().isoformat(),
            },
            separators=(",", ":"),
        )
        try:
            from db.session import get_session
            from sqlalchemy import text

            async with get_session() as session:
                result = await session.execute(
                    text(
                        """
                        INSERT INTO runtime_state(key, value, expires_at, updated_at)
                        VALUES (:key, CAST(:value AS JSONB), :expires_at, NOW())
                        ON CONFLICT (key) DO UPDATE
                        SET value = EXCLUDED.value,
                            expires_at = EXCLUDED.expires_at,
                            updated_at = NOW()
                        WHERE runtime_state.expires_at IS NOT NULL
                          AND runtime_state.expires_at <= NOW()
                        RETURNING key
                        """
                    ),
                    {
                        "key": self._reservation_key(idempotency_key),
                        "value": payload,
                        "expires_at": expires_at,
                    },
                )
                row = result.fetchone()
                await session.commit()
            return bool(row)
        except Exception:
            logger.warning(
                "[SignalRouter] durable execution reservation unavailable; blocking",
                exc_info=True,
            )
            return False

    async def _record_execution_reservation(
        self,
        idempotency_key: str,
        *,
        status: str,
        order_id: Optional[str] = None,
        error: Optional[str] = None,
    ) -> None:
        """Update reservation evidence without affecting the broker outcome."""
        try:
            from db.session import get_session
            from sqlalchemy import text

            payload = json.dumps(
                {
                    "status": str(status),
                    "order_id": str(order_id) if order_id else None,
                    "error": str(error)[:240] if error else None,
                    "updated_at": self._utc_now_naive().isoformat(),
                },
                separators=(",", ":"),
            )
            async with get_session() as session:
                await session.execute(
                    text(
                        """
                        UPDATE runtime_state
                        SET value = runtime_state.value || CAST(:value AS JSONB),
                            updated_at = NOW()
                        WHERE key = :key
                        """
                    ),
                    {
                        "key": self._reservation_key(idempotency_key),
                        "value": payload,
                    },
                )
                await session.commit()
        except Exception:
            logger.warning(
                "[SignalRouter] failed to update execution reservation evidence",
                exc_info=True,
            )

    @staticmethod
    def _resource_pressure_clear() -> bool:
        """Block new broker orders when the runtime reports critical pressure."""
        values = (
            os.getenv("RESOURCE_PRESSURE_LEVEL"),
            os.getenv("RESOURCE_GOVERNOR_STATE"),
            os.getenv("SIGNALRANK_RESOURCE_PRESSURE"),
        )
        blocked = {"critical", "blocked", "stop", "oom", "overloaded"}
        if any(str(value or "").strip().lower() in blocked for value in values):
            return False
        try:
            from core.resource_governor import get_resource_governor

            return bool(
                get_resource_governor().policy.real_execution_allowed
            )
        except Exception:
            logger.warning(
                "[SignalRouter] resource governor unavailable; blocking execution",
                exc_info=True,
            )
            return False

    async def _get_user_execution_policy(
        self,
        user_id: int,
        account_id: str,
    ) -> Dict[str, Any]:
        """Load current user consent/mode and validate encrypted credentials."""
        policy: Dict[str, Any] = {
            "found": False,
            "consent": False,
            "user_enabled": False,
            "credentials_encrypted": False,
        }
        try:
            from db.models import MT5Credentials, RuntimeState, User
            from db.session import get_session
            from services.security import decrypt_secret, is_encryption_available
            from sqlalchemy import select

            async with get_session() as session:
                result = await session.execute(
                    select(
                        User.accepted_terms,
                        User.execution_mode,
                        MT5Credentials.password_encrypted,
                        MT5Credentials.metaapi_account_id,
                    )
                    .join(MT5Credentials, MT5Credentials.user_id == User.id)
                    .where(User.telegram_user_id == int(user_id))
                    .limit(1)
                )
                row = result.fetchone()
                optin_result = await session.execute(
                    select(RuntimeState.key, RuntimeState.value)
                    .where(
                        RuntimeState.key.in_(
                            (
                                f"autoexec_user_optin:{int(user_id)}",
                                f"copyexec_user_optin:{int(user_id)}",
                            )
                        )
                    )
                )
                optins = {
                    str(item[0]): item[1]
                    for item in optin_result.all()
                    if item and len(item) >= 2
                }
            if not row:
                return policy
            encrypted = str(row[2] or "").strip()
            stored_account = str(row[3] or "").strip()
            mode = str(row[1] or "").strip().lower()
            consent_key = (
                f"copyexec_user_optin:{int(user_id)}"
                if mode == ExecutionMode.COPY_TRADE
                else f"autoexec_user_optin:{int(user_id)}"
            )
            optin_value = optins.get(consent_key)
            execution_optin = bool(
                isinstance(optin_value, dict) and optin_value.get("enabled") is True
            )
            credentials_valid = bool(
                encrypted
                and stored_account
                and stored_account == str(account_id).strip()
                and is_encryption_available()
                and decrypt_secret(encrypted)
            )
            policy.update(
                {
                    "found": True,
                    # Terms acceptance alone is not execution consent. AUTO
                    # additionally requires the current explicit opt-in record;
                    # COPY remains disabled until it has its own consent flow.
                    "consent": bool(
                        row[0]
                        and mode
                        in {ExecutionMode.AUTO, ExecutionMode.COPY_TRADE}
                        and execution_optin
                    ),
                    "user_enabled": mode in {
                        ExecutionMode.AUTO,
                        ExecutionMode.COPY_TRADE,
                        "live",
                    },
                    "credentials_encrypted": credentials_valid,
                    "mode": mode,
                }
            )
        except Exception:
            logger.warning(
                "[SignalRouter] user execution policy unavailable; blocking",
                exc_info=True,
            )
        return policy

    async def _has_execution_evidence(self, user_id: int, signal_id: str) -> bool:
        """Require a proven delivery to this user before broker execution."""
        if not str(signal_id or "").strip():
            return False
        try:
            from db.session import get_session
            from sqlalchemy import text

            async with get_session() as session:
                result = await session.execute(
                    text(
                        """
                        SELECT 1
                        FROM signal_deliveries sd
                        JOIN users u ON u.id = sd.user_id
                        WHERE u.telegram_user_id = :tid
                          AND sd.signal_id = :signal_id
                          AND sd.sent_ok IS TRUE
                          AND COALESCE(sd.delivery_state, 'delivered')
                              IN ('delivered', 'confirmed', 'sent')
                        LIMIT 1
                        """
                    ),
                    {"tid": int(user_id), "signal_id": str(signal_id)},
                )
                return result.fetchone() is not None
        except Exception:
            logger.warning(
                "[SignalRouter] execution evidence unavailable; blocking",
                exc_info=True,
            )
            return False
        
    async def initialize(self) -> bool:
        """Initialize router and start processing loop."""
        if self._processing:
            return True
        self._processing = True
        asyncio.create_task(self._process_execution_loop())
        logger.info("[SignalRouter] Initialized")
        return True
    
    async def route_signal(
        self,
        signal: Dict[str, Any],
        user_id: int,
        execution_mode: str = "manual",
    ) -> ExecutionResult:
        """
        Route signal to appropriate execution handler.
        
        Args:
            signal: Signal dict with asset, direction, entry, stop_loss, take_profit
            user_id: Telegram user ID
            execution_mode: manual, auto, or none
            
        Returns:
            ExecutionResult with success status and details
        """
        try:
            valid, reason = self._validate_signal(signal or {})
            if not valid:
                return ExecutionResult(success=False, message=reason, error=reason)

            execution_mode = str(execution_mode or ExecutionMode.NONE).strip().lower()
            if execution_mode == "copy":
                execution_mode = ExecutionMode.COPY_TRADE
            if execution_mode == ExecutionMode.NONE:
                return ExecutionResult(
                    success=False,
                    message="Execution disabled - signals only",
                )
            if execution_mode == ExecutionMode.MANUAL:
                return ExecutionResult(
                    success=True,
                    message=(
                        f"Execute manually: {signal.get('asset')} "
                        f"{str(signal.get('direction') or '').upper()} "
                        f"@ {signal.get('entry')} SL {signal.get('stop_loss')}"
                    ),
                )
            if execution_mode not in {
                ExecutionMode.AUTO,
                ExecutionMode.COPY_TRADE,
            }:
                return ExecutionResult(
                    success=False,
                    message="Unsupported or non-live execution mode",
                    error="execution_mode_not_live",
                )

            signal_id = str(
                signal.get("signal_id") or signal.get("id") or ""
            ).strip()
            tier = self._get_user_tier(user_id)
            mt5_account_id = await self._get_user_mt5_account(user_id)
            if not mt5_account_id:
                return ExecutionResult(
                    success=False,
                    message="No MT5 linked - use /mt5_link to connect your account",
                    error="broker_account_not_ready",
                )

            from core.redis_state import state
            from execution.service import ExecutionRequest as GateRequest
            from services.market_intelligence import evaluate_market
            from services.mt5_client import (
                get_account_info,
                get_live_quote,
                get_reconciliation_snapshot,
                get_symbol_specification,
            )

            asset = str(signal.get("asset") or signal.get("symbol") or "").upper()
            account_info, symbol_spec, quote, policy, evidence = await asyncio.gather(
                get_account_info(mt5_account_id),
                get_symbol_specification(mt5_account_id, asset),
                get_live_quote(mt5_account_id, asset),
                self._get_user_execution_policy(user_id, mt5_account_id),
                self._has_execution_evidence(user_id, signal_id),
            )
            reconciliation = await get_reconciliation_snapshot(
                mt5_account_id,
                account_info=account_info,
            )
            try:
                kill_state = await state.get_killswitch()
                kill_switch = bool(getattr(kill_state, "enabled", True))
            except Exception:
                # Inability to establish kill-switch clearance is itself a
                # block; never infer "clear" from an unavailable backend.
                kill_switch = True

            volume = await self._calculate_position_size(
                user_id=user_id,
                entry=signal.get("entry", 0),
                stop_loss=signal.get("stop_loss", 0),
                account_id=mt5_account_id,
                tier=tier,
                account_info=account_info,
                symbol_spec=symbol_spec,
                symbol=asset,
            )

            market = evaluate_market(asset, signal=signal)
            requested_mode = str(policy.get("mode") or "").strip().lower()
            if execution_mode == ExecutionMode.COPY_TRADE:
                user_enabled = requested_mode == ExecutionMode.COPY_TRADE
            else:
                user_enabled = requested_mode in {ExecutionMode.AUTO, "live"}
            account_ready = bool(
                isinstance(account_info, dict)
                and account_info.get("connected") is True
                and isinstance(account_info.get("equity"), (int, float))
                and float(account_info["equity"]) > 0
                and isinstance(account_info.get("free_margin"), (int, float))
                and float(account_info["free_margin"]) > 0
            )
            account_is_demo = (
                account_info.get("is_demo")
                if isinstance(account_info, dict)
                and isinstance(account_info.get("is_demo"), bool)
                else None
            )
            quote_trusted = bool(
                isinstance(quote, dict)
                and quote.get("provider") == "metaapi"
                and quote.get("trusted") is True
            )
            quote_age = quote.get("age_seconds") if isinstance(quote, dict) else None
            max_quote_age = (
                quote.get("max_age_seconds", 15.0)
                if isinstance(quote, dict)
                else 15.0
            )
            symbol_ready = bool(
                isinstance(symbol_spec, dict)
                and symbol_spec.get("trade_allowed") is True
            )
            risk_allowed = bool(volume > 0 and symbol_ready and account_ready)

            gate_request = GateRequest(
                user_id=int(user_id),
                signal_id=signal_id,
                signal=signal,
                account_id=mt5_account_id,
                tier=tier,
                mode=execution_mode,
                user_enabled=bool(policy.get("found") and user_enabled),
                consent=bool(policy.get("consent")),
                account_ready=account_ready,
                account_is_demo=account_is_demo,
                credentials_encrypted=bool(policy.get("credentials_encrypted")),
                quote_trusted=quote_trusted,
                quote_age_seconds=quote_age,
                max_quote_age_seconds=max_quote_age,
                market_open=bool(market.market_open and market.trading_allowed),
                risk_allowed=risk_allowed,
                evidence_allowed=bool(evidence),
                broker_healthy=bool(account_ready and quote_trusted and symbol_ready),
                resources_available=self._resource_pressure_clear(),
                reconciliation_ready=bool(reconciliation.get("ready")),
                kill_switch=kill_switch,
            )
            idempotency_key = gate_request.key()

            async def _broker_submit(_request: GateRequest) -> Dict[str, Any]:
                reserved = await self._reserve_execution_once(
                    idempotency_key,
                    user_id=int(user_id),
                    signal_id=signal_id,
                )
                if not reserved:
                    return {
                        "success": False,
                        "status": "DUPLICATE",
                        "error": "duplicate_or_unavailable_execution_reservation",
                    }
                routed = await self._execute_via_mt5(
                    signal=signal,
                    user_id=user_id,
                    volume=volume,
                    account_id=mt5_account_id,
                    execution_authorized=True,
                    idempotency_key=idempotency_key,
                )
                await self._record_execution_reservation(
                    idempotency_key,
                    status="submitted" if routed.success else "rejected",
                    order_id=routed.order_id,
                    error=routed.error,
                )
                return {
                    "success": routed.success,
                    "order_id": routed.order_id,
                    "error": routed.error,
                    "status": "SUBMITTED" if routed.success else "REJECTED",
                }

            gated = await self._execution_gate.execute(gate_request, _broker_submit)
            if gated.accepted and gated.status == "SUBMITTED":
                return ExecutionResult(
                    success=True,
                    message=f"Executed: {asset} {signal.get('direction')}",
                    order_id=gated.order_id,
                    executed_at=self._utc_now_naive(),
                )
            if gated.status == "SUBMITTING":
                return ExecutionResult(
                    success=False,
                    message="Broker execution is already in progress",
                    error="execution_in_progress",
                )
            reasons = ", ".join(gated.decision.reasons)
            error = gated.error or (
                reasons if gated.status == "BLOCKED" else gated.status.lower()
            )
            return ExecutionResult(
                success=False,
                message=f"Execution {gated.status.lower()}: {error}",
                error=error,
            )

        except Exception as e:
            logger.error(f"[SignalRouter] Route error: {e}")
            return ExecutionResult(
                success=False,
                message=f"Error: {str(e)}",
                error=str(e),
            )
    
    async def _execute_via_mt5(
        self,
        signal: Dict[str, Any],
        user_id: int,
        volume: float,
        account_id: str,
        *,
        execution_authorized: bool = False,
        idempotency_key: Optional[str] = None,
    ) -> ExecutionResult:
        """Execute signal via MT5/MetaApi."""
        if not execution_authorized or not str(idempotency_key or "").strip():
            return ExecutionResult(
                success=False,
                message="ExecutionGate authorization is required",
                error="execution_gate_required",
            )
        try:
            from services.mt5_client import execute_trade
            
            asset = signal.get("asset", "")
            direction = signal.get("direction", "long")
            entry = signal.get("entry", 0)
            stop_loss = signal.get("stop_loss", 0)
            take_profit = signal.get("take_profit")
            
            tp_list = self._parse_take_profit(take_profit)
            
            # Use first TP for now
            tp_price = float(tp_list[0]) if tp_list else 0
            
            result = await execute_trade(
                account_id=account_id,
                symbol=asset,
                direction=direction,
                volume=volume,
                stop_loss=stop_loss,
                take_profit=tp_price,
                signal_entry=entry,
                comment=f"SignalRank:{signal.get('signal_id', '')}",
                execution_authorized=True,
                idempotency_key=idempotency_key,
            )
            
            if result.get("success"):
                # Sync to paper ledger
                await self._sync_to_paper_ledger(
                    signal=signal,
                    user_id=user_id,
                    order_id=result.get("order_id"),
                    volume=volume,
                )
                
                return ExecutionResult(
                    success=True,
                    message=f"Executed: {asset} {direction}",
                    order_id=result.get("order_id"),
                    executed_at=self._utc_now_naive(),
                )
            else:
                return ExecutionResult(
                    success=False,
                    message=f"Failed: {result.get('error', 'Unknown error')}",
                    error=result.get("error"),
                )
                
        except Exception as e:
            logger.error(f"[SignalRouter] MT5 execution error: {e}")
            return ExecutionResult(
                success=False,
                message=f"Execution error: {str(e)}",
                error=str(e),
            )
    
    async def _calculate_position_size(
        self,
        user_id: int,
        entry: float,
        stop_loss: float,
        account_id: str,
        tier: str,
        account_info: Optional[Dict[str, Any]] = None,
        symbol_spec: Optional[Dict[str, Any]] = None,
        symbol: str = "",
    ) -> float:
        """Calculate broker-compliant size or return zero on missing data.

        Tick value is assumed to be reported by MetaApi in account currency.
        The result is always rounded *down* to the broker's volume step. It is
        never raised to the minimum lot and never replaced by a fallback lot.
        """
        try:
            from services.mt5_client import (
                get_account_info,
                get_symbol_specification,
            )

            info = (
                account_info
                if isinstance(account_info, dict)
                else await get_account_info(account_id)
            )
            spec = (
                symbol_spec
                if isinstance(symbol_spec, dict)
                else await get_symbol_specification(
                    account_id,
                    str(symbol or "").strip().upper(),
                )
            )
            # Callers that do not already have a specification must provide a
            # symbol through the specification object; guessing is unsafe.
            if not isinstance(info, dict) or not isinstance(spec, dict):
                return 0.0
            if spec.get("trade_allowed") is not True:
                return 0.0

            equity = float(info.get("equity"))
            free_margin = float(info.get("free_margin"))
            entry_f = float(entry)
            stop_f = float(stop_loss)
            tick_size = float(spec.get("tick_size"))
            tick_value = float(spec.get("tick_value"))
            contract_size = float(spec.get("contract_size"))
            min_volume = float(spec.get("min_volume"))
            max_volume = float(spec.get("max_volume"))
            volume_step = float(spec.get("volume_step"))
            values = (
                equity,
                free_margin,
                entry_f,
                stop_f,
                tick_size,
                tick_value,
                contract_size,
                min_volume,
                max_volume,
                volume_step,
            )
            if not all(math.isfinite(value) for value in values):
                return 0.0
            if (
                equity <= 0
                or free_margin <= 0
                or entry_f <= 0
                or stop_f <= 0
                or tick_size <= 0
                or tick_value <= 0
                or contract_size <= 0
                or min_volume <= 0
                or max_volume < min_volume
                or volume_step <= 0
            ):
                return 0.0

            risk_pct = await self._get_user_risk_pct(user_id)
            if risk_pct is None or not math.isfinite(risk_pct) or risk_pct <= 0:
                return 0.0
            try:
                max_risk_pct = float(os.getenv("MAX_LIVE_RISK_PCT", "5"))
            except (TypeError, ValueError):
                max_risk_pct = 5.0
            if risk_pct > max(0.0, max_risk_pct):
                return 0.0

            risk_amount = equity * (risk_pct / 100.0)
            if risk_amount <= 0 or risk_amount > free_margin:
                return 0.0
            sl_distance = abs(entry_f - stop_f)
            if sl_distance <= 0:
                return 0.0
            risk_per_lot = (sl_distance / tick_size) * tick_value
            if not math.isfinite(risk_per_lot) or risk_per_lot <= 0:
                return 0.0
            raw_volume = min(risk_amount / risk_per_lot, max_volume)
            step = Decimal(str(volume_step))
            rounded = (
                (Decimal(str(raw_volume)) / step)
                .to_integral_value(rounding=ROUND_DOWN)
                * step
            )
            volume = float(rounded)
            if not math.isfinite(volume) or volume < min_volume:
                return 0.0
            return min(volume, max_volume)
        except Exception as e:
            logger.error(f"[SignalRouter] Volume calculation error: {e}")
            return 0.0
    
    async def _sync_to_paper_ledger(
        self,
        signal: Dict[str, Any],
        user_id: int,
        order_id: Optional[str],
        volume: float,
    ) -> None:
        """Sync executed trade to paper ledger for tracking."""
        try:
            from core.paper_ledger import sync_execution
            
            await sync_execution(
                signal_id=signal.get("signal_id", ""),
                user_id=user_id,
                order_id=order_id or "",
                asset=signal.get("asset", ""),
                direction=signal.get("direction", "long"),
                entry=signal.get("entry", 0),
                stop_loss=signal.get("stop_loss", 0),
                take_profit=signal.get("take_profit", ""),
                volume=volume,
                status="executed",
            )
        except Exception as e:
            logger.error(f"[SignalRouter] Paper ledger sync error: {e}")
    
    async def _get_user_mt5_account(self, user_id: int) -> Optional[str]:
        """Get user's MT5 MetaApi account ID."""
        try:
            from services.mt5_client import get_user_mt5_account_id
            return await get_user_mt5_account_id(user_id)
        except Exception:
            return None
    
    def _get_user_tier(self, user_id: int) -> str:
        """Get user's current tier."""
        try:
            from signalrank_telegram.access import resolve_user_tier
            tier = resolve_user_tier(user_id)
            return str(tier).upper()
        except Exception:
            return "FREE"
    
    async def _get_user_risk_pct(self, user_id: int) -> Optional[float]:
        """Load the user's configured risk percentage from PostgreSQL."""
        try:
            from db.session import get_session
            from db.models import User
            from sqlalchemy import select

            async with get_session() as session:
                result = await session.execute(
                    select(User.max_risk_percentage)
                    .where(User.telegram_user_id == int(user_id))
                    .limit(1)
                )
                row = result.fetchone()
            if not row or row[0] is None:
                return None
            value = float(row[0])
            return value if math.isfinite(value) and value > 0 else None
        except Exception:
            logger.warning(
                "[SignalRouter] risk configuration unavailable; blocking",
                exc_info=True,
            )
            return None
    
    async def _process_execution_loop(self) -> None:
        """Background loop for processing execution queue."""
        while self._processing:
            try:
                request = await self._execution_queue.get()
                # Process in background
                asyncio.create_task(self._process_request(request))
            except Exception as e:
                logger.error(f"[SignalRouter] Loop error: {e}")
    
    async def _process_request(self, request: ExecutionRequest) -> None:
        """Process a single execution request."""
        # Implementation would handle retry logic, etc.
        pass
    
    async def shutdown(self) -> None:
        """Shutdown router."""
        self._processing = False
        logger.info("[SignalRouter] Shutdown complete")


# Singleton instance
router = MT5SignalRouter()


# Convenience functions
async def route_signal_to_mt5(
    signal: Dict[str, Any],
    user_id: int,
    execution_mode: str = "manual",
) -> ExecutionResult:
    """Route signal to MT5 for execution."""
    return await router.route_signal(signal, user_id, execution_mode)


async def get_user_execution_mode(user_id: int) -> str:
    """Get user's current execution mode."""
    try:
        from db.session import get_session
        from db.models import User
        from sqlalchemy import select
        
        async with get_session() as session:
            result = await session.execute(
                select(User.execution_mode)
                .where(User.telegram_user_id == user_id)
            )
            row = result.fetchone()
            return row[0] if row else "manual"
    except Exception:
        return "manual"


async def set_user_execution_mode(user_id: int, mode: str) -> bool:
    """Set user's execution mode."""
    try:
        from db.session import get_session
        from db.models import User
        from sqlalchemy import update
        
        async with get_session() as session:
            await session.execute(
                update(User)
                .where(User.telegram_user_id == user_id)
                .values(execution_mode=mode)
            )
            await session.commit()
        return True
    except Exception as e:
        logger.error(f"[SignalRouter] Set mode error: {e}")
        return False


if __name__ == "__main__":
    # Test
    import asyncio
    
    async def test():
        r = MT5SignalRouter()
        await r.initialize()
        print("Router initialized")
        await r.shutdown()
    
    asyncio.run(test())
