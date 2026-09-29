#!/usr/bin/env python3
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from core.tier_constants import EXPECTANCY_MIN
from engine.expectancy_gate import (
    clear_expectancy_cache,
    expectancy_gate,
    get_live_expectancy,
    get_live_performance_context,
)


@pytest.fixture(autouse=True)
def _clear_cache(monkeypatch):
    clear_expectancy_cache()
    monkeypatch.setenv("EXPECTANCY_CACHE_SECONDS", "0")
    monkeypatch.setenv("EXPECTANCY_MIN_SAMPLE", "5")
    monkeypatch.setenv("EXPECTANCY_REQUIRE_DELIVERED_PROOF", "1")


def _session_with_row(row):
    mock_session = MagicMock()
    mock_sess = AsyncMock()
    mock_result = MagicMock()
    mock_result.first.return_value = row
    mock_sess.execute.return_value = mock_result
    mock_session.return_value.__aenter__.return_value = mock_sess
    return mock_session, mock_sess


@pytest.mark.asyncio
async def test_live_performance_context_uses_realized_r_not_placeholder_assumptions():
    # n, wins, losses, avg_r, avg_win_r, avg_loss_r, gross_win_r, gross_loss_r
    session, _ = _session_with_row((10, 6, 4, 0.42, 1.40, -0.75, 8.40, -3.00))
    with patch("engine.expectancy_gate.get_session", session):
        context = await get_live_performance_context("BTCUSDT")

    assert context["actionable"] is True
    assert context["sample_size"] == 10
    assert context["win_rate"] == pytest.approx(0.60)
    assert context["expectancy_r"] == pytest.approx(0.42)
    assert context["avg_win_r"] == pytest.approx(1.40)
    assert context["avg_loss_r"] == pytest.approx(0.75)
    assert context["profit_factor"] == pytest.approx(2.8)


@pytest.mark.asyncio
async def test_get_live_expectancy_good():
    session, _ = _session_with_row((10, 7, 3, 0.38, 1.10, -0.80, 7.70, -2.40))
    with patch("engine.expectancy_gate.get_session", session):
        exp = await get_live_expectancy("BTCUSDT")
    assert exp == pytest.approx(0.38)
    assert exp >= EXPECTANCY_MIN


@pytest.mark.asyncio
async def test_get_live_expectancy_bad():
    session, _ = _session_with_row((10, 2, 8, -0.31, 1.20, -0.70, 2.40, -5.60))
    with patch("engine.expectancy_gate.get_session", session):
        exp = await get_live_expectancy("ETHUSDT")
    assert exp == pytest.approx(-0.31)
    assert exp < EXPECTANCY_MIN


@pytest.mark.asyncio
async def test_insufficient_sample_is_non_actionable_instead_of_fabricated():
    session, _ = _session_with_row((2, 2, 0, 1.50, 1.50, None, 3.0, 0.0))
    with patch("engine.expectancy_gate.get_session", session):
        context = await get_live_performance_context("EURUSD")

    assert context["actionable"] is False
    assert context["reason"] == "insufficient_sample"
    assert context["sample_size"] == 2


@pytest.mark.asyncio
async def test_expectancy_gate_passes_when_actionable_evidence_is_positive():
    signal = {
        "asset": "BTCUSDT",
        "strategy_name": "sma_cross",
        "live_expectancy": 0.20,
        "historical_evidence_actionable": True,
    }
    assert await expectancy_gate(signal) is True


@pytest.mark.asyncio
async def test_expectancy_gate_blocks_actionable_negative_evidence():
    signal = {
        "asset": "ETHUSDT",
        "strategy_name": "rsi_div",
        "live_expectancy": 0.10,
        "historical_evidence_actionable": True,
    }
    assert await expectancy_gate(signal) is False


def test_expectancy_query_uses_canonical_strategy_and_delivery_proof():
    from pathlib import Path

    source = Path("engine/expectancy_gate.py").read_text(encoding="utf-8")
    assert "Signal.strategy_name == strategy_key" in source
    assert "Signal.strategy ==" not in source
    assert "SignalOutcome.r_multiple" in source
    assert "SignalDelivery.sent_ok.is_(True)" in source
    assert "avg_win_r = 1.8" not in source
    assert "avg_loss_r = 0.8" not in source
