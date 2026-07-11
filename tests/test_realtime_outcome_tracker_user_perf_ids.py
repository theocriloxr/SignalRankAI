import unittest
from unittest.mock import AsyncMock, patch
import time


class _Rows:
    def __init__(self, rows):
        self._rows = list(rows)

    def all(self):
        return list(self._rows)


class _Session:
    def __init__(self, rows):
        self._rows = list(rows)

    async def execute(self, _stmt):
        return _Rows(self._rows)


class _SessionCM:
    def __init__(self, rows):
        self._rows = list(rows)

    async def __aenter__(self):
        return _Session(self._rows)

    async def __aexit__(self, exc_type, exc, tb):
        return False


class TestRealtimeOutcomeTrackerPerformanceIds(unittest.IsolatedAsyncioTestCase):
    async def test_check_all_updates_performance_by_telegram_user_id(self):
        from engine.realtime_outcome_tracker import RealtimeOutcomeTracker

        tracker = RealtimeOutcomeTracker()
        tracker._last_retrain_ts = time.time()
        tracker._check_signal = AsyncMock(return_value=None)

        telegram_user_id = 1234567890
        perf_mock = AsyncMock(return_value={"total": 0})

        with (
            patch("engine.realtime_outcome_tracker._fetch_active_signals", AsyncMock(return_value=[{"signal_id": "sig-1"}])),
            patch("engine.realtime_outcome_tracker._fetch_delivered_untracked_signals", AsyncMock(return_value=[])),
            patch("db.session.get_session", side_effect=lambda: _SessionCM([(telegram_user_id,)])),
            patch("db.pg_features.get_user_performance_30d", perf_mock),
            patch.dict("os.environ", {"OUTCOME_TRACKER_UPDATE_USER_PERF": "1"}),
        ):
            await tracker._check_all()

        perf_mock.assert_awaited_once()
        self.assertEqual(perf_mock.await_args.args[1], telegram_user_id)

