"""Safe preparation of a connected DEMO account for broker certification.

This module deliberately stops short of execution enablement. It refreshes
provider-backed read-only proof and applies a bounded MANUAL DEMO policy while
leaving the broker connection execution toggle disabled.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any, Mapping


_DEMO_MAX_RISK_PER_TRADE = Decimal("0.005")
_DEMO_MAX_DAILY_LOSS = Decimal("0.02")
_DEMO_MAX_WEEKLY_LOSS = Decimal("0.04")
_DEMO_MAX_TOTAL_DRAWDOWN = Decimal("0.06")
_DEMO_MAX_OPEN_POSITIONS = 1
_DEMO_MAX_LEVERAGE = Decimal("3")
_DEMO_MAX_SPREAD_BPS = Decimal("50")
_DEMO_MAX_SLIPPAGE_BPS = Decimal("25")


def _decimal(value: Any, default: Decimal) -> Decimal:
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return default
    return parsed if parsed.is_finite() and parsed >= 0 else default


def _cap_decimal(value: Any, cap: Decimal, default: Decimal) -> Decimal:
    return min(_decimal(value, default), cap)


def _credential_ready(connection: Mapping[str, Any]) -> bool:
    fmt = str(connection.get("credential_format") or "").strip().lower()
    if fmt.startswith("envelope_"):
        return bool(connection.get("credential_encrypted"))
    if fmt == "provider_managed":
        return bool(str(connection.get("external_account_id") or "").strip())
    return False


def _bounded_demo_policy_kwargs(policy: Mapping[str, Any]) -> dict[str, Any]:
    """Return a policy that can only tighten the current account limits."""
    try:
        max_positions = max(0, int(policy.get("max_open_positions") or 0))
    except (TypeError, ValueError):
        max_positions = _DEMO_MAX_OPEN_POSITIONS
    max_positions = min(
        max_positions if max_positions > 0 else _DEMO_MAX_OPEN_POSITIONS,
        _DEMO_MAX_OPEN_POSITIONS,
    )

    return {
        "account_mode": "DEMO",
        "execution_permission": "MANUAL",
        "reset_timezone": str(policy.get("reset_timezone") or "UTC"),
        "currency": str(policy.get("currency") or "USD"),
        "max_risk_per_trade_pct": _cap_decimal(
            policy.get("max_risk_per_trade_pct"),
            _DEMO_MAX_RISK_PER_TRADE,
            _DEMO_MAX_RISK_PER_TRADE,
        ),
        "max_daily_loss_pct": _cap_decimal(
            policy.get("max_daily_loss_pct"),
            _DEMO_MAX_DAILY_LOSS,
            _DEMO_MAX_DAILY_LOSS,
        ),
        "max_weekly_loss_pct": _cap_decimal(
            policy.get("max_weekly_loss_pct"),
            _DEMO_MAX_WEEKLY_LOSS,
            _DEMO_MAX_WEEKLY_LOSS,
        ),
        "max_total_drawdown_pct": _cap_decimal(
            policy.get("max_total_drawdown_pct"),
            _DEMO_MAX_TOTAL_DRAWDOWN,
            _DEMO_MAX_TOTAL_DRAWDOWN,
        ),
        "max_open_positions": max_positions,
        "max_leverage": _cap_decimal(
            policy.get("max_leverage"),
            _DEMO_MAX_LEVERAGE,
            _DEMO_MAX_LEVERAGE,
        ),
        "max_spread_bps": _cap_decimal(
            policy.get("max_spread_bps"),
            _DEMO_MAX_SPREAD_BPS,
            _DEMO_MAX_SPREAD_BPS,
        ),
        "max_slippage_bps": _cap_decimal(
            policy.get("max_slippage_bps"),
            _DEMO_MAX_SLIPPAGE_BPS,
            _DEMO_MAX_SLIPPAGE_BPS,
        ),
        "min_confidence": _decimal(
            policy.get("min_confidence"), Decimal("0")
        ),
        "min_expected_rr": _decimal(
            policy.get("min_expected_rr"), Decimal("0")
        ),
        "safety_buffer_pct": Decimal("0"),
        "external_max_daily_loss_pct": None,
        "external_max_weekly_loss_pct": None,
        "external_max_total_drawdown_pct": None,
        "allowed_instruments": list(policy.get("allowed_instruments") or []),
        "allowed_asset_classes": list(policy.get("allowed_asset_classes") or []),
        "allowed_strategies": list(policy.get("allowed_strategies") or []),
        "trading_windows": list(policy.get("trading_windows") or []),
        "news_trading_allowed": False,
        "weekend_holding_allowed": False,
        "prop_firm": None,
        "prop_phase": None,
        "prop_rules_version": None,
        "external_rules": {},
    }


async def _connections(user_id: int) -> list[dict[str, Any]]:
    from services.broker_connections import list_connections

    return await list_connections(int(user_id))


async def _verify(user_id: int, connection_id: str) -> dict[str, Any]:
    from services.broker_verification import verify_broker_connection_read_only

    return await verify_broker_connection_read_only(
        int(user_id), str(connection_id)
    )


async def _policy(user_id: int, connection_id: str) -> dict[str, Any]:
    from services.account_policies import get_account_policy

    return await get_account_policy(int(user_id), str(connection_id))


async def _reconciliation(user_id: int, connection_id: str) -> dict[str, Any]:
    from services.account_policies import reconciliation_snapshot

    return await reconciliation_snapshot(int(user_id), str(connection_id))


async def _configure(
    user_id: int,
    connection_id: str,
    **kwargs: Any,
) -> dict[str, Any]:
    from services.account_policies import configure_account_policy

    return await configure_account_policy(
        int(user_id),
        str(connection_id),
        **kwargs,
    )


def _find_owned_connection(
    rows: list[dict[str, Any]], connection_id: str
) -> dict[str, Any]:
    target = str(connection_id or "").strip()
    for row in rows:
        if str(row.get("connection_id") or "") == target:
            return dict(row)
    raise LookupError("broker_connection_not_found")


def _assert_provider_demo_identity(connection: Mapping[str, Any]) -> None:
    environment = str(connection.get("environment") or "").strip().lower()
    classification = str(
        connection.get("account_classification") or ""
    ).strip().upper()
    if environment != "demo" or classification != "DEMO":
        raise PermissionError("provider_proven_demo_account_required")


async def prepare_demo_certification(
    user_id: int,
    connection_id: str,
) -> dict[str, Any]:
    """Prepare one owned provider-proven DEMO account without enabling execution."""
    connection = _find_owned_connection(
        await _connections(int(user_id)),
        connection_id,
    )
    _assert_provider_demo_identity(connection)

    verification = await _verify(int(user_id), str(connection_id))
    if verification.get("success") is not True:
        raise PermissionError(
            str(verification.get("error") or "demo_read_only_verification_required")
        )

    refreshed = _find_owned_connection(
        await _connections(int(user_id)),
        connection_id,
    )
    _assert_provider_demo_identity(refreshed)
    if not refreshed.get("verified_at"):
        raise PermissionError("demo_provider_verification_timestamp_required")
    if not _credential_ready(refreshed):
        raise PermissionError("demo_canonical_credentials_not_ready")

    reconciliation = verification.get("reconciliation")
    if not isinstance(reconciliation, Mapping):
        reconciliation = await _reconciliation(
            int(user_id), str(connection_id)
        )
    if (
        str(reconciliation.get("status") or "").strip().upper() != "HEALTHY"
        or reconciliation.get("ready") is not True
    ):
        raise PermissionError("demo_reconciliation_not_healthy")

    current_policy = await _policy(int(user_id), str(connection_id))
    prepared_policy = await _configure(
        int(user_id),
        str(connection_id),
        **_bounded_demo_policy_kwargs(current_policy),
    )

    final_connection = _find_owned_connection(
        await _connections(int(user_id)),
        connection_id,
    )
    if final_connection.get("execution_enabled") is True:
        # configure_account_policy is required to disable execution on every
        # material policy version change. Treat any violation as a hard error.
        raise RuntimeError("demo_prepare_execution_invariant_violated")

    return {
        "connection": final_connection,
        "policy": prepared_policy,
        "reconciliation": dict(reconciliation),
        "demo_certification_prepared": True,
        "read_only_verification": True,
        "execution_permission": "MANUAL",
        "execution_enabled": False,
        "order_placed": False,
        "next_action": (
            "Accept execution-risk terms, then explicitly enable this DEMO "
            "account before the bounded certification order lifecycle."
        ),
    }


__all__ = [
    "prepare_demo_certification",
]
