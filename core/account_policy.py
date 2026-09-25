"""Deterministic per-trading-account execution and prop-policy authority.

The policy layer is deliberately pure: it never calls a broker, database, LLM,
or market-data provider. Callers provide an immutable account/risk snapshot and
receive a fail-closed decision. Percentages are decimal fractions (0.01 = 1%).

This module is the boundary between global SignalRank intelligence and an
individual user's trading-account permissions. It supports multiple accounts
per canonical user without sharing mutable account state.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


ACCOUNT_MODES = frozenset({"PAPER", "DEMO", "LIVE_PERSONAL", "PROP"})
EXECUTION_PERMISSIONS = frozenset(
    {
        "READ_ONLY",
        "SIGNALS_ONLY",
        "PAPER_ONLY",
        "MANUAL",
        "ASSISTED_EXECUTION",
        "AUTO_EXECUTION",
    }
)

_LIVE_MODES = frozenset({"manual_confirmed", "auto", "live", "copy_trade"})


def _decimal(value: Any, *, field_name: str, default: str | None = None) -> Decimal:
    raw = default if value in (None, "") and default is not None else value
    try:
        result = Decimal(str(raw))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError(f"invalid_{field_name}") from None
    if not result.is_finite():
        raise ValueError(f"invalid_{field_name}")
    return result


def _tuple_upper(value: Any) -> tuple[str, ...]:
    if value in (None, ""):
        return ()
    if isinstance(value, str):
        items = [item for item in value.split(",")]
    elif isinstance(value, (list, tuple, set, frozenset)):
        items = list(value)
    else:
        raise ValueError("invalid_policy_list")
    return tuple(sorted({str(item).strip().upper() for item in items if str(item).strip()}))


@dataclass(frozen=True, slots=True)
class TradingAccountPolicy:
    """Versioned hard policy for one broker/paper account."""

    connection_id: str
    user_id: int
    policy_version: int = 1
    account_mode: str = "DEMO"
    execution_permission: str = "SIGNALS_ONLY"
    status: str = "configured"
    reset_timezone: str = "UTC"

    # Internal SignalRank hard ceilings.
    max_risk_per_trade_pct: Decimal = Decimal("0.005")
    max_daily_loss_pct: Decimal = Decimal("0.04")
    max_total_drawdown_pct: Decimal = Decimal("0.08")
    max_open_positions: int = 3
    max_leverage: Decimal = Decimal("1")

    # PROP accounts can sit inside the firm's hard boundary by this buffer.
    safety_buffer_pct: Decimal = Decimal("0")
    external_max_daily_loss_pct: Decimal | None = None
    external_max_total_drawdown_pct: Decimal | None = None

    allowed_instruments: tuple[str, ...] = ()
    allowed_asset_classes: tuple[str, ...] = ()
    news_trading_allowed: bool = True
    weekend_holding_allowed: bool = True

    prop_firm: str | None = None
    prop_phase: str | None = None
    prop_rules_version: str | None = None
    certified: bool = False
    certification_ref: str | None = None

    frozen: bool = False
    frozen_reason: str | None = None
    extra_rules: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        mode = str(self.account_mode or "").strip().upper()
        permission = str(self.execution_permission or "").strip().upper()
        status = str(self.status or "").strip().lower()
        if mode not in ACCOUNT_MODES:
            raise ValueError("invalid_account_mode")
        if permission not in EXECUTION_PERMISSIONS:
            raise ValueError("invalid_execution_permission")
        if type(self.user_id) is not int or self.user_id <= 0:
            raise ValueError("invalid_user_id")
        if not str(self.connection_id or "").strip():
            raise ValueError("invalid_connection_id")
        if int(self.policy_version) <= 0:
            raise ValueError("invalid_policy_version")
        if int(self.max_open_positions) < 0:
            raise ValueError("invalid_max_open_positions")

        for name in (
            "max_risk_per_trade_pct",
            "max_daily_loss_pct",
            "max_total_drawdown_pct",
            "max_leverage",
            "safety_buffer_pct",
        ):
            value = _decimal(getattr(self, name), field_name=name)
            if value < 0:
                raise ValueError(f"{name}_must_not_be_negative")
            object.__setattr__(self, name, value)

        for name in ("external_max_daily_loss_pct", "external_max_total_drawdown_pct"):
            value = getattr(self, name)
            if value is not None:
                parsed = _decimal(value, field_name=name)
                if parsed <= 0:
                    raise ValueError(f"{name}_must_be_positive")
                object.__setattr__(self, name, parsed)

        try:
            ZoneInfo(str(self.reset_timezone or "UTC"))
        except ZoneInfoNotFoundError:
            raise ValueError("invalid_reset_timezone") from None

        object.__setattr__(self, "account_mode", mode)
        object.__setattr__(self, "execution_permission", permission)
        object.__setattr__(self, "status", status)
        object.__setattr__(self, "allowed_instruments", _tuple_upper(self.allowed_instruments))
        object.__setattr__(self, "allowed_asset_classes", _tuple_upper(self.allowed_asset_classes))


@dataclass(frozen=True, slots=True)
class AccountRiskSnapshot:
    """Broker/account state used for one admission decision."""

    current_equity: Decimal
    day_start_equity: Decimal
    peak_equity: Decimal
    daily_realized_pnl: Decimal = Decimal("0")
    open_positions: int = 0
    proposed_risk_pct: Decimal = Decimal("0")
    proposed_leverage: Decimal = Decimal("0")
    symbol: str = ""
    asset_class: str = ""
    high_impact_news_window: bool = False
    weekend_hold_expected: bool = False
    account_is_demo: bool | None = None
    reconciliation_ready: bool = True
    # Real-money decisions require broker/reconciliation-derived daily and
    # peak-equity baselines; current equity alone cannot prove loss headroom.
    loss_baselines_verified: bool = False

    def __post_init__(self) -> None:
        for name in (
            "current_equity",
            "day_start_equity",
            "peak_equity",
            "daily_realized_pnl",
            "proposed_risk_pct",
            "proposed_leverage",
        ):
            object.__setattr__(
                self,
                name,
                _decimal(getattr(self, name), field_name=name),
            )
        if int(self.open_positions) < 0:
            raise ValueError("invalid_open_positions")


@dataclass(frozen=True, slots=True)
class AccountPolicyDecision:
    allowed: bool
    code: str
    reasons: tuple[str, ...]
    policy_version: int
    effective_daily_loss_limit: Decimal | None = None
    effective_drawdown_limit: Decimal | None = None


def _permission_allows(permission: str, execution_mode: str, account_mode: str) -> bool:
    permission = str(permission).strip().upper()
    mode = str(execution_mode or "").strip().lower()
    if account_mode == "PAPER":
        return False
    if mode not in _LIVE_MODES:
        return False
    if mode == "manual_confirmed":
        return permission in {"MANUAL", "ASSISTED_EXECUTION", "AUTO_EXECUTION"}
    if mode in {"auto", "live", "copy_trade"}:
        return permission == "AUTO_EXECUTION"
    return False


def _effective_limit(
    internal: Decimal,
    external: Decimal | None,
    buffer: Decimal,
) -> Decimal | None:
    if external is None:
        return internal
    external_buffered = external - buffer
    if external_buffered <= 0:
        return None
    return min(internal, external_buffered)


def evaluate_account_policy(
    policy: TradingAccountPolicy,
    snapshot: AccountRiskSnapshot,
    *,
    execution_mode: str,
) -> AccountPolicyDecision:
    """Evaluate one account deterministically and fail closed on uncertainty."""

    reasons: list[str] = []

    if policy.status not in {"active", "certified", "configured"}:
        reasons.append("account_policy_inactive")
    if policy.frozen:
        reasons.append("account_policy_frozen")
    if not snapshot.reconciliation_ready:
        reasons.append("account_reconciliation_unready")

    if not _permission_allows(
        policy.execution_permission,
        execution_mode,
        policy.account_mode,
    ):
        reasons.append("execution_permission_blocked")

    if policy.account_mode == "PAPER":
        reasons.append("paper_account_broker_execution_forbidden")
    elif policy.account_mode == "DEMO":
        if snapshot.account_is_demo is not True:
            reasons.append("demo_account_classification_mismatch")
    elif policy.account_mode in {"LIVE_PERSONAL", "PROP"}:
        if snapshot.account_is_demo is not False:
            reasons.append("live_account_classification_mismatch")
        if not snapshot.loss_baselines_verified:
            reasons.append("loss_baseline_unavailable")

    if policy.account_mode == "PROP":
        if not policy.certified or not str(policy.certification_ref or "").strip():
            reasons.append("prop_policy_not_certified")
        if not str(policy.prop_firm or "").strip():
            reasons.append("prop_firm_required")
        if not str(policy.prop_rules_version or "").strip():
            reasons.append("prop_rules_version_required")
        if policy.external_max_daily_loss_pct is None:
            reasons.append("prop_external_daily_loss_required")
        if policy.external_max_total_drawdown_pct is None:
            reasons.append("prop_external_drawdown_required")

    daily_limit = _effective_limit(
        policy.max_daily_loss_pct,
        policy.external_max_daily_loss_pct if policy.account_mode == "PROP" else None,
        policy.safety_buffer_pct if policy.account_mode == "PROP" else Decimal("0"),
    )
    drawdown_limit = _effective_limit(
        policy.max_total_drawdown_pct,
        policy.external_max_total_drawdown_pct if policy.account_mode == "PROP" else None,
        policy.safety_buffer_pct if policy.account_mode == "PROP" else Decimal("0"),
    )
    if daily_limit is None:
        reasons.append("invalid_daily_loss_buffer")
    if drawdown_limit is None:
        reasons.append("invalid_drawdown_buffer")

    if snapshot.current_equity <= 0 or snapshot.day_start_equity <= 0 or snapshot.peak_equity <= 0:
        reasons.append("account_equity_unavailable")
    else:
        equity_daily_loss = max(
            Decimal("0"),
            (snapshot.day_start_equity - snapshot.current_equity) / snapshot.day_start_equity,
        )
        realized_daily_loss = max(
            Decimal("0"),
            -snapshot.daily_realized_pnl / snapshot.day_start_equity,
        )
        daily_loss = max(equity_daily_loss, realized_daily_loss)
        total_drawdown = max(
            Decimal("0"),
            (snapshot.peak_equity - snapshot.current_equity) / snapshot.peak_equity,
        )
        if daily_limit is not None and daily_loss >= daily_limit:
            reasons.append("daily_loss_limit")
        if drawdown_limit is not None and total_drawdown >= drawdown_limit:
            reasons.append("total_drawdown_limit")

    if snapshot.proposed_risk_pct < 0 or snapshot.proposed_risk_pct > policy.max_risk_per_trade_pct:
        reasons.append("risk_per_trade_limit")
    if snapshot.proposed_leverage < 0 or snapshot.proposed_leverage > policy.max_leverage:
        reasons.append("leverage_limit")
    if snapshot.open_positions >= policy.max_open_positions:
        reasons.append("max_open_positions")

    symbol = str(snapshot.symbol or "").strip().upper()
    asset_class = str(snapshot.asset_class or "").strip().upper()
    if policy.allowed_instruments and (not symbol or symbol not in policy.allowed_instruments):
        reasons.append("instrument_not_allowed")
    if policy.allowed_asset_classes and (
        not asset_class or asset_class not in policy.allowed_asset_classes
    ):
        reasons.append("asset_class_not_allowed")
    if snapshot.high_impact_news_window and not policy.news_trading_allowed:
        reasons.append("news_trading_blocked")
    if snapshot.weekend_hold_expected and not policy.weekend_holding_allowed:
        reasons.append("weekend_holding_blocked")

    if reasons:
        return AccountPolicyDecision(
            False,
            "ACCOUNT_POLICY_BLOCKED",
            tuple(dict.fromkeys(reasons)),
            policy.policy_version,
            daily_limit,
            drawdown_limit,
        )
    return AccountPolicyDecision(
        True,
        "ACCOUNT_POLICY_ALLOWED",
        (),
        policy.policy_version,
        daily_limit,
        drawdown_limit,
    )


def policy_from_mapping(value: Mapping[str, Any]) -> TradingAccountPolicy:
    """Convert a persistence/API mapping to the canonical immutable policy."""

    return TradingAccountPolicy(
        connection_id=str(value.get("connection_id") or ""),
        user_id=int(value.get("user_id") or 0),
        policy_version=int(value.get("policy_version") or 1),
        account_mode=str(value.get("account_mode") or "DEMO"),
        execution_permission=str(value.get("execution_permission") or "SIGNALS_ONLY"),
        status=str(value.get("status") or "configured"),
        reset_timezone=str(value.get("reset_timezone") or "UTC"),
        max_risk_per_trade_pct=_decimal(
            value.get("max_risk_per_trade_pct"),
            field_name="max_risk_per_trade_pct",
            default="0.005",
        ),
        max_daily_loss_pct=_decimal(
            value.get("max_daily_loss_pct"),
            field_name="max_daily_loss_pct",
            default="0.04",
        ),
        max_total_drawdown_pct=_decimal(
            value.get("max_total_drawdown_pct"),
            field_name="max_total_drawdown_pct",
            default="0.08",
        ),
        max_open_positions=int(
            value.get("max_open_positions")
            if value.get("max_open_positions") is not None
            else 3
        ),
        max_leverage=_decimal(
            value.get("max_leverage"),
            field_name="max_leverage",
            default="1",
        ),
        safety_buffer_pct=_decimal(
            value.get("safety_buffer_pct"),
            field_name="safety_buffer_pct",
            default="0",
        ),
        external_max_daily_loss_pct=(
            _decimal(
                value.get("external_max_daily_loss_pct"),
                field_name="external_max_daily_loss_pct",
            )
            if value.get("external_max_daily_loss_pct") not in (None, "")
            else None
        ),
        external_max_total_drawdown_pct=(
            _decimal(
                value.get("external_max_total_drawdown_pct"),
                field_name="external_max_total_drawdown_pct",
            )
            if value.get("external_max_total_drawdown_pct") not in (None, "")
            else None
        ),
        allowed_instruments=_tuple_upper(value.get("allowed_instruments")),
        allowed_asset_classes=_tuple_upper(value.get("allowed_asset_classes")),
        news_trading_allowed=bool(value.get("news_trading_allowed", True)),
        weekend_holding_allowed=bool(value.get("weekend_holding_allowed", True)),
        prop_firm=(str(value.get("prop_firm")).strip() if value.get("prop_firm") else None),
        prop_phase=(str(value.get("prop_phase")).strip() if value.get("prop_phase") else None),
        prop_rules_version=(
            str(value.get("prop_rules_version")).strip()
            if value.get("prop_rules_version")
            else None
        ),
        certified=bool(value.get("certified", False)),
        certification_ref=(
            str(value.get("certification_ref")).strip()
            if value.get("certification_ref")
            else None
        ),
        frozen=bool(value.get("frozen", False)),
        frozen_reason=(
            str(value.get("frozen_reason")).strip()
            if value.get("frozen_reason")
            else None
        ),
        extra_rules=dict(value.get("extra_rules") or {}),
    )


__all__ = [
    "ACCOUNT_MODES",
    "EXECUTION_PERMISSIONS",
    "TradingAccountPolicy",
    "AccountRiskSnapshot",
    "AccountPolicyDecision",
    "evaluate_account_policy",
    "policy_from_mapping",
]
