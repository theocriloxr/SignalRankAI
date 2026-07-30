"""Provider-neutral signal execution router."""
from __future__ import annotations

from typing import Any, Mapping

from db.user_preferences import get_user_preferences


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
):
    prefs = await get_user_preferences(int(telegram_user_id))
    provider = str(getattr(prefs, "execution_provider", "auto") or "auto").strip().lower()
    asset_class = str(signal.get("asset_class") or "").strip().lower()
    symbol = str(signal.get("asset") or signal.get("symbol") or "").strip().upper()
    if provider == "auto":
        is_bybit_asset = asset_class in {"", "crypto"} and symbol.endswith("USDT")
        provider = "bybit" if is_bybit_asset and await _has_bybit_link(int(telegram_user_id)) else "mt5"
    if provider == "bybit":
        from services.bybit_signal_router import route_signal_to_bybit
        return await route_signal_to_bybit(signal, int(telegram_user_id), execution_mode=execution_mode)
    if provider == "mt5":
        from services.mt5_signal_router import route_signal_to_mt5
        return await route_signal_to_mt5(dict(signal), int(telegram_user_id), execution_mode=execution_mode)
    raise ValueError("unsupported_execution_provider")


__all__ = ["route_signal_to_broker"]
