#!/usr/bin/env python3
"""
Manual test script to demonstrate signal freshness validation.
Run this to see freshness checks in action.
"""

import sys
import os
from datetime import datetime, timedelta, timezone

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.price_validator import (
    is_signal_fresh,
    enrich_signal_with_live_price,
    is_signal_stale,
    filter_stale_signals,
)


def _utcnow_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def test_freshness_validation():
    """Test signal freshness validation with various scenarios."""
    
    print("=" * 80)
    print("Signal Freshness Validation - Manual Test")
    print("=" * 80)
    print()
    
    # Test 1: Fresh crypto signal
    print("Test 1: Fresh crypto signal (1 minute old)")
    print("-" * 40)
    fresh_signal = {
        'signal_id': 'sig_001',
        'asset': 'BTCUSDT',
        'created_at': _utcnow_naive() - timedelta(minutes=1),
        'entry': 50000.0,
        'direction': 'long',
        'take_profit': '[52000.0]',
        'stop_loss': 49000.0,
    }
    
    is_fresh, reason = is_signal_fresh(fresh_signal)
    print(f"  Fresh? {is_fresh}")
    print(f"  Reason: {reason}")
    print(f"  Stale? {is_signal_stale(fresh_signal)}")
    print()
    
    # Test 2: Stale crypto signal
    print("Test 2: Stale crypto signal (10 minutes old)")
    print("-" * 40)
    stale_signal = {
        'signal_id': 'sig_002',
        'asset': 'ETHUSDT',
        'created_at': _utcnow_naive() - timedelta(minutes=10),
        'entry': 3000.0,
        'direction': 'long',
        'take_profit': '[3100.0]',
        'stop_loss': 2950.0,
    }
    
    is_fresh, reason = is_signal_fresh(stale_signal)
    print(f"  Fresh? {is_fresh}")
    print(f"  Reason: {reason}")
    print(f"  Stale? {is_signal_stale(stale_signal)}")
    print()
    
    # Test 3: Fresh FX signal
    print("Test 3: Fresh FX signal (2 minutes old)")
    print("-" * 40)
    fx_signal = {
        'signal_id': 'sig_003',
        'asset': 'EUR/USD',
        'created_at': _utcnow_naive() - timedelta(minutes=2),
        'entry': 1.0850,
        'direction': 'long',
        'take_profit': '[1.0900]',
        'stop_loss': 1.0820,
    }
    
    is_fresh, reason = is_signal_fresh(fx_signal)
    print(f"  Fresh? {is_fresh}")
    print(f"  Reason: {reason}")
    print(f"  Stale? {is_signal_stale(fx_signal)}")
    print()
    
    # Test 4: Filter stale signals from a list
    print("Test 4: Filter stale signals from list")
    print("-" * 40)
    signals = [
        {
            'signal_id': 'sig_004',
            'asset': 'BTCUSDT',
            'created_at': _utcnow_naive() - timedelta(seconds=30),
            'entry': 50000.0,
        },
        {
            'signal_id': 'sig_005',
            'asset': 'ETHUSDT',
            'created_at': _utcnow_naive() - timedelta(minutes=15),
            'entry': 3000.0,
        },
        {
            'signal_id': 'sig_006',
            'asset': 'BNBUSDT',
            'created_at': _utcnow_naive() - timedelta(minutes=1),
            'entry': 400.0,
        },
    ]
    
    print(f"  Total signals: {len(signals)}")
    fresh_signals = filter_stale_signals(signals)
    print(f"  Fresh signals after filtering: {len(fresh_signals)}")
    print(f"  Fresh signal IDs: {[s['signal_id'] for s in fresh_signals]}")
    print()
    
    # Test 5: Signal enrichment
    print("Test 5: Signal enrichment with live price")
    print("-" * 40)
    print("  Note: This requires actual market data fetch, which may fail")
    test_signal = {
        'signal_id': 'sig_007',
        'asset': 'BTCUSDT',
        'created_at': _utcnow_naive(),
        'entry': 50000.0,
        'direction': 'long',
    }
    
    try:
        enriched = enrich_signal_with_live_price(test_signal)
        print(f"  Original signal keys: {list(test_signal.keys())}")
        print(f"  Enriched signal keys: {list(enriched.keys())}")
        print(f"  Signal age (seconds): {enriched.get('signal_age_seconds')}")
        print(f"  Current price: {enriched.get('current_price')}")
        print(f"  Price distance %: {enriched.get('price_distance_pct')}")
    except Exception as e:
        print(f"  Enrichment failed (expected in offline mode): {e}")
    print()
    
    print("=" * 80)
    print("Tests completed successfully!")
    print("=" * 80)


if __name__ == '__main__':
    test_freshness_validation()
