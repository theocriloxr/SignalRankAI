from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from engine.smart_dca import SmartDCA


class MemoryState:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    async def cache_get(self, key: str):
        return self.values.get(key)

    async def cache_set(self, key: str, value: str, ex=None):
        self.values[key] = value


def _signal() -> SimpleNamespace:
    return SimpleNamespace(
        signal_id="sig-dca",
        asset="BTCUSDT",
        direction="long",
        entry=100.0,
        stop_loss=90.0,
        take_profit="[120, 130, 140]",
    )


@pytest.mark.asyncio
async def test_dca_is_default_off(monkeypatch) -> None:
    monkeypatch.delenv("SMART_DCA_ENABLED", raising=False)
    manager = SmartDCA(redis_state=MemoryState())
    allowed, reason = await manager.should_dca(
        "sig-dca", 7, 96.0, signal=_signal()
    )
    assert allowed is False
    assert reason == "smart_dca_disabled"


@pytest.mark.asyncio
async def test_dca_progresses_dca1_then_dca2(monkeypatch) -> None:
    monkeypatch.setenv("SMART_DCA_ENABLED", "1")
    memory = MemoryState()
    manager = SmartDCA("balanced", redis_state=memory)
    sig = _signal()

    allowed, level = await manager.should_dca("sig-dca", 7, 96.0, signal=sig)
    assert (allowed, level) == (True, "dca1")

    await manager._save_state(7, "sig-dca", {"dca1_done": True})
    allowed, level = await manager.should_dca("sig-dca", 7, 93.0, signal=sig)
    assert (allowed, level) == (True, "dca2")

    await manager._save_state(7, "sig-dca", {"dca1_done": True, "dca2_done": True})
    allowed, level = await manager.should_dca("sig-dca", 7, 92.0, signal=sig)
    assert (allowed, level) == (False, "dca_complete")


@pytest.mark.asyncio
async def test_dca_never_averages_after_stop(monkeypatch) -> None:
    monkeypatch.setenv("SMART_DCA_ENABLED", "1")
    manager = SmartDCA(redis_state=MemoryState())
    allowed, reason = await manager.should_dca(
        "sig-dca", 7, 89.0, signal=_signal()
    )
    assert allowed is False
    assert reason == "stop_already_crossed"


@pytest.mark.asyncio
async def test_dca_routes_through_canonical_gate_with_original_delivery_evidence(
    monkeypatch,
) -> None:
    monkeypatch.setenv("SMART_DCA_ENABLED", "1")
    memory = MemoryState()
    manager = SmartDCA("balanced", redis_state=memory)
    route = AsyncMock(
        return_value=SimpleNamespace(success=True, order_id="order-dca", error=None)
    )
    monkeypatch.setattr("services.mt5_signal_router.route_signal_to_mt5", route)

    ok = await manager.execute_dca(
        "sig-dca", 7, "dca1", 96.0, signal=_signal()
    )

    assert ok is True
    routed, user_id = route.await_args.args[:2]
    assert routed["signal_id"] == "sig-dca:dca1:7"
    assert routed["evidence_signal_id"] == "sig-dca"
    assert routed["position_weight"] == 0.33
    assert user_id == 7
    assert route.await_args.kwargs["execution_mode"] == "auto"
    saved = await manager._load_state(7, "sig-dca")
    assert saved["dca1_done"] is True
    assert saved["dca2_done"] is False


def test_position_weight_rounds_down_and_never_raises_to_minimum() -> None:
    from services.mt5_signal_router import MT5SignalRouter

    spec = {"volume_step": 0.1, "min_volume": 0.1, "max_volume": 10.0}
    assert MT5SignalRouter._apply_position_weight(1.0, 0.33, spec) == 0.3
    assert MT5SignalRouter._apply_position_weight(0.1, 0.33, spec) == 0.0
    assert MT5SignalRouter._apply_position_weight(1.0, 1.5, spec) == 0.0
