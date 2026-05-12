#!/usr/bin/env python3
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta

import sys
sys.path.insert(0, '..')
from engine.risk import (
    calculate_dynamic_risk,
    risk_check,
    calculate_position_size,
    soft_throttle_active,
    hard_stop_active,
    get_max_volatility
)
from core.tier_constants import EXPECTANCY_MIN, DD_SOFT_THROTTLE, DD_HARD_LIMIT

@pytest.fixture
def sample_signal():
    return {
        'asset': 'BTCUSDT',
        'direction': 'long',
        'entry': 50000.0,
        'stop_loss': 49000.0,
        'take_profit': 55000.0,
        'atr_rel': 0.05,
        'ml_probability': 0.7,
        'timeframe_minutes': 60,
        'live_expectancy': 0.20,
        'volatility': 0.04,
    }

@pytest.fixture
def account_state_normal():
    return MagicMock(drawdown=0.03)  # < soft

@pytest.fixture
def account_state_soft():
    return MagicMock(drawdown=0.08)  # > soft

@pytest.fixture
def account_state_hard():
    return MagicMock(drawdown=0.15)  # > hard

def test_calculate_position_size(sample_signal):
    balance = 100000.0
    size = calculate_position_size(sample_signal, balance, risk_pct=1.0)
    assert size is not None
    assert size > 0
    risk_dist = abs(sample_signal['entry'] - sample_signal['stop_loss'])
    expected = (balance * 0.01) / risk_dist
    assert abs(size - expected) < 0.01

def test_soft_throttle_active(account_state_soft):
    assert soft_throttle_active(account_state_soft) == True

def test_hard_stop_active(account_state_hard):
    assert hard_stop_active(account_state_hard) == True

def test_get_max_volatility():
    assert get_max_volatility('crypto') <= 0.12

def test_risk_check_good(sample_signal, account_state_normal):
    sample_signal['live_expectancy'] = 0.20  # > EXPECTANCY_MIN
    assert risk_check(sample_signal, account_state_normal) == True

def test_risk_check_low_expectancy(sample_signal, account_state_normal):
    sample_signal['live_expectancy'] = 0.10  # < EXPECTANCY_MIN
    assert risk_check(sample_signal, account_state_normal) == True


def test_risk_check_low_expectancy_hard_block(monkeypatch, sample_signal, account_state_normal):
    monkeypatch.setenv("EXPECTANCY_HARD_BLOCK_ENABLED", "1")
    sample_signal['live_expectancy'] = 0.10  # < EXPECTANCY_MIN
    assert risk_check(sample_signal, account_state_normal) == False

def test_risk_check_high_vol(sample_signal, account_state_normal):
    # atr_rel is read before volatility in the or-chain, so set the field
    # that risk_check actually evaluates first.
    sample_signal['atr_rel'] = 0.15  # high vol -> above MAX_SIGNAL_VOLATILITY default 0.12
    assert risk_check(sample_signal, account_state_normal) == False

def test_calculate_dynamic_risk(sample_signal):
    profile = calculate_dynamic_risk(sample_signal)
    assert 'risk_pct' in profile
    assert 0.1 <= profile['risk_pct'] <= 2.0

def test_position_size_bounds(sample_signal):
    balance = 10000.0
    size = calculate_position_size(sample_signal, balance)
    assert 0.01 <= size <= balance * 0.1  # min/max bounds

