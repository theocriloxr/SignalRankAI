import sys
import types
from contextlib import asynccontextmanager

import pytest


def test_optional_polygon_connector_outage_is_suppressed_by_default(monkeypatch):
    from data.fetcher import should_alert_provider_outage

    monkeypatch.delenv("PROVIDER_OUTAGE_ALERT_OPTIONAL", raising=False)

    assert should_alert_provider_outage("polygon_connector", 30.0) is False


def test_optional_provider_outage_can_be_opted_in(monkeypatch):
    import data.fetcher as fetcher

    monkeypatch.setenv("PROVIDER_OUTAGE_ALERT_OPTIONAL", "1")
    fetcher._PROVIDER_OUTAGE_ALERTED.clear()
    fetcher._PROVIDER_OUTAGE_LAST_ALERT.clear()

    assert fetcher.should_alert_provider_outage("polygon_connector", 30.0) is True


def test_stats_adapter_supports_legacy_property_increment():
    from core.redis_global_stats import stats

    stats.reset()
    stats.scanned += 1
    stats.delivered += 2
    stats.vetoed_score += 3

    snapshot = stats.get_stats()

    assert snapshot["scanned"] == 1
    assert snapshot["delivered"] == 2
    assert snapshot["vetoed_score"] == 3


def test_tradingview_validation_does_not_emit_synthetic_candle(monkeypatch):
    import data.fetcher as fetcher

    class _Analysis:
        indicators = {"summary": "BUY", "RSI": 55}

    class _Handler:
        def __init__(self, *args, **kwargs):
            pass

        def get_analysis(self):
            return _Analysis()

    fake_tv = types.SimpleNamespace(
        TA_Handler=_Handler,
        Interval=types.SimpleNamespace(
            INTERVAL_1_HOUR="1h",
            INTERVAL_4_HOURS="4h",
            INTERVAL_1_DAY="1d",
            INTERVAL_15_MINUTES="15m",
        ),
    )
    monkeypatch.setitem(sys.modules, "tradingview_ta", fake_tv)
    monkeypatch.setenv("TRADINGVIEW_ENABLED", "1")

    candles = fetcher.get_tradingview_candles("BTCUSDT", "1h")

    assert candles == []


def test_similarity_module_imports_and_sync_wrapper_runs(monkeypatch):
    import engine.similarity as similarity

    async def _fake_winrate(*args, **kwargs):
        return 0.75, 12, 9

    monkeypatch.setattr(similarity, "get_historical_winrate", _fake_winrate)

    assert similarity.get_historical_winrate_sync("BTCUSDT") == (0.75, 12, 9)


@pytest.mark.asyncio
async def test_risk_free_recipient_throttle_is_asset_direction_timeframe_scoped(monkeypatch):
    from engine.realtime_outcome_tracker import _mark_risk_free_recipient_triggered

    seen = set()

    class _FakeState:
        async def cache_get(self, key):
            return "1" if key in seen else None

        async def cache_set(self, key, value, ex=None):
            seen.add(key)

    monkeypatch.setitem(sys.modules, "core.redis_state", types.SimpleNamespace(state=_FakeState()))

    signal_a = {"asset": "AAVEUSDT", "direction": "short", "timeframe": "1d"}
    signal_b = {"asset": "AAVEUSDT", "direction": "short", "timeframe": "1d"}
    signal_c = {"asset": "AAVEUSDT", "direction": "short", "timeframe": "4h"}

    assert await _mark_risk_free_recipient_triggered(123, signal_a, ttl_seconds=300) is True
    assert await _mark_risk_free_recipient_triggered(123, signal_b, ttl_seconds=300) is False
    assert await _mark_risk_free_recipient_triggered(123, signal_c, ttl_seconds=300) is True


@pytest.mark.asyncio
async def test_admin_pulse_uses_db_evidence_when_global_stats_are_zero(monkeypatch):
    import engine.admin_pulse as pulse

    class _Stats:
        def get_stats(self):
            return {
                "scanned": 0,
                "delivered": 0,
                "vetoed_regime": 0,
                "vetoed_squeeze": 0,
                "vetoed_microstructure": 0,
                "vetoed_score": 0,
                "vetoed_ml": 0,
                "vetoed_other": 0,
            }

    monkeypatch.setitem(sys.modules, "engine.stats_manager", types.SimpleNamespace(stats=_Stats()))

    class _Result:
        def __init__(self, rows):
            self._rows = rows

        def first(self):
            return self._rows[0] if self._rows else None

        def fetchall(self):
            return list(self._rows)

    class _Session:
        async def execute(self, stmt, params=None):
            sql = str(stmt)
            if "FROM decision_log" in sql and "GROUP BY" not in sql:
                return _Result([(3,)])
            if "FROM decision_log" in sql and "GROUP BY" in sql:
                return _Result([("rejected", 2), ("issued", 1)])
            if "FROM signal_deliveries" in sql and "delivered_at" in sql:
                return _Result([(2,)])
            if "FROM signals" in sql:
                return _Result([(4,)])
            return _Result([(0,)])

    @asynccontextmanager
    async def _fake_get_session():
        yield _Session()

    monkeypatch.setitem(sys.modules, "db.session", types.SimpleNamespace(get_session=_fake_get_session))

    class _State:
        def get_sync(self, key):
            return 0

    monkeypatch.setitem(sys.modules, "core.redis_state", types.SimpleNamespace(state=_State()))

    stats = await pulse.compute_engine_health(window_hours=1)

    assert stats["scanned"] == 4
    assert stats["delivered"] == 2
    assert stats["rejected_by"] == {"rejected": 2, "issued": 1}
    assert stats["sources"]["global_total"] == 0
