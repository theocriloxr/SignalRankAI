"""Tests for signal freshness validation."""
import unittest
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.price_validator import (
    is_signal_fresh,
    enrich_signal_with_live_price,
    is_signal_stale,
    filter_stale_signals,
    check_sl_tp_hit,
    get_asset_type,
)


class TestPriceValidator(unittest.TestCase):
    """Test price validation and freshness checks."""
    
    def test_get_asset_type(self):
        """Test asset type detection."""
        self.assertEqual(get_asset_type('BTCUSDT'), 'crypto')
        self.assertEqual(get_asset_type('ETHUSDC'), 'crypto')
        self.assertEqual(get_asset_type('EUR/USD'), 'fx')
        self.assertEqual(get_asset_type('XAUUSD'), 'commodity')
        self.assertEqual(get_asset_type('AAPL'), 'stock')
    
    def test_is_signal_fresh_with_fresh_signal(self):
        """Test freshness check with a fresh signal."""
        signal = {
            'asset': 'BTCUSDT',
            'created_at': datetime.utcnow(),
            'entry': 50000.0,
        }
        is_fresh, reason = is_signal_fresh(signal)
        self.assertTrue(is_fresh)
        self.assertIn('Fresh', reason)
    
    def test_is_signal_fresh_with_stale_signal(self):
        """Test freshness check with a stale signal."""
        signal = {
            'asset': 'BTCUSDT',
            'created_at': datetime.utcnow() - timedelta(minutes=10),
            'entry': 50000.0,
        }
        is_fresh, reason = is_signal_fresh(signal)
        self.assertFalse(is_fresh)
        self.assertIn('exceeds', reason)
    
    def test_is_signal_fresh_with_string_timestamp(self):
        """Test freshness check with string timestamp."""
        signal = {
            'asset': 'BTCUSDT',
            'created_at': datetime.utcnow().isoformat(),
            'entry': 50000.0,
        }
        is_fresh, reason = is_signal_fresh(signal)
        self.assertTrue(is_fresh)
    
    def test_is_signal_fresh_without_timestamp(self):
        """Test freshness check without timestamp."""
        signal = {
            'asset': 'BTCUSDT',
            'entry': 50000.0,
        }
        is_fresh, reason = is_signal_fresh(signal)
        self.assertFalse(is_fresh)
        self.assertIn('No creation timestamp', reason)
    
    @patch('engine.price_validator.get_current_price')
    def test_enrich_signal_with_live_price(self, mock_price):
        """Test signal enrichment with live price."""
        mock_price.return_value = 51000.0
        
        signal = {
            'asset': 'BTCUSDT',
            'created_at': datetime.utcnow(),
            'entry': 50000.0,
            'direction': 'long',
        }
        
        enriched = enrich_signal_with_live_price(signal)
        
        self.assertIn('current_price', enriched)
        self.assertIn('signal_age_seconds', enriched)
        self.assertIn('price_distance_pct', enriched)
        self.assertEqual(enriched['current_price'], 51000.0)
        self.assertIsNotNone(enriched['signal_age_seconds'])
        self.assertAlmostEqual(enriched['price_distance_pct'], 2.0, places=1)
    
    def test_check_sl_tp_hit_long_sl_hit(self):
        """Test SL hit detection for long position."""
        signal = {
            'direction': 'long',
            'entry': 50000.0,
            'stop_loss': 49000.0,
            'take_profit': 52000.0,
        }
        
        should_skip, reason = check_sl_tp_hit(signal, 48500.0)
        self.assertTrue(should_skip)
        self.assertIn('Stop loss already hit', reason)
    
    def test_check_sl_tp_hit_long_tp_hit(self):
        """Test TP hit detection for long position."""
        signal = {
            'direction': 'long',
            'entry': 50000.0,
            'stop_loss': 49000.0,
            'take_profit': '[52000.0]',  # JSON string
        }
        
        should_skip, reason = check_sl_tp_hit(signal, 52500.0)
        self.assertTrue(should_skip)
        self.assertIn('Take profit already hit', reason)
    
    def test_check_sl_tp_hit_short_sl_hit(self):
        """Test SL hit detection for short position."""
        signal = {
            'direction': 'short',
            'entry': 50000.0,
            'stop_loss': 51000.0,
            'take_profit': 48000.0,
        }
        
        should_skip, reason = check_sl_tp_hit(signal, 51500.0)
        self.assertTrue(should_skip)
        self.assertIn('Stop loss already hit', reason)
    
    def test_check_sl_tp_hit_no_hit(self):
        """Test no SL/TP hit."""
        signal = {
            'direction': 'long',
            'entry': 50000.0,
            'stop_loss': 49000.0,
            'take_profit': 52000.0,
        }
        
        should_skip, reason = check_sl_tp_hit(signal, 50500.0)
        self.assertFalse(should_skip)
        self.assertIsNone(reason)
    
    @patch('engine.price_validator.is_signal_fresh')
    def test_is_signal_stale_age_check(self, mock_fresh):
        """Test staleness check based on age."""
        mock_fresh.return_value = (False, "Too old")
        
        signal = {
            'asset': 'BTCUSDT',
            'created_at': datetime.utcnow() - timedelta(hours=2),
            'entry': 50000.0,
        }
        
        is_stale = is_signal_stale(signal)
        self.assertTrue(is_stale)
    
    @patch('engine.price_validator.get_current_price')
    @patch('engine.price_validator.is_signal_fresh')
    def test_filter_stale_signals(self, mock_fresh, mock_price):
        """Test filtering of stale signals from a list."""
        mock_price.return_value = 50000.0
        
        # First signal is fresh
        mock_fresh.side_effect = [
            (True, "Fresh"),   # Signal 1
            (False, "Stale"),  # Signal 2
            (True, "Fresh"),   # Signal 3
        ]
        
        signals = [
            {'asset': 'BTCUSDT', 'created_at': datetime.utcnow(), 'entry': 50000.0, 'signal_id': 'sig1'},
            {'asset': 'ETHUSDT', 'created_at': datetime.utcnow() - timedelta(hours=1), 'entry': 3000.0, 'signal_id': 'sig2'},
            {'asset': 'BNBUSDT', 'created_at': datetime.utcnow(), 'entry': 400.0, 'signal_id': 'sig3'},
        ]
        
        fresh_signals = filter_stale_signals(signals)
        
        # Should only have 2 signals (sig1 and sig3)
        self.assertEqual(len(fresh_signals), 2)
        self.assertEqual(fresh_signals[0]['signal_id'], 'sig1')
        self.assertEqual(fresh_signals[1]['signal_id'], 'sig3')


if __name__ == '__main__':
    unittest.main()
