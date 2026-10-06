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


@pytest.mark.asyncio
async def test_raw_model_confidence_is_not_historical_win_rate() -> None:
    assert await DynamicSizer().calculate_size(user_id=1,
        signal={"entry": 100, "stop_loss": 95, "direction": "long"},
        ml_probability=0.99, balance=10_000) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("win_rate", [0.0, 0.1, 0.4])
async def test_no_positive_empirical_edge_blocks_risk(win_rate) -> None:
    assert await DynamicSizer().calculate_size(user_id=1,
        signal={"entry": 100, "stop_loss": 95, "direction": "long"},
        ml_probability=0.99, win_rate=win_rate, avg_rr=1.5, balance=10_000) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("field,value", [("balance", float("nan")), ("balance", float("inf")),
    ("win_rate", True), ("win_rate", float("nan")), ("avg_rr", float("inf")),
    ("entry", "invalid"), ("entry", float("nan")), ("stop_loss", float("inf"))])
async def test_invalid_sizing_data_never_creates_nonfinite_units(field, value) -> None:
    inputs = {"balance": 10_000, "win_rate": 0.8, "avg_rr": 2.0}
    signal = {"entry": 100, "stop_loss": 95, "direction": "long"}
    (signal if field in signal else inputs)[field] = value
    assert await DynamicSizer().calculate_size(user_id=1, signal=signal, **inputs) == 0


@pytest.mark.asyncio
async def test_sizing_details_report_actual_kelly_capped_risk(monkeypatch) -> None:
    from core import paper_ledger
    from types import SimpleNamespace
    from unittest.mock import AsyncMock
    monkeypatch.setattr(paper_ledger, "get_paper_ledger", lambda: SimpleNamespace(get_balance=AsyncMock(return_value=10_000)))
    # Positive but small empirical edge caps risk below the probability table.
    report = await DynamicSizer().calculate_size_info(user_id=1,
        signal={"entry": 100, "stop_loss": 95, "direction": "long"},
        ml_probability=0.99, win_rate=0.405, avg_rr=1.5)
    assert report["risk_amount"] == pytest.approx(report["size"] * 5)
    assert report["risk_pct"] == pytest.approx(report["kelly_risk_pct"])
    assert report["probability"] == 0.405 and report["instrument_sizing_certified"] is False
