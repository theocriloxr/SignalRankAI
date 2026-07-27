from __future__ import annotations

import pytest

from services.dynamic_sizing import DynamicSizer


@pytest.mark.asyncio
async def test_zero_equity_does_not_fall_back_to_paper_balance(monkeypatch) -> None:
    sizer = DynamicSizer()
    size = await sizer.calculate_size(
        user_id=1,
        signal={"entry": 100, "stop_loss": 95, "direction": "long"},
        ml_probability=0.8,
        balance=0.0,
    )
    assert size == 0.0


@pytest.mark.asyncio
async def test_invalid_geometry_returns_zero_not_assumed_one_percent_move() -> None:
    sizer = DynamicSizer()
    assert await sizer.calculate_size(
        user_id=1,
        signal={"entry": 100, "stop_loss": 105, "direction": "long"},
        ml_probability=0.8,
        balance=10_000,
    ) == 0.0


@pytest.mark.asyncio
async def test_valid_sizing_uses_real_balance_and_stop_distance() -> None:
    sizer = DynamicSizer()
    size = await sizer.calculate_size(
        user_id=1,
        signal={"entry": 100, "stop_loss": 95, "direction": "long"},
        ml_probability=0.8,
        win_rate=0.8,
        avg_rr=2.0,
        balance=10_000,
    )
    assert size > 0
    assert size == pytest.approx(60.0)
