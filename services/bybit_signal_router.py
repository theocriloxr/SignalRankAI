"""Fail-closed Bybit signal execution router."""
from __future__ import annotations

import hashlib
import json
import math
import os
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Mapping

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from db.models import BrokerExecution, MT5Execution, RuntimeState, SignalDelivery, User
from db.session import get_session
from execution.service import ExecutionGate, ExecutionRequest
from services.bybit_client import (
    BybitAmbiguousOrderError,
    BybitCredentials,
    BybitError,
    BybitV5Client,
)
from services.security import decrypt_secret
from services.execution_quota import release_user_execution_quota, reserve_user_execution_quota
from utils.timeutils import now_utc_naive


@dataclass(frozen=True, slots=True)
class BybitRouteResult:
    success: bool
    message: str
    order_id: str | None = None
    status: str = "blocked"
    error: str | None = None


def _state_key(telegram_user_id: int) -> str:
    return f"broker_exchange:{int(telegram_user_id)}:bybit"


def _tp1(signal: Mapping[str, Any]) -> float:
    for key in ("tp1", "take_profit_1"):
        try:
            value = float(signal.get(key) or 0)
            if value > 0:
                return value
        except (TypeError, ValueError):
            pass
    raw = signal.get("take_profit") or signal.get("take_profits")
    if isinstance(raw, (list, tuple)) and raw:
        return float(raw[0])
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list) and parsed:
                return float(parsed[0])
            if isinstance(parsed, Mapping):
                return float(parsed.get("tp1") or parsed.get("1") or 0)
        except Exception:
            try:
                return float(raw.split(",")[0].strip(" []"))
            except Exception:
                return 0.0
    return 0.0


def _asset_supported(signal: Mapping[str, Any]) -> bool:
    asset_class = str(signal.get("asset_class") or "").strip().lower()
    symbol = str(signal.get("asset") or signal.get("symbol") or "").strip().upper()
    return (asset_class in {"", "crypto"}) and symbol.endswith("USDT")


async def _resources_available() -> bool:
    try:
        from core.resource_governor import ResourceState, get_resource_governor
        return get_resource_governor().snapshot().state is not ResourceState.CRITICAL
    except Exception:
        return False


async def route_signal_to_bybit(
    signal: Mapping[str, Any],
    telegram_user_id: int,
    execution_mode: str = "auto",
) -> BybitRouteResult:
    if str(execution_mode or "").strip().lower() in {"auto", "copy", "copy_trade"}:
        from core.live_execution_integrity import evaluate_live_signal_admission
        integrity = evaluate_live_signal_admission(signal)
        if not integrity.allowed:
            reason = "live_integrity_blocked:" + ",".join(integrity.reasons)
            return BybitRouteResult(False, reason, error=reason)
    if not _asset_supported(signal):
        return BybitRouteResult(False, "Bybit execution supports USDT crypto signals only", error="unsupported_asset")

    signal_id = str(signal.get("signal_id") or signal.get("id") or "").strip()
    symbol = str(signal.get("asset") or signal.get("symbol") or "").strip().upper()
    entry = float(signal.get("entry") or 0)
    stop = float(signal.get("stop_loss") or signal.get("stop") or 0)
    take_profit = _tp1(signal)
    direction = str(signal.get("direction") or signal.get("side") or "").strip().lower()
    if not signal_id or entry <= 0 or stop <= 0 or take_profit <= 0 or direction not in {"buy", "sell", "long", "short"}:
        return BybitRouteResult(False, "Signal lacks broker-safe entry, stop, TP, or direction", error="invalid_signal")

    async with get_session(label="bybit.preflight", timeout_seconds=8.0) as session:
        user = (await session.execute(select(User).where(User.telegram_user_id == int(telegram_user_id)))).scalar_one_or_none()
        if user is None:
            return BybitRouteResult(False, "User profile not found", error="user_not_found")
        try:
            from services.user_intelligence import (
                get_user_trading_preferences,
                signal_matches_preferences,
            )
            profile_prefs = await get_user_trading_preferences(
                session,
                int(telegram_user_id),
            )
        except Exception:
            profile_prefs = None
        if profile_prefs is None:
            return BybitRouteResult(False, "User trading profile unavailable", error="user_profile_unavailable")
        profile_ok, profile_reason = signal_matches_preferences(dict(signal), profile_prefs)
        if not profile_ok:
            return BybitRouteResult(
                False,
                f"Signal does not match user profile: {profile_reason}",
                error="user_profile_signal_mismatch",
            )
        if str(profile_prefs.trading_mode or "paper").lower() not in {"live", "both"}:
            return BybitRouteResult(False, "Live trading is disabled in the user profile", error="profile_live_disabled")
        requested_mode = str(execution_mode or "auto").strip().lower()
        configured_mode = str(profile_prefs.execution_mode or "manual").strip().lower()
        if requested_mode in {"copy", "copy_trade"} and configured_mode != "copy_trade":
            return BybitRouteResult(False, "Copy trading is not enabled in the user profile", error="profile_copy_disabled")
        if requested_mode in {"auto", "live"} and configured_mode not in {"auto", "live"}:
            return BybitRouteResult(False, "Automatic execution is not enabled in the user profile", error="profile_auto_disabled")
        configured_provider = str(profile_prefs.execution_provider or "auto").strip().lower()
        if configured_provider not in {"auto", "bybit"}:
            return BybitRouteResult(False, "User profile selected a different execution provider", error="profile_provider_mismatch")
        open_statuses = ("reserved", "submitting", "ambiguous", "confirmed", "open", "reconciliation_pending")
        bybit_open_count = int((await session.execute(
            select(func.count(BrokerExecution.id)).where(
                BrokerExecution.user_id == int(user.id),
                func.lower(BrokerExecution.status).in_(open_statuses),
            )
        )).scalar_one() or 0)
        mt5_open_count = int((await session.execute(
            select(func.count(MT5Execution.id)).where(
                MT5Execution.user_id == int(user.id),
                func.lower(MT5Execution.status).in_(("pending", "confirmed", "open", "submitted")),
            )
        )).scalar_one() or 0)
        duplicate_asset = int((await session.execute(
            select(func.count(BrokerExecution.id)).where(
                BrokerExecution.user_id == int(user.id),
                BrokerExecution.symbol == symbol,
                func.lower(BrokerExecution.status).in_(open_statuses),
            )
        )).scalar_one() or 0) > 0
        max_positions = max(1, int(profile_prefs.max_concurrent_positions or 1))
        if duplicate_asset:
            return BybitRouteResult(False, "An open execution already exists for this asset", error="duplicate_open_asset")
        if bybit_open_count + mt5_open_count >= max_positions:
            return BybitRouteResult(False, "User profile maximum concurrent positions reached", error="profile_max_concurrent_positions")
        state_row = await session.get(RuntimeState, _state_key(int(telegram_user_id)))
        value = dict(getattr(state_row, "value", {}) or {}) if state_row else {}
        delivery = (await session.execute(
            select(SignalDelivery).where(
                SignalDelivery.user_id == int(user.id),
                SignalDelivery.signal_id == signal_id,
                SignalDelivery.sent_ok.is_(True),
            )
        )).scalar_one_or_none()

    key_enc = str(value.get("api_key_enc") or "")
    secret_enc = str(value.get("api_secret_enc") or "")
    api_key = decrypt_secret(key_enc) if key_enc else None
    api_secret = decrypt_secret(secret_enc) if secret_enc else None
    sandbox = bool(value.get("sandbox", True))
    permissions = dict(value.get("permissions") or {})
    account_ready = bool(api_key and api_secret and permissions.get("trade") and not permissions.get("withdraw") and not permissions.get("internal_transfer"))

    client = BybitV5Client(BybitCredentials(str(api_key or ""), str(api_secret or ""), sandbox))
    permission_info: dict[str, Any] = {}
    if account_ready:
        try:
            permission_info = await client.verify_trade_only_key(
                require_ip_binding=str(os.getenv("BYBIT_REQUIRE_IP_BINDING", "1")).strip().lower()
                in {"1", "true", "yes", "on"}
            )
            account_ready = (
                bool(permission_info.get("trade"))
                and not bool(permission_info.get("withdraw"))
                and not bool(permission_info.get("internal_transfer"))
            )
        except BybitError:
            account_ready = False
    wallet_ok = quote_ok = reconciliation_ok = False
    has_open_position = True
    quote_age = 0.0
    wallet_equity = 0.0
    try:
        wallet = await client.get_wallet_balance(coin="USDT") if account_ready else {}
        accounts = list(wallet.get("list") or [])
        if accounts:
            wallet_equity = float(accounts[0].get("totalEquity") or accounts[0].get("totalWalletBalance") or 0)
        ticker = await client.get_ticker(symbol) if account_ready else {}
        quote_value = float(ticker.get("lastPrice") or 0)
        wallet_ok = wallet_equity > 0
        quote_ok = quote_value > 0 and abs(quote_value - entry) / entry <= float(os.getenv("BYBIT_MAX_ENTRY_DEVIATION_PCT", "1.0")) / 100.0
        positions = await client.get_positions(symbol=symbol) if account_ready else []
        reconciliation_ok = isinstance(positions, list)
        has_open_position = any(float(item.get("size") or 0) > 0 for item in positions)
    except BybitError:
        wallet_ok = quote_ok = reconciliation_ok = False

    risk_pct = min(
        max(float(getattr(user, "max_risk_percentage", 1.0) or 1.0), 0.1),
        max(0.1, float(getattr(profile_prefs, "risk_per_trade_pct", 1.0) or 1.0)),
        float(os.getenv("LIVE_MAX_RISK_PER_TRADE_PCT", "1.0")),
    )
    risk_amount = wallet_equity * risk_pct / 100.0
    stop_distance = abs(entry - stop)
    quantity = risk_amount / stop_distance if stop_distance > 0 else 0.0
    max_notional = wallet_equity * float(os.getenv("BYBIT_MAX_NOTIONAL_MULTIPLIER", "1.0"))
    if quantity * entry > max_notional > 0:
        quantity = max_notional / entry
    risk_allowed = math.isfinite(quantity) and quantity > 0 and wallet_ok and not has_open_position

    optin_key = "copyexec_user_optin" if execution_mode == "copy_trade" else "autoexec_user_optin"
    async with get_session(label="bybit.consent", timeout_seconds=5.0) as session:
        optin = await session.get(RuntimeState, f"{optin_key}:{int(telegram_user_id)}")
        user_enabled = bool((dict(getattr(optin, "value", {}) or {})).get("enabled")) if optin else False

    kill_switch = True
    try:
        from core.redis_state import state
        kill_state = await state.get_killswitch()
        kill_switch = bool(getattr(kill_state, "enabled", True))
    except Exception:
        kill_switch = True

    gate_request = ExecutionRequest(
        user_id=int(telegram_user_id),
        signal_id=signal_id,
        signal=dict(signal),
        tier=str(getattr(user, "tier", "free") or "free"),
        mode=execution_mode,
        consent=bool(getattr(user, "accepted_terms", False)),
        account_ready=account_ready,
        quote_trusted=quote_ok,
        market_open=True,
        risk_allowed=risk_allowed,
        evidence_allowed=delivery is not None,
        kill_switch=kill_switch,
        account_id=str(value.get("masked_key") or "bybit"),
        user_enabled=user_enabled,
        account_is_demo=sandbox,
        credentials_encrypted=bool(key_enc and secret_enc),
        quote_age_seconds=quote_age,
        max_quote_age_seconds=10.0,
        broker_healthy=bool(account_ready and wallet_ok and quote_ok),
        resources_available=await _resources_available(),
        reconciliation_ready=reconciliation_ok,
        broker_provider="bybit",
    )
    gate = ExecutionGate()
    idempotency_key = gate_request.key()
    client_order_id = f"sr-{hashlib.sha256(idempotency_key.encode()).hexdigest()[:30]}"

    async def submit(_: ExecutionRequest) -> dict[str, Any]:
        quota_user_id: int | None = None
        async with get_session(label="bybit.reserve", timeout_seconds=8.0) as session:
            existing = (await session.execute(select(BrokerExecution).where(
                BrokerExecution.provider == "bybit",
                BrokerExecution.idempotency_key == idempotency_key,
            ).with_for_update())).scalar_one_or_none()
            if existing is not None:
                existing_status = str(existing.status or "").strip().lower()
                if existing_status in {"rejected", "cancelled", "failed", "blocked"}:
                    return {
                        "success": False,
                        "status": existing_status.upper(),
                        "error": existing.error_code or "previous_execution_rejected",
                    }
                if existing.provider_order_id and existing_status in {
                    "submitted", "confirmed", "open", "partially_filled", "filled", "closed", "success"
                }:
                    return {"success": True, "order_id": existing.provider_order_id, "status": existing.status}
                return {
                    "success": False,
                    "status": "AMBIGUOUS" if existing_status in {"ambiguous", "submitting"} else "DUPLICATE",
                    "error": "execution_state_requires_reconciliation",
                }
            row = BrokerExecution(
                user_id=int(user.id), signal_id=signal_id, provider="bybit",
                account_ref=str(value.get("masked_key") or "bybit"), idempotency_key=idempotency_key,
                provider_client_order_id=client_order_id, symbol=symbol, direction=direction,
                quantity=float(quantity), entry_price=entry, stop_loss=stop, take_profit=take_profit,
                status="reserved", tier_at_execution=str(getattr(user, "tier", "vip") or "vip"),
                meta={
                    "sandbox": sandbox,
                    "execution_mode": execution_mode,
                    "permission_reverified": bool(permission_info),
                    "ip_bound": bool(permission_info.get("ip_bound")),
                },
            )
            session.add(row)
            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()
                return {"success": False, "status": "DUPLICATE", "error": "execution_already_reserved"}

        quota_ok, quota_reason, quota_user_id = await reserve_user_execution_quota(
            int(telegram_user_id),
            tier=str(getattr(user, "tier", "vip") or "vip"),
            execution_mode=execution_mode,
        )
        if not quota_ok:
            async with get_session(label="bybit.quota_block", timeout_seconds=8.0) as session:
                row = (await session.execute(select(BrokerExecution).where(
                    BrokerExecution.provider == "bybit", BrokerExecution.idempotency_key == idempotency_key,
                ).with_for_update())).scalar_one()
                row.status = "blocked"
                row.error_code = str(quota_reason)[:128]
                row.updated_at = now_utc_naive()
                await session.commit()
            return {"success": False, "status": "BLOCKED", "error": quota_reason}

        async with get_session(label="bybit.submitting", timeout_seconds=8.0) as session:
            row = (await session.execute(select(BrokerExecution).where(
                BrokerExecution.provider == "bybit", BrokerExecution.idempotency_key == idempotency_key,
            ).with_for_update())).scalar_one()
            row.status = "submitting"
            row.updated_at = now_utc_naive()
            await session.commit()

        try:
            provider_result = await client.place_market_order(
                symbol=symbol,
                side=direction,
                qty=Decimal(str(quantity)),
                stop_loss=Decimal(str(stop)),
                take_profit=Decimal(str(take_profit)),
                order_link_id=client_order_id,
            )
        except BybitAmbiguousOrderError as exc:
            async with get_session(label="bybit.ambiguous", timeout_seconds=8.0) as session:
                row = (await session.execute(select(BrokerExecution).where(BrokerExecution.provider == "bybit", BrokerExecution.idempotency_key == idempotency_key).with_for_update())).scalar_one()
                row.status = "ambiguous"
                row.error_code = str(exc)[:128]
                row.updated_at = now_utc_naive()
                await session.commit()
            raise
        except BybitError as exc:
            async with get_session(label="bybit.rejected", timeout_seconds=8.0) as session:
                row = (await session.execute(select(BrokerExecution).where(BrokerExecution.provider == "bybit", BrokerExecution.idempotency_key == idempotency_key).with_for_update())).scalar_one()
                row.status = "rejected"
                row.error_code = str(exc)[:128]
                row.closed_at = now_utc_naive()
                row.updated_at = now_utc_naive()
                await session.commit()
            await release_user_execution_quota(quota_user_id)
            return {"success": False, "status": "REJECTED", "error": str(exc)}

        async with get_session(label="bybit.confirm", timeout_seconds=8.0) as session:
            row = (await session.execute(select(BrokerExecution).where(BrokerExecution.provider == "bybit", BrokerExecution.idempotency_key == idempotency_key).with_for_update())).scalar_one()
            row.status = "confirmed"
            row.provider_order_id = str(provider_result["order_id"])
            row.confirmed_at = now_utc_naive()
            row.updated_at = now_utc_naive()
            row.meta = {**dict(row.meta or {}), "provider_status": provider_result.get("status")}
            await session.commit()
        return provider_result

    result = await gate.execute(gate_request, submit)
    if result.accepted:
        return BybitRouteResult(True, "Bybit order confirmed", result.order_id, result.status)
    return BybitRouteResult(False, "Bybit execution blocked", status=result.status, error=result.error or ",".join(result.decision.reasons))


__all__ = ["BybitRouteResult", "route_signal_to_bybit"]
