from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from services.mt5_signal_router import ExecutionRequest, ExecutionResult, MT5SignalRouter


def _request() -> ExecutionRequest:
    return ExecutionRequest(
        signal_id="sig-queue",
        user_id=7,
        asset="BTCUSDT",
        direction="long",
        entry=100.0,
        stop_loss=95.0,
        take_profit=[110.0],
        volume=0.2,
        execution_mode="auto",
        tier="VIP",
        created_at=datetime.now(timezone.utc),
    )


@pytest.mark.asyncio
async def test_bounded_queue_routes_through_canonical_path(monkeypatch) -> None:
    router = MT5SignalRouter(execution_gate=object())
    route = AsyncMock(
        return_value=ExecutionResult(success=True, message="ok", order_id="order-1")
    )
    monkeypatch.setattr(router, "route_signal", route)

    result = await router.enqueue_execution(_request())
    await router.shutdown()

    assert result.success is True
    route.assert_awaited_once()
    signal, user_id, mode = route.await_args.args
    assert signal["signal_id"] == "sig-queue"
    assert signal["requested_volume"] == 0.2
    assert user_id == 7
    assert mode == "auto"


@pytest.mark.asyncio
async def test_shutdown_releases_worker_without_background_task_leak() -> None:
    router = MT5SignalRouter(execution_gate=object())
    await router.initialize()
    assert router._worker_task is not None
    await router.shutdown()
    assert router._worker_task is None
    assert router._processing is False
