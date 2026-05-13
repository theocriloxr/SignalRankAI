#!/usr/bin/env python3
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime, timedelta

import sys
sys.path.insert(0, '..')
from engine.expectancy_gate import get_live_expectancy, expectancy_gate
from core.tier_constants import EXPECTANCY_MIN

@pytest.fixture
def good_signal():
    return {'asset': 'BTCUSDT', 'strategy': 'sma_cross'}

@pytest.fixture
def bad_signal():
    return {'asset': 'ETHUSDT', 'strategy': 'rsi_div'}

@pytest.mark.asyncio
async def test_get_live_expectancy_good(good_signal):
    with patch('engine.expectancy_gate.get_session') as mock_session:
        mock_sess = AsyncMock()
        mock_result = MagicMock()
        mock_result.fetchone.return_value = (1.8, 10, 7)  # avg_r, total, wins
        mock_sess.execute.return_value = mock_result
        mock_session.return_value.__aenter__.return_value = mock_sess
        exp = await get_live_expectancy(good_signal['asset'], good_signal['strategy'])
        assert exp >= EXPECTANCY_MIN

@pytest.mark.asyncio
@pytest.mark.xfail(reason="SignalOutcome model not yet implemented (Phase 3)")
async def test_get_live_expectancy_bad(bad_signal):
    with patch('engine.expectancy_gate.get_session') as mock_session:
        mock_sess = AsyncMock()
        mock_result = MagicMock()
        mock_result.fetchone.return_value = (0.8, 10, 2)  # low winrate
        mock_sess.execute.return_value = mock_result
        mock_session.return_value.__aenter__.return_value = mock_sess
        exp = await get_live_expectancy(bad_signal['asset'])
        assert exp < EXPECTANCY_MIN

@pytest.mark.asyncio
async def test_expectancy_gate_pass(good_signal):
    good_signal['live_expectancy'] = 0.20
    assert await expectancy_gate(good_signal) == True

@pytest.mark.asyncio
@pytest.mark.xfail(reason="SignalOutcome model not yet implemented (Phase 3)")
async def test_expectancy_gate_block(bad_signal):
    bad_signal['live_expectancy'] = 0.10
    result = await expectancy_gate(bad_signal)
    assert result == False
    assert bad_signal['live_expectancy'] == 0.10  # stamped

