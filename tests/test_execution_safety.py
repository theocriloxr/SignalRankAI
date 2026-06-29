import unittest


class TestExecutionSafety(unittest.IsolatedAsyncioTestCase):
    def test_mt5_router_rejects_missing_hard_stop(self):
        from services.mt5_signal_router import MT5SignalRouter

        valid, reason = MT5SignalRouter._validate_signal(
            {
                "asset": "BTCUSDT",
                "direction": "long",
                "entry": 100.0,
                "take_profit": 110.0,
            }
        )
        self.assertFalse(valid)
        self.assertIn("stop_loss", reason)

    def test_mt5_router_rejects_invalid_short_stop_direction(self):
        from services.mt5_signal_router import MT5SignalRouter

        valid, reason = MT5SignalRouter._validate_signal(
            {
                "asset": "BTCUSDT",
                "direction": "short",
                "entry": 100.0,
                "stop_loss": 95.0,
                "take_profit": 90.0,
            }
        )
        self.assertFalse(valid)
        self.assertIn("short stop_loss", reason)

    async def test_copy_alias_routes_to_live_execution_in_both_mode(self):
        from services.trading_mode_manager import TradingModeManager, TRADING_MODE_BOTH

        mgr = TradingModeManager()

        async def _get_mode(_user_id):
            return TRADING_MODE_BOTH

        async def _get_execution_mode(_user_id):
            return "copy"

        mgr.get_mode = _get_mode
        mgr.get_execution_mode = _get_execution_mode
        seen = {}

        async def _execute_live(_signal, _user_id, execution_mode):
            seen["execution_mode"] = execution_mode
            return {"success": True, "destination": "mt5"}

        mgr._execute_live = _execute_live
        result = await mgr.execute_signal({"signal_id": "s1"}, 123)

        self.assertTrue(result["success"])
        self.assertEqual(result["destination"], "mt5")
        self.assertEqual(seen["execution_mode"], "copy_trade")

    async def test_signals_only_never_executes_paper_or_live(self):
        from services.trading_mode_manager import TradingModeManager, TRADING_MODE_LIVE

        mgr = TradingModeManager()

        async def _get_mode(_user_id):
            return TRADING_MODE_LIVE

        async def _get_execution_mode(_user_id):
            return "signals_only"

        mgr.get_mode = _get_mode
        mgr.get_execution_mode = _get_execution_mode

        result = await mgr.execute_signal({"signal_id": "s2"}, 123)

        self.assertTrue(result["success"])
        self.assertEqual(result["destination"], "signals")


if __name__ == "__main__":
    unittest.main()
