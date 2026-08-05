"""Canonical portfolio-risk authority for the V2.0 programme (section 12).

One risk decision path used by signal qualification, paper trading, live
trading, copy trading and strategy bots. Pure, decimal-safe and deterministic
so it can be unit-tested without a database or broker. Kill-switch state is
explicit and env-derived; every decision returns a typed ``RiskDecision``.
"""
from __future__ import annotations

import math
import os
import time
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable, Mapping


def _env_bool(name: str, default: bool = False) -> bool:
    return str(os.getenv(name, "1" if default else "0")).strip().lower() in {
        "1", "true", "yes", "on"
    }


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)) or default)
    except (TypeError, ValueError):
        return float(default)


def _decimal(value: Any, field_name: str) -> Decimal:
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError(f"non_finite_{field_name}") from None
    if not parsed.is_finite():
        raise ValueError(f"non_finite_{field_name}")
    return parsed


@dataclass(frozen=True, slots=True)
class RiskLimits:
    """Configuration limits; all percentages are expressed in decimal (0.02 = 2%)."""

    max_positions_per_symbol: int = 1
    max_simultaneous_theses: int = 20
    max_account_exposure_pct: Decimal = Decimal("0.20")
    max_symbol_exposure_pct: Decimal = Decimal("0.05")
    max_daily_loss_pct: Decimal = Decimal("0.05")
    max_consecutive_losses: int = 4
    max_drawdown_pct: Decimal = Decimal("0.15")
    max_spread_bps: Decimal = Decimal("50")
    max_slippage_bps: Decimal = Decimal("25")
    max_volatility_pct: Decimal = Decimal("0.30")

    def __post_init__(self) -> None:
        for attr in (
            "max_account_exposure_pct",
            "max_symbol_exposure_pct",
            "max_daily_loss_pct",
            "max_drawdown_pct",
            "max_spread_bps",
            "max_slippage_bps",
            "max_volatility_pct",
        ):
            value = getattr(self, attr)
            parsed = _decimal(value, attr)
            if parsed < 0:
                raise ValueError(f"{attr}_must_not_be_negative")
            object.__setattr__(self, attr, parsed)

    @classmethod
    def from_env(cls) -> "RiskLimits":
        return cls(
            max_positions_per_symbol=int(_env_float("RISK_MAX_POSITIONS_PER_SYMBOL", 1)),
            max_simultaneous_theses=int(_env_float("RISK_MAX_SIMULTANEOUS_THESES", 20)),
            max_account_exposure_pct=Decimal(str(_env_float("RISK_MAX_ACCOUNT_EXPOSURE_PCT", 0.20))),
            max_symbol_exposure_pct=Decimal(str(_env_float("RISK_MAX_SYMBOL_EXPOSURE_PCT", 0.05))),
            max_daily_loss_pct=Decimal(str(_env_float("RISK_MAX_DAILY_LOSS_PCT", 0.05))),
            max_consecutive_losses=int(_env_float("RISK_MAX_CONSECUTIVE_LOSSES", 4)),
            max_drawdown_pct=Decimal(str(_env_float("RISK_MAX_DRAWDOWN_PCT", 0.15))),
            max_spread_bps=Decimal(str(_env_float("RISK_MAX_SPREAD_BPS", 50))),
            max_slippage_bps=Decimal(str(_env_float("RISK_MAX_SLIPPAGE_BPS", 25))),
            max_volatility_pct=Decimal(str(_env_float("RISK_MAX_VOLATILITY_PCT", 0.30))),
        )


@dataclass(frozen=True, slots=True)
class PortfolioState:
    """Current portfolio snapshot used for admission decisions."""

    equity: Decimal
    daily_realized_pnl: Decimal = Decimal("0")
    daily_start_equity: Decimal | None = None
    positions_by_symbol: Mapping[str, int] = field(default_factory=dict)
    open_positions: int = 0
    notional_by_symbol: Mapping[str, Decimal] = field(default_factory=dict)
    total_notional: Decimal = Decimal("0")
    consecutive_losses: int = 0
    peak_equity: Decimal | None = None


@dataclass(frozen=True, slots=True)
class RiskDecision:
    approved: bool
    reason: str = "approved"
    checks: tuple[str, ...] = ()
    exposure_used: Decimal | None = None


@dataclass(frozen=True, slots=True)
class TradeCandidate:
    symbol: str
    direction: str
    notional: Any
    entry: Any
    stop: Any
    spread_bps: Any = Decimal("0")
    expected_slippage_bps: Any = Decimal("0")
    volatility_pct: Any = Decimal("0")
    position_mode_ok: bool = True
    margin_mode_ok: bool = True


def _bps(value: Any) -> Decimal:
    return _decimal(value, "bps")


class PortfolioRiskAuthority:
    """Deterministic portfolio admission, loss tracking and kill-switch gates.

    Thread-unsafe by design; one authority instance per portfolio/tenant.
    """

    def __init__(
        self,
        *,
        limits: RiskLimits | None = None,
        equity: Any = Decimal("0"),
        kill_switch_global: bool | None = None,
        now: float | None = None,
    ) -> None:
        self.limits = limits or RiskLimits.from_env()
        self.equity = _decimal(equity, "equity")
        self.daily_realized_pnl = Decimal("0")
        self.daily_start_equity = self.equity
        self.positions_by_symbol: dict[str, int] = {}
        self.open_positions = 0
        self.notional_by_symbol: dict[str, Decimal] = {}
        self.total_notional = Decimal("0")
        self.consecutive_losses = 0
        self.peak_equity = self.equity
        self._kill_switch = (
            _env_bool("GLOBAL_EXECUTION_KILL_SWITCH", True)
            if kill_switch_global is None
            else bool(kill_switch_global)
        )
        self._now = now
        self.decisions_recorded = 0
        self.breakers_tripped: list[str] = []

    @property
    def kill_switch_active(self) -> bool:
        return self._kill_switch

    def set_kill_switch(self, active: bool) -> None:
        self._kill_switch = bool(active)

    def _time(self) -> float:
        return self._now if self._now is not None else time.time()

    def evaluate(self, candidate: TradeCandidate) -> RiskDecision:
        """Admit or reject a trade candidate against the full risk stack."""
        self.decisions_recorded += 1
        checks: list[str] = []
        if self._kill_switch:
            return RiskDecision(False, "global_execution_kill_switch", ("kill_switch",))
        checks.append("kill_switch")

        if not candidate.position_mode_ok:
            return RiskDecision(False, "position_mode_not_supported", tuple(checks))
        if not candidate.margin_mode_ok:
            return RiskDecision(False, "margin_mode_not_supported", tuple(checks))
        checks.append("mode_support")

        if candidate.direction not in ("long", "short"):
            return RiskDecision(False, "invalid_direction", tuple(checks))

        if self.consecutive_losses >= self.limits.max_consecutive_losses:
            self.breakers_tripped.append("consecutive_loss_breaker")
            return RiskDecision(False, "consecutive_loss_breaker", tuple(checks))

        if self.daily_realized_pnl < -abs(self.limits.max_daily_loss_pct) * abs(self.equity):
            self.breakers_tripped.append("daily_loss_breaker")
            return RiskDecision(False, "daily_loss_breaker", tuple(checks))

        if self.daily_start_equity > 0 and self.peak_equity > 0:
            drawdown = (self.peak_equity - self.equity) / self.peak_equity
            if drawdown > self.limits.max_drawdown_pct:
                self.breakers_tripped.append("drawdown_breaker")
                return RiskDecision(False, "drawdown_breaker", tuple(checks))
        checks.append("loss_breakers")

        symbol_count = self.positions_by_symbol.get(candidate.symbol, 0)
        if symbol_count >= self.limits.max_positions_per_symbol:
            return RiskDecision(False, "max_positions_per_symbol", tuple(checks))
        if self.open_positions >= self.limits.max_simultaneous_theses:
            return RiskDecision(False, "max_simultaneous_theses", tuple(checks))

        notional = _decimal(candidate.notional, "notional")
        if notional <= 0:
            return RiskDecision(False, "invalid_notional", tuple(checks))
        symbol_notional = self.notional_by_symbol.get(candidate.symbol, Decimal("0")) + notional
        account_exposure = (self.total_notional + notional) / self.equity if self.equity > 0 else Decimal("0")
        symbol_exposure = symbol_notional / self.equity if self.equity > 0 else Decimal("0")
        if account_exposure > self.limits.max_account_exposure_pct:
            return RiskDecision(
                False, "account_exposure_limit", tuple(checks), account_exposure
            )
        if symbol_exposure > self.limits.max_symbol_exposure_pct:
            return RiskDecision(
                False, "symbol_exposure_limit", tuple(checks), account_exposure
            )
        checks.append("exposure")

        spread = _bps(candidate.spread_bps)
        slippage = _bps(candidate.expected_slippage_bps)
        volatility = _decimal(candidate.volatility_pct, "volatility")
        if spread > self.limits.max_spread_bps:
            return RiskDecision(False, "spread_breaker", tuple(checks), account_exposure)
        if slippage > self.limits.max_slippage_bps:
            return RiskDecision(False, "slippage_breaker", tuple(checks), account_exposure)
        if volatility > self.limits.max_volatility_pct:
            return RiskDecision(False, "abnormal_volatility_breaker", tuple(checks), account_exposure)
        checks.append("quality_breakers")

        return RiskDecision(True, "approved", tuple(checks), account_exposure)

    def reserve(self, candidate: TradeCandidate) -> RiskDecision:
        """Atomically reserve a position after approval."""
        decision = self.evaluate(candidate)
        if not decision.approved:
            return decision
        notional = _decimal(candidate.notional, "notional")
        self.positions_by_symbol[candidate.symbol] = self.positions_by_symbol.get(candidate.symbol, 0) + 1
        self.open_positions += 1
        self.notional_by_symbol[candidate.symbol] = (
            self.notional_by_symbol.get(candidate.symbol, Decimal("0")) + notional
        )
        self.total_notional += notional
        return decision

    def release(self, symbol: str, notional: Any) -> None:
        self.positions_by_symbol[symbol] = max(0, self.positions_by_symbol.get(symbol, 0) - 1)
        self.open_positions = max(0, self.open_positions - 1)
        amount = _decimal(notional, "notional")
        current = self.notional_by_symbol.get(symbol, Decimal("0"))
        self.notional_by_symbol[symbol] = max(Decimal("0"), current - amount)
        self.total_notional = max(Decimal("0"), self.total_notional - amount)

    def record_pnl(self, pnl: Any, *, realized: bool = True) -> None:
        amount = _decimal(pnl, "pnl")
        if not realized:
            return
        self.daily_realized_pnl += amount
        self.equity += amount
        if self.equity > self.peak_equity:
            self.peak_equity = self.equity
        if amount < 0:
            self.consecutive_losses += 1
        else:
            self.consecutive_losses = 0

    def reset_daily(self, *, equity: Any | None = None) -> None:
        if equity is not None:
            self.equity = _decimal(equity, "equity")
        self.daily_start_equity = self.equity
        self.daily_realized_pnl = Decimal("0")

    def snapshot(self) -> PortfolioState:
        return PortfolioState(
            equity=self.equity,
            daily_realized_pnl=self.daily_realized_pnl,
            daily_start_equity=self.daily_start_equity,
            positions_by_symbol=dict(self.positions_by_symbol),
            open_positions=self.open_positions,
            notional_by_symbol=dict(self.notional_by_symbol),
            total_notional=self.total_notional,
            consecutive_losses=self.consecutive_losses,
            peak_equity=self.peak_equity,
        )


__all__ = [
    "PortfolioRiskAuthority",
    "PortfolioState",
    "RiskDecision",
    "RiskLimits",
    "TradeCandidate",
]
