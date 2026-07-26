from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from engine import tiered_executor


@pytest.mark.asyncio
async def test_premium_execution_delegates_to_canonical_router(monkeypatch) -> None:
    user = SimpleNamespace(
        id=11,
        telegram_user_id=777,
        tier="PREMIUM",
        daily_executions_today=0,
        daily_executions_reset_at=None,
    )
    signal = SimpleNamespace(
        signal_id="sig-1",
        asset="EURUSD",
        direction="long",
        entry=1.10,
        stop_loss=1.09,
        take_profit="[1.11, 1.12, 1.13]",
    )
    routed = AsyncMock(
        return_value=SimpleNamespace(
            success=True,
            order_id="order-1",
            message="ok",
            error=None,
        )
    )
    monkeypatch.setattr("services.mt5_signal_router.route_signal_to_mt5", routed)
    monkeypatch.setattr(tiered_executor, "_record_execution", AsyncMock())

    result = await tiered_executor.execute_premium_signal(user, signal, AsyncMock())

    assert result["success"] is True
    payload = routed.await_args.args[0]
    assert payload["take_profit"] == [1.12]
    assert routed.await_args.kwargs["execution_mode"] == "auto"


@pytest.mark.asyncio
async def test_vip_execution_does_not_call_adapter_directly(monkeypatch) -> None:
    user = SimpleNamespace(
        id=12,
        telegram_user_id=778,
        tier="VIP",
        metaapi_account_id="account",
    )
    signal = SimpleNamespace(
        signal_id="sig-2",
        asset="BTCUSDT",
        direction="short",
        entry=100.0,
        stop_loss=105.0,
        take_profit="[95, 90, 85]",
    )
    routed = AsyncMock(
        return_value=SimpleNamespace(
            success=False,
            order_id=None,
            message="AUTO_TRADE_DISABLED",
            error="AUTO_TRADE_DISABLED",
        )
    )
    monkeypatch.setattr("services.mt5_signal_router.route_signal_to_mt5", routed)

    result = await tiered_executor.execute_vip_signal(user, signal, AsyncMock(), 10_000)

    assert result["success"] is False
    routed.assert_awaited_once()
    assert routed.await_args.args[0]["take_profit"] == [95.0]
