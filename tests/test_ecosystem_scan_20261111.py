"""Fixes from the 11 Nov 2026 ecosystem scan."""
from __future__ import annotations

import asyncio
import contextlib

HOUR_MS = 3_600_000


def _bar(ts, o, h, l, c, v=1.0):
    return {"timestamp": ts, "open": o, "high": h, "low": l, "close": c, "volume": v}


def test_coinbase_4h_is_built_from_complete_utc_hours():
    from data.connectors.coinbase_adapter import _aggregate_4h

    base = 1_794_384_000_000 - 1_794_384_000_000 % (4 * HOUR_MS)
    hourly = [_bar(base - HOUR_MS, 9, 9, 9, 9)]  # tail of an incomplete earlier bucket: dropped
    hourly += [_bar(base + i * HOUR_MS, 10 + i, 20 + i, 5 + i, 11 + i, 2.0) for i in range(4)]
    hourly += [_bar(base + 4 * HOUR_MS, 30, 31, 29, 30.5)]  # newest bucket, still forming: kept
    bars = _aggregate_4h(hourly)

    assert [b["timestamp"] for b in bars] == [base, base + 4 * HOUR_MS]
    first = bars[0]
    assert (first["open"], first["high"], first["low"], first["close"], first["volume"]) == (10, 23, 5, 14, 8.0)


def test_coinbase_4h_request_uses_hourly_data(monkeypatch):
    from data.connectors import coinbase_adapter as cb

    asked = []
    real = cb._async_get_candles

    async def fake(symbol, timeframe, limit=200, timeout=10):
        if timeframe == "1h":
            asked.append((timeframe, limit))
            base = 0
            return [_bar(base + i * HOUR_MS, 1, 2, 0.5, 1.5) for i in range(8)]
        return await real(symbol, timeframe, limit=limit, timeout=timeout)

    monkeypatch.setattr(cb, "_async_get_candles", fake)
    bars = asyncio.run(real("BTCUSDT", "4h"))
    assert asked == [("1h", 300)]
    assert len(bars) == 2


def test_training_run_is_also_kept_in_runtime_state(monkeypatch):
    import db.session as db_session
    from ml import lifecycle_status

    written = {}

    class _Session:
        async def execute(self, stmt, params=None):
            written[params["k"]] = params["v"]

        async def commit(self):
            return None

    @contextlib.asynccontextmanager
    async def fake_get_session(**_kwargs):
        yield _Session()

    monkeypatch.setattr(db_session, "get_session", fake_get_session)

    async def train_main():
        import logging
        logging.getLogger("ml.train_model").info("[ml_quality] gate passed=False auc=0.71")
        return False

    asyncio.run(lifecycle_status.run_and_record(train_main))
    assert lifecycle_status.DB_LAST_RUN_KEY in written
    assert '"returned": false' in written[lifecycle_status.DB_LAST_RUN_KEY]


def test_segment_refresh_uses_short_sessions_and_survives_one_failure(monkeypatch):
    """10-11 Nov 2026: one 30 s session for 1,440 reads timed out; the snapshot went stale."""
    import db.session as db_session
    from services import segment_evidence as se

    monkeypatch.setenv("SEGMENT_EVIDENCE_LOOKBACK_DAYS", "1")
    calls = {"window": 0, "sessions": 0}
    stored = {}

    class _Result:
        def __init__(self, rows):
            self._rows = rows

        def all(self):
            return self._rows

    class _Session:
        async def execute(self, stmt, params=None):
            sql = str(stmt)
            if "ml_rejected_signals" in sql:
                calls["window"] += 1
                if calls["window"] == 3:
                    raise TimeoutError("busy")
                if calls["window"] == 1:
                    return _Result([("BTCUSDT", "1h", "ema trend", "long", 1, "tp1")])
                return _Result([])
            if "INSERT INTO runtime_state" in sql:
                stored["value"] = params["value"]
            return _Result([])

        async def commit(self):
            return None

        async def rollback(self):
            return None

    @contextlib.asynccontextmanager
    async def fake_get_session(**_kwargs):
        calls["sessions"] += 1
        yield _Session()

    async def no_sleep(_s):
        return None

    monkeypatch.setattr(db_session, "get_session", fake_get_session)
    monkeypatch.setattr(asyncio, "sleep", no_sleep)
    count = asyncio.run(se.refresh_once())
    assert count == 1
    assert calls["window"] == 25  # 24 hours + one retry
    assert calls["sessions"] >= 26  # one per read, plus the store
    assert '"ema trend|1h|long"' in stored["value"] or "ema trend" in stored["value"]


def test_drought_alert_names_a_stale_setup_evidence_snapshot(monkeypatch):
    from observability import owner_alerts
    from observability.owner_alerts import signal_drought_alert

    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:test")
    monkeypatch.setattr(owner_alerts, "_owner_ids", lambda: [42])
    monkeypatch.setattr("core.health_notifications.claim_health_notification", lambda *a, **k: (True, None))
    sent = []
    finding = {"hours_since_last_signal": 36.0, "top_reasons": [{"reason": "quality_adx N < N (fx)", "count": 9}],
               "segment_evidence_age_hours": 19.3}
    signal_drought_alert(finding, post=lambda token, chat, text: sent.append(text) or True)
    assert sent and "19.3 h old" in sent[0]
