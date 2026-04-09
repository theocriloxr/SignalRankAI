import os
import unittest
from datetime import timedelta
from unittest.mock import patch


class TestMonolithHardeningDefaults(unittest.TestCase):
    def test_signal_dedup_window_is_one_hour(self):
        from engine.signal_deduplicator import SignalDeduplicator

        d = SignalDeduplicator()
        self.assertEqual(d._cache_ttl, timedelta(hours=1))

    def test_outcome_tracker_default_interval_is_20s(self):
        from engine import realtime_outcome_tracker as rot

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("OUTCOME_CHECK_INTERVAL_SECONDS", None)
            self.assertEqual(rot._check_interval(), 20)

    def test_run_startup_ops_auto_migrate_default_is_disabled(self):
        from db import auto_ops

        with patch("db.auto_ops._sync_database_url", return_value="postgresql://u:p@localhost:5432/db"), \
             patch.dict(os.environ, {}, clear=False), \
             patch("db.auto_ops.time.sleep") as _sleep:
            os.environ.pop("AUTO_MIGRATE", None)
            # Should return early without retries when AUTO_MIGRATE is unset.
            auto_ops.run_startup_ops("all")
            self.assertFalse(_sleep.called)

    def test_db_engine_singleton_per_process(self):
        import db.session as dbs

        dbs._engines_by_loop.clear()
        dbs._sessionmakers_by_loop.clear()
        fake_engine = object()
        with patch("db.session.get_database_url", return_value="postgresql+asyncpg://u:p@localhost:5432/db"), \
             patch("db.session.create_async_engine", return_value=fake_engine):
            e1 = dbs.get_engine_for_event_loop()
            e2 = dbs.get_engine_for_event_loop()
            self.assertIs(e1, e2)


if __name__ == "__main__":
    unittest.main()

