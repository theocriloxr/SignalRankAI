import unittest
import os
from engine.signal_controller import SignalController
from db.pg_compat import postgres_enabled
from signalrank_telegram.access import resolve_user_tier

class TestSignalController(unittest.TestCase):
    def setUp(self):
        self.controller = SignalController()

    def test_kill_switch(self):
        self.controller.enable_kill_switch("test", admin_id=1)
        self.assertTrue(self.controller.is_kill_switch_enabled())
        self.controller.disable_kill_switch(admin_id=1)
        self.assertFalse(self.controller.is_kill_switch_enabled())

    def test_approve_signals_empty(self):
        # Should return [] if kill switch is enabled
        self.controller.enable_kill_switch("test", admin_id=1)
        result = self.controller.approve_signals([], None)
        self.assertEqual(result, [])
        self.controller.disable_kill_switch(admin_id=1)

    def test_deduplicate_signals(self):
        signals = [
            {'asset': 'BTC', 'direction': 'LONG', 'timeframe': '1h'},
            {'asset': 'BTC', 'direction': 'LONG', 'timeframe': '1h'},
            {'asset': 'ETH', 'direction': 'SHORT', 'timeframe': '1h'}
        ]
        deduped = self.controller.deduplicate_signals(signals)
        self.assertEqual(len(deduped), 2)

class TestUserTier(unittest.TestCase):
    def test_set_and_get_tier(self):
        # Postgres-only: without DATABASE_URL configured in local tests,
        # tier resolution should default safely to FREE for reliability.
        user_id = 999999
        if postgres_enabled():
            tier = resolve_user_tier(user_id)
            self.assertIn(tier, {"FREE", "PREMIUM", "VIP", "OWNER"})
        else:
            # When Postgres isn't configured, resolve_user_tier gracefully returns "FREE"
            # This ensures the bot continues to function without database access.
            tier = resolve_user_tier(user_id)
            self.assertEqual(tier, "FREE")

if __name__ == "__main__":
    unittest.main()
