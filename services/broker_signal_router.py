"""Provider-neutral signal execution router with one-position evidence."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping



@dataclass(frozen=True, slots=True)
class BrokerRouteResult:
    success: bool
    message: str
    order_id: str | None = None
    status: str = "blocked"
    error: str | None = None
    provider: str | None = None
    evidence: dict[str, Any] | None = None


async def _has_bybit_link(telegram_user_id: int) -> bool:
    try:
        from db.models import RuntimeState
        from db.session import get_session

        async with get_session(label="broker.auto_provider", timeout_seconds=5.0) as session:
            row = await session.get(RuntimeState, f"broker_exchange:{int(telegram_user_id)}:bybit")
        value = dict(getattr(row, "value", {}) or {}) if row is not None else {}
        return bool(value.get("api_key_enc") and value.get("api_secret_enc"))
    except Exception:
        return False


async def route_signal_to_broker(
    signal: Mapping[str, Any],
    telegram_user_id: int,
    execution_mode: str = "auto",
) -> BrokerRouteResult:
    from core.execution_claims import execution_destination_lock
    from db.session import get_session
    from services.execution_evidence import get_execution_evidence

    signal_id = str(signal.get("signal_id") or signal.get("id") or "").strip()
    if not signal_id:
        return BrokerRouteResult(False, "Signal ID is required", error="signal_id_missing")
    async with execution_destination_lock(int(telegram_user_id), signal_id) as claimed:
        if not claimed:
            return BrokerRouteResult(
                False,
                "Execution destination is busy or unavailable",
                status="deferred",
                error="execution_destination_lock_unavailable",
            )
        async with get_session(label="broker.destination_preflight", timeout_seconds=8.0) as session:
            before = await get_execution_evidence(
                session, telegram_user_id=int(telegram_user_id), signal_id=signal_id,
            )
        if before.get("position_count"):
            position = before.get("position") or {}
            if before.get("exactly_one") and position.get("destination") == "broker":
                return BrokerRouteResult(
                    True,
                    "Existing broker execution confirmed",
                    str(position.get("reference")),
                    str(position.get("status") or "confirmed"),
                    provider=str(position.get("provider") or "broker"),
                    evidence=before,
                )
            return BrokerRouteResult(
                False,
                "A paper position or ambiguous execution evidence already exists",
                status="blocked",
                error="execution_destination_already_claimed",
                evidence=before,
            )

        async with get_session(label="broker.profile_policy", timeout_seconds=8.0) as session:
            from services.user_intelligence import get_user_trading_preferences
            prefs = await get_user_trading_preferences(session, int(telegram_user_id))
        provider = str(getattr(prefs, "execution_provider", "auto") or "auto").strip().lower()
        asset_class = str(signal.get("asset_class") or "").strip().lower()
        symbol = str(signal.get("asset") or signal.get("symbol") or "").strip().upper()
        if provider == "auto":
            is_bybit_asset = asset_class in {"", "crypto"} and symbol.endswith("USDT")
            provider = "bybit" if is_bybit_asset and await _has_bybit_link(int(telegram_user_id)) else "mt5"
        if provider == "bybit":
            from services.bybit_signal_router import route_signal_to_bybit

            routed = await route_signal_to_bybit(
                signal, int(telegram_user_id), execution_mode=execution_mode,
            )
        elif provider == "mt5":
            from services.mt5_signal_router import route_signal_to_mt5

            routed = await route_signal_to_mt5(
                dict(signal), int(telegram_user_id), execution_mode=execution_mode,
            )
        else:
            return BrokerRouteResult(
                False, "Unsupported execution provider", error="unsupported_execution_provider",
            )

        order_id = str(getattr(routed, "order_id", None) or "").strip() or None
        if not bool(getattr(routed, "success", False)):
            return BrokerRouteResult(
                False,
                str(getattr(routed, "message", None) or "Broker execution blocked"),
                order_id,
                str(getattr(routed, "status", None) or "blocked"),
                str(getattr(routed, "error", None) or "broker_execution_blocked"),
                provider,
            )
        async with get_session(label="broker.execution_evidence", timeout_seconds=8.0) as session:
            evidence = await get_execution_evidence(
                session,
                telegram_user_id=int(telegram_user_id),
                signal_id=signal_id,
                expected_reference=order_id,
            )
        if not evidence.get("exactly_one"):
            return BrokerRouteResult(
                False,
                "Broker acknowledged the request but canonical execution evidence is ambiguous",
                order_id,
                "ambiguous",
                "execution_evidence_not_exactly_one",
                provider,
                evidence,
            )
        position = dict(evidence.get("position") or {})
        return BrokerRouteResult(
            True,
            str(getattr(routed, "message", None) or "Broker execution confirmed"),
            order_id,
            str(position.get("status") or getattr(routed, "status", None) or "confirmed"),
            None,
            provider,
            evidence,
        )


__all__ = ["BrokerRouteResult", "route_signal_to_broker"]