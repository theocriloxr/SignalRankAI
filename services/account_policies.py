"""Canonical multi-account policy, reconciliation and decision-provenance service.

Every public function is scoped by canonical users.id plus connection_id.
The module never accepts Telegram IDs as ownership identifiers. PROP policy
certification is deliberately separate from user configuration.
"""
from __future__ import annotations

import os
from dataclasses import asdict
from datetime import datetime
from decimal import Decimal
from typing import Any, Mapping
from uuid import uuid4

from sqlalchemy import select

from core.account_policy import (
    AccountPolicyDecision,
    AccountRiskSnapshot,
    TradingAccountPolicy,
    evaluate_account_policy,
    policy_from_mapping,
)
from db.models import (
    BrokerConnection,
    BrokerExecutionDecision,
    BrokerReconciliationState,
    TradingAccountPolicyRecord,
)
from db.session import get_session
from utils.timeutils import now_utc_naive


_RECONCILIATION_HEALTHY = {"HEALTHY"}
_RECONCILIATION_BLOCKING = {
    "UNKNOWN",
    "RECONCILING",
    "DEGRADED",
    "FROZEN",
    "DISCONNECTED",
    "AUTH_EXPIRED",
}


def _iso(value: Any) -> str | None:
    return value.isoformat() if isinstance(value, datetime) else None


def public_account_policy(row: TradingAccountPolicyRecord) -> dict[str, Any]:
    return {
        "policy_id": row.policy_id,
        "connection_id": row.connection_id,
        "user_id": row.user_id,
        "policy_version": row.policy_version,
        "account_mode": row.account_mode,
        "execution_permission": row.execution_permission,
        "status": row.status,
        "currency": row.currency,
        "reset_timezone": row.reset_timezone,
        "max_risk_per_trade_pct": str(row.max_risk_per_trade_pct),
        "max_daily_loss_pct": str(row.max_daily_loss_pct),
        "max_weekly_loss_pct": str(row.max_weekly_loss_pct),
        "max_total_drawdown_pct": str(row.max_total_drawdown_pct),
        "max_open_positions": row.max_open_positions,
        "max_leverage": str(row.max_leverage),
        "max_spread_bps": str(row.max_spread_bps),
        "max_slippage_bps": str(row.max_slippage_bps),
        "min_confidence": str(row.min_confidence),
        "min_expected_rr": str(row.min_expected_rr),
        "safety_buffer_pct": str(row.safety_buffer_pct),
        "external_max_daily_loss_pct": (
            str(row.external_max_daily_loss_pct)
            if row.external_max_daily_loss_pct is not None else None
        ),
        "external_max_weekly_loss_pct": (
            str(row.external_max_weekly_loss_pct)
            if row.external_max_weekly_loss_pct is not None else None
        ),
        "external_max_total_drawdown_pct": (
            str(row.external_max_total_drawdown_pct)
            if row.external_max_total_drawdown_pct is not None else None
        ),
        "allowed_instruments": list(row.allowed_instruments or []),
        "allowed_asset_classes": list(row.allowed_asset_classes or []),
        "allowed_strategies": list(row.allowed_strategies or []),
        "trading_windows": list(row.trading_windows or []),
        "news_trading_allowed": bool(row.news_trading_allowed),
        "weekend_holding_allowed": bool(row.weekend_holding_allowed),
        "prop_firm": row.prop_firm,
        "prop_phase": row.prop_phase,
        "prop_rules_version": row.prop_rules_version,
        "external_rules": dict(row.external_rules or {}),
        "certified": row.certified_at is not None,
        "certified_at": _iso(row.certified_at),
        "certification_ref": row.certification_ref,
        "frozen": row.frozen_at is not None,
        "frozen_at": _iso(row.frozen_at),
        "frozen_reason": row.frozen_reason,
        "created_at": _iso(row.created_at),
        "updated_at": _iso(row.updated_at),
    }


def _domain_policy(row: TradingAccountPolicyRecord) -> TradingAccountPolicy:
    return policy_from_mapping({
        **public_account_policy(row),
        "certified": row.certified_at is not None,
        "extra_rules": dict(row.external_rules or {}),
    })


async def _owned_connection(
    session: Any,
    *,
    user_id: int,
    connection_id: str,
    lock: bool = False,
) -> BrokerConnection:
    query = select(BrokerConnection).where(
        BrokerConnection.user_id == int(user_id),
        BrokerConnection.connection_id == str(connection_id),
    )
    if lock:
        query = query.with_for_update()
    row = (await session.execute(query.limit(1))).scalar_one_or_none()
    if row is None:
        raise LookupError("broker_connection_not_found")
    return row


async def get_account_policy(user_id: int, connection_id: str) -> dict[str, Any]:
    async with get_session(label="account_policy.get", timeout_seconds=6.0) as session:
        await _owned_connection(session, user_id=int(user_id), connection_id=connection_id)
        row = (
            await session.execute(
                select(TradingAccountPolicyRecord).where(
                    TradingAccountPolicyRecord.user_id == int(user_id),
                    TradingAccountPolicyRecord.connection_id == str(connection_id),
                ).limit(1)
            )
        ).scalar_one_or_none()
        await session.rollback()
    if row is None:
        raise LookupError("account_policy_not_found")
    return public_account_policy(row)


async def configure_account_policy(
    user_id: int,
    connection_id: str,
    *,
    account_mode: str,
    execution_permission: str,
    reset_timezone: str = "UTC",
    currency: str = "USD",
    max_risk_per_trade_pct: Decimal | str = Decimal("0.005"),
    max_daily_loss_pct: Decimal | str = Decimal("0.04"),
    max_weekly_loss_pct: Decimal | str = Decimal("0.08"),
    max_total_drawdown_pct: Decimal | str = Decimal("0.08"),
    max_open_positions: int = 3,
    max_leverage: Decimal | str = Decimal("1"),
    max_spread_bps: Decimal | str = Decimal("50"),
    max_slippage_bps: Decimal | str = Decimal("25"),
    min_confidence: Decimal | str = Decimal("0"),
    min_expected_rr: Decimal | str = Decimal("0"),
    safety_buffer_pct: Decimal | str = Decimal("0"),
    external_max_daily_loss_pct: Decimal | str | None = None,
    external_max_weekly_loss_pct: Decimal | str | None = None,
    external_max_total_drawdown_pct: Decimal | str | None = None,
    allowed_instruments: list[str] | tuple[str, ...] | None = None,
    allowed_asset_classes: list[str] | tuple[str, ...] | None = None,
    allowed_strategies: list[str] | tuple[str, ...] | None = None,
    trading_windows: list[Mapping[str, Any]] | tuple[Mapping[str, Any], ...] | None = None,
    news_trading_allowed: bool = True,
    weekend_holding_allowed: bool = True,
    prop_firm: str | None = None,
    prop_phase: str | None = None,
    prop_rules_version: str | None = None,
    external_rules: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Create/update policy without granting PROP certification.

    Any material edit increments policy_version, clears prior certification,
    and disables broker execution so older evidence cannot authorize new rules.
    """
    candidate = TradingAccountPolicy(
        connection_id=str(connection_id),
        user_id=int(user_id),
        account_mode=account_mode,
        execution_permission=execution_permission,
        reset_timezone=reset_timezone,
        max_risk_per_trade_pct=Decimal(str(max_risk_per_trade_pct)),
        max_daily_loss_pct=Decimal(str(max_daily_loss_pct)),
        max_weekly_loss_pct=Decimal(str(max_weekly_loss_pct)),
        max_total_drawdown_pct=Decimal(str(max_total_drawdown_pct)),
        max_open_positions=int(max_open_positions),
        max_leverage=Decimal(str(max_leverage)),
        max_spread_bps=Decimal(str(max_spread_bps)),
        max_slippage_bps=Decimal(str(max_slippage_bps)),
        min_confidence=Decimal(str(min_confidence)),
        min_expected_rr=Decimal(str(min_expected_rr)),
        safety_buffer_pct=Decimal(str(safety_buffer_pct)),
        external_max_daily_loss_pct=(
            Decimal(str(external_max_daily_loss_pct))
            if external_max_daily_loss_pct is not None else None
        ),
        external_max_weekly_loss_pct=(
            Decimal(str(external_max_weekly_loss_pct))
            if external_max_weekly_loss_pct is not None else None
        ),
        external_max_total_drawdown_pct=(
            Decimal(str(external_max_total_drawdown_pct))
            if external_max_total_drawdown_pct is not None else None
        ),
        allowed_instruments=tuple(allowed_instruments or ()),
        allowed_asset_classes=tuple(allowed_asset_classes or ()),
        allowed_strategies=tuple(allowed_strategies or ()),
        trading_windows=tuple(dict(window) for window in (trading_windows or ())),
        news_trading_allowed=bool(news_trading_allowed),
        weekend_holding_allowed=bool(weekend_holding_allowed),
        prop_firm=prop_firm,
        prop_phase=prop_phase,
        prop_rules_version=prop_rules_version,
        certified=False,
        extra_rules=dict(external_rules or {}),
    )

    async with get_session(label="account_policy.configure", timeout_seconds=10.0) as session:
        connection = await _owned_connection(
            session, user_id=int(user_id), connection_id=str(connection_id), lock=True
        )
        row = (
            await session.execute(
                select(TradingAccountPolicyRecord).where(
                    TradingAccountPolicyRecord.connection_id == str(connection_id),
                    TradingAccountPolicyRecord.user_id == int(user_id),
                ).with_for_update().limit(1)
            )
        ).scalar_one_or_none()

        if row is None:
            row = TradingAccountPolicyRecord(
                policy_id=str(uuid4()),
                connection_id=str(connection_id),
                user_id=int(user_id),
                policy_version=1,
                created_at=now_utc_naive(),
            )
            session.add(row)
        else:
            row.policy_version = int(row.policy_version or 0) + 1

        row.account_mode = candidate.account_mode
        row.execution_permission = candidate.execution_permission
        row.status = "configured"
        row.currency = str(currency or "USD").strip().upper()[:8] or "USD"
        row.reset_timezone = candidate.reset_timezone
        row.max_risk_per_trade_pct = candidate.max_risk_per_trade_pct
        row.max_daily_loss_pct = candidate.max_daily_loss_pct
        row.max_weekly_loss_pct = candidate.max_weekly_loss_pct
        row.max_total_drawdown_pct = candidate.max_total_drawdown_pct
        row.max_open_positions = int(candidate.max_open_positions)
        row.max_leverage = candidate.max_leverage
        row.max_spread_bps = candidate.max_spread_bps
        row.max_slippage_bps = candidate.max_slippage_bps
        row.min_confidence = candidate.min_confidence
        row.min_expected_rr = candidate.min_expected_rr
        row.safety_buffer_pct = candidate.safety_buffer_pct
        row.external_max_daily_loss_pct = candidate.external_max_daily_loss_pct
        row.external_max_weekly_loss_pct = candidate.external_max_weekly_loss_pct
        row.external_max_total_drawdown_pct = candidate.external_max_total_drawdown_pct
        row.allowed_instruments = list(candidate.allowed_instruments)
        row.allowed_asset_classes = list(candidate.allowed_asset_classes)
        row.allowed_strategies = list(candidate.allowed_strategies)
        row.trading_windows = [dict(window) for window in candidate.trading_windows]
        row.news_trading_allowed = candidate.news_trading_allowed
        row.weekend_holding_allowed = candidate.weekend_holding_allowed
        row.prop_firm = candidate.prop_firm
        row.prop_phase = candidate.prop_phase
        row.prop_rules_version = candidate.prop_rules_version
        row.external_rules = dict(candidate.extra_rules or {})
        row.certified_at = None
        row.certification_ref = None
        row.updated_at = now_utc_naive()

        next_meta = dict(connection.meta or {})
        next_meta["account_classification"] = candidate.account_mode
        next_meta["account_policy_version"] = int(row.policy_version)
        connection.meta = next_meta
        connection.execution_enabled = False
        connection.updated_at = now_utc_naive()
        await session.commit()
        await session.refresh(row)
        return public_account_policy(row)


async def certify_prop_policy(
    user_id: int,
    connection_id: str,
    *,
    certification_ref: str,
    expected_policy_version: int,
) -> dict[str, Any]:
    """Internal certification action; public users cannot self-certify PROP."""
    ref = str(certification_ref or "").strip()
    if not ref:
        raise ValueError("certification_ref_required")
    async with get_session(label="account_policy.certify", timeout_seconds=8.0) as session:
        await _owned_connection(
            session, user_id=int(user_id), connection_id=connection_id, lock=True
        )
        row = (
            await session.execute(
                select(TradingAccountPolicyRecord).where(
                    TradingAccountPolicyRecord.connection_id == str(connection_id),
                    TradingAccountPolicyRecord.user_id == int(user_id),
                ).with_for_update().limit(1)
            )
        ).scalar_one_or_none()
        if row is None:
            raise LookupError("account_policy_not_found")
        if str(row.account_mode).upper() != "PROP":
            raise PermissionError("prop_account_required")
        if int(row.policy_version) != int(expected_policy_version):
            raise PermissionError("policy_version_changed")
        policy = _domain_policy(row)
        if not policy.prop_firm or not policy.prop_rules_version:
            raise PermissionError("prop_rule_identity_incomplete")
        if (
            policy.external_max_daily_loss_pct is None
            or policy.external_max_total_drawdown_pct is None
        ):
            raise PermissionError("prop_external_limits_required")
        row.status = "certified"
        row.certified_at = now_utc_naive()
        row.certification_ref = ref[:160]
        row.updated_at = now_utc_naive()
        await session.commit()
        await session.refresh(row)
        return public_account_policy(row)


async def set_account_frozen(
    user_id: int,
    connection_id: str,
    *,
    frozen: bool,
    reason: str,
) -> dict[str, Any]:
    reason_value = str(reason or "").strip()
    if frozen and not reason_value:
        raise ValueError("freeze_reason_required")
    async with get_session(label="account_policy.freeze", timeout_seconds=8.0) as session:
        connection = await _owned_connection(
            session, user_id=int(user_id), connection_id=connection_id, lock=True
        )
        row = (
            await session.execute(
                select(TradingAccountPolicyRecord).where(
                    TradingAccountPolicyRecord.connection_id == str(connection_id),
                    TradingAccountPolicyRecord.user_id == int(user_id),
                ).with_for_update().limit(1)
            )
        ).scalar_one_or_none()
        if row is None:
            raise LookupError("account_policy_not_found")
        existing_reason = str(row.frozen_reason or "").strip()
        if not frozen and row.frozen_at is not None and existing_reason and not existing_reason.startswith("user:"):
            raise PermissionError("system_safety_freeze_requires_reconciliation")
        row.frozen_at = now_utc_naive() if frozen else None
        row.frozen_reason = (
            f"user:{reason_value}"[:256] if frozen else None
        )
        row.updated_at = now_utc_naive()
        if frozen:
            connection.execution_enabled = False
        connection.updated_at = now_utc_naive()
        await session.commit()
        await session.refresh(row)
        return public_account_policy(row)


async def reconciliation_snapshot(user_id: int, connection_id: str) -> dict[str, Any]:
    async with get_session(label="account_reconciliation.get", timeout_seconds=6.0) as session:
        await _owned_connection(session, user_id=int(user_id), connection_id=connection_id)
        row = await session.get(BrokerReconciliationState, str(connection_id))
        await session.rollback()
    if row is None:
        return {
            "connection_id": str(connection_id),
            "user_id": int(user_id),
            "status": "UNKNOWN",
            "ready": False,
            "discrepancy_code": "reconciliation_not_recorded",
        }
    return {
        "connection_id": row.connection_id,
        "user_id": row.user_id,
        "status": row.status,
        "ready": str(row.status).upper() in _RECONCILIATION_HEALTHY,
        "discrepancy_code": row.discrepancy_code,
        "details": dict(row.details or {}),
        "last_reconciled_at": _iso(row.last_reconciled_at),
        "frozen_at": _iso(row.frozen_at),
        "updated_at": _iso(row.updated_at),
    }


async def record_reconciliation(
    user_id: int,
    connection_id: str,
    *,
    status: str,
    discrepancy_code: str | None = None,
    details: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    normalized = str(status or "").strip().upper()
    allowed = _RECONCILIATION_HEALTHY | _RECONCILIATION_BLOCKING
    if normalized not in allowed:
        raise ValueError("invalid_reconciliation_status")

    async with get_session(label="account_reconciliation.record", timeout_seconds=8.0) as session:
        connection = await _owned_connection(
            session, user_id=int(user_id), connection_id=connection_id, lock=True
        )
        row = await session.get(
            BrokerReconciliationState, str(connection_id), with_for_update=True
        )
        if row is None:
            row = BrokerReconciliationState(
                connection_id=str(connection_id), user_id=int(user_id)
            )
            session.add(row)
        if int(row.user_id) != int(user_id):
            raise PermissionError("reconciliation_owner_mismatch")
        row.status = normalized
        row.discrepancy_code = (
            str(discrepancy_code).strip()[:128] if discrepancy_code else None
        )
        row.details = dict(details or {})
        row.last_reconciled_at = (
            now_utc_naive() if normalized == "HEALTHY" else row.last_reconciled_at
        )
        row.frozen_at = (
            now_utc_naive()
            if normalized in {"DEGRADED", "FROZEN", "AUTH_EXPIRED"}
            else None
        )
        row.updated_at = now_utc_naive()

        policy = (
            await session.execute(
                select(TradingAccountPolicyRecord).where(
                    TradingAccountPolicyRecord.connection_id == str(connection_id),
                    TradingAccountPolicyRecord.user_id == int(user_id),
                ).with_for_update().limit(1)
            )
        ).scalar_one_or_none()
        # A transient reconciliation pass blocks the current decision but
        # does not silently revoke the user's account permission. Material
        # discrepancies/disconnect/auth failures freeze new execution until
        # explicitly resolved.
        if normalized in {"DEGRADED", "FROZEN", "AUTH_EXPIRED", "DISCONNECTED"}:
            connection.execution_enabled = False
            if policy is not None:
                policy.frozen_at = now_utc_naive()
                policy.frozen_reason = str(
                    discrepancy_code or f"reconciliation_{normalized.lower()}"
                )[:256]
                policy.updated_at = now_utc_naive()
        connection.updated_at = now_utc_naive()
        await session.commit()
    return await reconciliation_snapshot(int(user_id), str(connection_id))


async def evaluate_persisted_account_policy(
    user_id: int,
    connection_id: str,
    snapshot: AccountRiskSnapshot,
    *,
    execution_mode: str,
) -> AccountPolicyDecision:
    async with get_session(label="account_policy.evaluate", timeout_seconds=6.0) as session:
        await _owned_connection(session, user_id=int(user_id), connection_id=connection_id)
        row = (
            await session.execute(
                select(TradingAccountPolicyRecord).where(
                    TradingAccountPolicyRecord.connection_id == str(connection_id),
                    TradingAccountPolicyRecord.user_id == int(user_id),
                ).limit(1)
            )
        ).scalar_one_or_none()
        reconciliation = await session.get(BrokerReconciliationState, str(connection_id))
        await session.rollback()
    if row is None:
        return AccountPolicyDecision(
            False, "ACCOUNT_POLICY_BLOCKED", ("account_policy_missing",), 0
        )
    if reconciliation is None or str(reconciliation.status).upper() != "HEALTHY":
        snapshot = AccountRiskSnapshot(
            **{**asdict(snapshot), "reconciliation_ready": False}
        )
    return evaluate_account_policy(
        _domain_policy(row), snapshot, execution_mode=execution_mode
    )


async def record_execution_decision(
    *,
    user_id: int,
    connection_id: str,
    signal_id: str,
    execution_mode: str,
    account_mode: str,
    policy_version: int,
    allowed: bool,
    reasons: tuple[str, ...] | list[str],
    market_snapshot: Mapping[str, Any] | None = None,
    risk_snapshot: Mapping[str, Any] | None = None,
    request_snapshot: Mapping[str, Any] | None = None,
    model_versions: Mapping[str, Any] | None = None,
    strategy_versions: Mapping[str, Any] | None = None,
    trace_id: str | None = None,
) -> str:
    """Append an immutable decision snapshot containing no credentials."""
    decision_id = str(uuid4())
    async with get_session(label="account_policy.decision", timeout_seconds=8.0) as session:
        await _owned_connection(session, user_id=int(user_id), connection_id=connection_id)
        row = BrokerExecutionDecision(
            decision_id=decision_id,
            user_id=int(user_id),
            connection_id=str(connection_id),
            signal_id=str(signal_id),
            execution_mode=str(execution_mode),
            account_mode=str(account_mode).upper(),
            policy_version=int(policy_version),
            decision_status="ALLOWED" if allowed else "BLOCKED",
            reason_codes=list(dict.fromkeys(str(item) for item in reasons)),
            release_sha=str(
                os.getenv("GIT_COMMIT_SHA")
                or os.getenv("RAILWAY_GIT_COMMIT_SHA")
                or ""
            )[:64] or None,
            execution_engine_version="account-policy-v1",
            model_versions=dict(model_versions or {}),
            strategy_versions=dict(strategy_versions or {}),
            market_snapshot=dict(market_snapshot or {}),
            risk_snapshot=dict(risk_snapshot or {}),
            request_snapshot=dict(request_snapshot or {}),
            trace_id=str(trace_id)[:128] if trace_id else None,
            created_at=now_utc_naive(),
        )
        session.add(row)
        await session.commit()
    return decision_id


__all__ = [
    "public_account_policy",
    "get_account_policy",
    "configure_account_policy",
    "certify_prop_policy",
    "set_account_frozen",
    "reconciliation_snapshot",
    "record_reconciliation",
    "evaluate_persisted_account_policy",
    "record_execution_decision",
]
