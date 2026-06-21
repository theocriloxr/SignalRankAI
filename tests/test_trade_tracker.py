import unittest
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone
import os

from core.trade_tracker import (
    TradeRecord,
    add_trade,
    _PRICE_FAILURE_STATE,
    price_hit_tp,
    price_hit_sl,
    update_trade_outcomes,
    open_trades_list,
    open_trades,
)


def _utcnow_naive_iso() -> str:
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat()


class TestTradeTracker(unittest.TestCase):
    def setUp(self):
        """Clear open trades before each test."""
        open_trades_list.clear()
        _PRICE_FAILURE_STATE.clear()

    def test_trade_record_creation_basic(self):
        """Test basic trade record creation."""
        signal = {
            "id": "sig_123",
            "symbol": "BTCUSDT",
            "direction": "long",
            "entry": 50000.0,
            "stop_loss": 49000.0,
            "take_profit": 52000.0,
            "timestamp": _utcnow_naive_iso(),
        }
        trade = TradeRecord(signal)

        self.assertEqual(trade.signal_id, "sig_123")
        self.assertEqual(trade.symbol, "BTCUSDT")
        self.assertEqual(trade.direction, "long")
        self.assertEqual(trade.entry, 50000.0)
        self.assertEqual(trade.stop, 49000.0)
        self.assertEqual(trade.targets, [52000.0])

    def test_trade_record_creation_multiple_targets(self):
        """Test trade record with multiple TP targets."""
        signal = {
            "signal_id": "sig_456",
            "asset": "ETHUSDT",
            "direction": "short",
            "entry": 3000.0,
            "stop": 3100.0,
            "targets": [2950.0, 2900.0, 2850.0],
            "timestamp": _utcnow_naive_iso(),
        }
        trade = TradeRecord(signal)

        self.assertEqual(trade.signal_id, "sig_456")
        self.assertEqual(trade.symbol, "ETHUSDT")
        self.assertEqual(trade.direction, "short")
        self.assertEqual(len(trade.targets), 3)
        self.assertEqual(trade.targets, [2950.0, 2900.0, 2850.0])

    def test_add_trade(self):
        """Test adding a trade to the tracker."""
        signal = {
            "id": "sig_789",
            "symbol": "BTCUSDT",
            "direction": "long",
            "entry": 50000.0,
            "stop_loss": 49000.0,
            "take_profit": 52000.0,
            "timestamp": _utcnow_naive_iso(),
        }
        
        trade = add_trade(signal)
        
        self.assertEqual(len(open_trades_list), 1)
        self.assertEqual(open_trades_list[0].signal_id, "sig_789")

    def test_add_trade_deduplicates_signal_id(self):
        """Duplicate signal IDs should not create duplicate open trades."""
        signal = {
            "id": "sig_dup",
            "symbol": "BTCUSDT",
            "direction": "long",
            "entry": 50000.0,
            "stop_loss": 49000.0,
            "take_profit": 52000.0,
            "timestamp": _utcnow_naive_iso(),
        }

        first = add_trade(signal)
        second = add_trade(dict(signal))

        self.assertIs(first, second)
        self.assertEqual(len(open_trades_list), 1)

    @patch.dict(os.environ, {"REDIS_URL": "redis://example"}, clear=False)
    @patch("core.trade_tracker.state.set_active_trade_sync", return_value=None)
    @patch("core.trade_tracker.state.get_active_trades_sync", return_value={})
    def test_open_trades_clears_stale_cache_when_state_empty(self, mock_state, mock_set_state):
        signal = {
            "id": "sig_stale",
            "symbol": "BTCUSDT",
            "direction": "long",
            "entry": 50000.0,
            "stop_loss": 49000.0,
            "take_profit": 52000.0,
            "timestamp": _utcnow_naive_iso(),
        }
        add_trade(signal)

        self.assertEqual(len(open_trades_list), 1)
        self.assertEqual(open_trades(), [])
        self.assertEqual(len(open_trades_list), 0)

    @patch('core.trade_tracker._get_current_price')
    def test_price_hit_tp_long(self, mock_price):
        """Test TP hit detection for long position."""
        signal = {
            "id": "sig_001",
            "symbol": "BTCUSDT",
            "direction": "long",
            "entry": 50000.0,
            "stop_loss": 49000.0,
            "take_profit": 52000.0,
            "timestamp": _utcnow_naive_iso(),
        }
        trade = TradeRecord(signal)

        # Price below target
        mock_price.return_value = 51000.0
        self.assertFalse(price_hit_tp(trade))

        # Price hits target
        mock_price.return_value = 52000.0
        self.assertTrue(price_hit_tp(trade))
        self.assertIn(52000.0, trade.targets_hit)

    @patch('core.trade_tracker._get_current_price')
    def test_price_hit_tp_short(self, mock_price):
        """Test TP hit detection for short position."""
        signal = {
            "id": "sig_002",
            "symbol": "ETHUSDT",
            "direction": "short",
            "entry": 3000.0,
            "stop": 3100.0,
            "targets": [2950.0, 2900.0],
            "timestamp": _utcnow_naive_iso(),
        }
        trade = TradeRecord(signal)

        # Price above first target
        mock_price.return_value = 2970.0
        self.assertFalse(price_hit_tp(trade))

        # Price hits first target
        mock_price.return_value = 2950.0
        self.assertTrue(price_hit_tp(trade))
        self.assertEqual(len(trade.targets_hit), 1)

        # Price hits second target
        mock_price.return_value = 2900.0
        self.assertTrue(price_hit_tp(trade))
        self.assertEqual(len(trade.targets_hit), 2)

    @patch('core.trade_tracker._get_current_price')
    def test_price_hit_sl_long(self, mock_price):
        """Test SL hit detection for long position."""
        signal = {
            "id": "sig_003",
            "symbol": "BTCUSDT",
            "direction": "long",
            "entry": 50000.0,
            "stop_loss": 49000.0,
            "take_profit": 52000.0,
            "timestamp": _utcnow_naive_iso(),
        }
        trade = TradeRecord(signal)

        # Price above stop
        mock_price.return_value = 49500.0
        self.assertFalse(price_hit_sl(trade))

        # Price hits stop
        mock_price.return_value = 49000.0
        self.assertTrue(price_hit_sl(trade))

        # Price below stop
        mock_price.return_value = 48500.0
        self.assertTrue(price_hit_sl(trade))

    @patch('core.trade_tracker._get_current_price')
    def test_price_hit_sl_short(self, mock_price):
        """Test SL hit detection for short position."""
        signal = {
            "id": "sig_004",
            "symbol": "ETHUSDT",
            "direction": "short",
            "entry": 3000.0,
            "stop": 3100.0,
            "targets": [2950.0],
            "timestamp": _utcnow_naive_iso(),
        }
        trade = TradeRecord(signal)

        # Price below stop
        mock_price.return_value = 3050.0
        self.assertFalse(price_hit_sl(trade))

        # Price hits stop
        mock_price.return_value = 3100.0
        self.assertTrue(price_hit_sl(trade))

    @patch('core.trade_tracker._get_current_price')
    def test_update_trade_outcomes_tp(self, mock_price):
        """Test updating trade outcomes when TP is hit."""
        signal = {
            "id": "sig_005",
            "symbol": "BTCUSDT",
            "direction": "long",
            "entry": 50000.0,
            "stop_loss": 49000.0,
            "take_profit": 52000.0,
            "timestamp": _utcnow_naive_iso(),
        }
        add_trade(signal)

        # Price hits TP
        mock_price.return_value = 52000.0
        closed = update_trade_outcomes()

        self.assertEqual(len(closed), 1)
        self.assertEqual(closed[0].outcome, "TP")
        self.assertEqual(len(open_trades_list), 0)

    @patch('core.trade_tracker._get_current_price')
    def test_update_trade_outcomes_sl(self, mock_price):
        """Test updating trade outcomes when SL is hit."""
        signal = {
            "id": "sig_006",
            "symbol": "BTCUSDT",
            "direction": "long",
            "entry": 50000.0,
            "stop_loss": 49000.0,
            "take_profit": 52000.0,
            "timestamp": _utcnow_naive_iso(),
        }
        add_trade(signal)

        # Price hits SL
        mock_price.return_value = 48500.0
        closed = update_trade_outcomes()

        self.assertEqual(len(closed), 1)
        self.assertEqual(closed[0].outcome, "SL")
        self.assertEqual(len(open_trades_list), 0)

    @patch('core.trade_tracker._get_current_price')
    def test_update_trade_outcomes_partial_tp(self, mock_price):
        """Test partial TP outcome."""
        signal = {
            "id": "sig_007",
            "symbol": "BTCUSDT",
            "direction": "long",
            "entry": 50000.0,
            "stop_loss": 49000.0,
            "targets": [51000.0, 52000.0, 53000.0],
            "timestamp": _utcnow_naive_iso(),
        }
        add_trade(signal)

        # Price hits first target
        mock_price.return_value = 51000.0
        closed = update_trade_outcomes()

        # Trade should be closed with PARTIAL_TP
        self.assertEqual(len(closed), 1)
        self.assertEqual(closed[0].outcome, "PARTIAL_TP")
        self.assertEqual(len(closed[0].targets_hit), 1)

    @patch('core.trade_tracker._get_current_price')
    def test_update_trade_outcomes_no_hit(self, mock_price):
        """Test no trades closed when price hasn't hit TP or SL."""
        signal = {
            "id": "sig_008",
            "symbol": "BTCUSDT",
            "direction": "long",
            "entry": 50000.0,
            "stop_loss": 49000.0,
            "take_profit": 52000.0,
            "timestamp": _utcnow_naive_iso(),
        }
        add_trade(signal)

        # Price between entry and targets
        mock_price.return_value = 50500.0
        closed = update_trade_outcomes()

        self.assertEqual(len(closed), 0)
        self.assertEqual(len(open_trades_list), 1)

    @patch('core.trade_tracker._market_closed_reason')
    @patch('core.trade_tracker.yf.Ticker')
    def test_get_current_price_skips_when_market_closed(self, mock_ticker, mock_market_closed):
        from core.trade_tracker import _get_current_price

        mock_market_closed.return_value = "US stock market closed (holiday: 2026-05-27)"

        price = _get_current_price("GOOGL")

        self.assertIsNone(price)
        mock_ticker.assert_not_called()

    @patch('core.trade_tracker.yf.Ticker')
    @patch('core.trade_tracker.requests.get')
    def test_get_current_price_backoff_after_failure(self, mock_get, mock_ticker):
        from core.trade_tracker import _get_current_price

        mock_ticker.side_effect = RuntimeError("yfinance unavailable")
        mock_get.side_effect = RuntimeError("binance unavailable")

        first = _get_current_price("BTCUSDT")
        second = _get_current_price("BTCUSDT")

        self.assertIsNone(first)
        self.assertIsNone(second)
        self.assertEqual(mock_ticker.call_count, 1)
        self.assertEqual(mock_get.call_count, 1)

    def test_price_hit_tp_uses_batched_market_data(self):
        signal = {
            "id": "sig_batch",
            "symbol": "BTCUSDT",
            "direction": "long",
            "entry": 50000.0,
            "stop_loss": 49000.0,
            "take_profit": 52000.0,
            "timestamp": _utcnow_naive_iso(),
        }
        trade = TradeRecord(signal)

        with patch('core.trade_tracker._get_current_price', side_effect=AssertionError("should not fetch live price")):
            self.assertTrue(price_hit_tp(trade, market_data={"BTCUSDT": 52000.0}))


if __name__ == '__main__':
    unittest.main()
