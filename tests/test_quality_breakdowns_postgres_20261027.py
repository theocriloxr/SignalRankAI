"""CX-SIG-21: rejection diagnostics by asset, timeframe, strategy and layer.

The Quality view reported only window totals and global top reasons, which
cannot show where a signal drought comes from. The breakdown runs against a
real PostgreSQL decision_log (GROUPING SETS cannot be faked by SQLite) and
labels rows without a strategy as unattributed instead of guessing one.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy.engine import make_url

import web.platform_api as platform_api
from web.platform_api import _quality_breakdowns

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def isolated_postgres():
    from db.session import dispose_engine_for_event_loop, get_session
    from sqlalchemy import text

    url = os.getenv("DATABASE_URL", "")
    if not url:
        if os.getenv("SIGNALRANK_POSTGRES_INTEGRATION_REQUIRED") == "1":
            pytest.fail("real PostgreSQL integration required but DATABASE_URL is missing")
        pytest.skip("requires an isolated PostgreSQL test database")
    parsed = make_url(url)
    assert parsed.get_backend_name() == "postgresql"
    assert os.getenv("APP_ENV") == "test", "integration mutations require APP_ENV=test"
    assert parsed.host in {"127.0.0.1", "localhost"}
    assert "test" in (parsed.database or "")
    async with get_session() as session:
        assert (await session.execute(text("SELECT version_num FROM alembic_version"))).scalar_one()
    yield
    await dispose_engine_for_event_loop()


async def _seed(tag: str) -> None:
    from db.models import DecisionLog
    from db.session import get_session

    now = datetime.utcnow()
    rows = [
        # asset, timeframe, decision, reason, meta
        (f"{tag}A", "1h", "rejected", "score_below_threshold", {"strategy": "breakout", "layer": "score"}),
        (f"{tag}A", "1h", "rejected", "ml_probability_low", {"strategy": "breakout", "layer": "ml"}),
        (f"{tag}A", "4h", "issued", "", {"strategy": "breakout"}),
        (f"{tag}B", "15m", "skipped", "stale_market_data", {"layer": "market_data"}),
        (f"{tag}B", "15m", "rejected", "risk_reward_low", {"strategy_name": "mean_reversion", "layer": "risk"}),
    ]
    async with get_session() as session:
        session.add_all([
            DecisionLog(signal_id=f"{tag}-{i}", asset=a, timeframe=tf, decision=d, reason=r, meta=m,
                        created_at=now - timedelta(minutes=5))
            for i, (a, tf, d, r, m) in enumerate(rows)
        ])
        # Outside the window: must not be counted.
        session.add(DecisionLog(signal_id=f"{tag}-old", asset=f"{tag}A", timeframe="1h", decision="rejected",
                                reason="old", meta={"strategy": "breakout"}, created_at=now - timedelta(days=30)))
        await session.commit()


def _by(result, dimension, value):
    return next(item for item in result["breakdowns"][dimension] if item["value"] == value)


async def test_quality_report_breaks_decisions_down_on_real_postgres(isolated_postgres, monkeypatch):
    tag = "QB" + uuid4().hex[:6].upper()
    await _seed(tag)
    monkeypatch.setattr(platform_api, "_assert_command", lambda *_a, **_k: None)

    result = await platform_api.quality_report(hours=1, user={"id": 1})

    asset_a = _by(result, "asset", f"{tag}A")
    assert (asset_a["issued"], asset_a["rejected_or_skipped"]) == (1, 2)
    assert asset_a["acceptance_rate"] == pytest.approx(1 / 3)
    asset_b = _by(result, "asset", f"{tag}B")
    assert (asset_b["issued"], asset_b["rejected_or_skipped"]) == (0, 2)
    assert set(result["breakdowns"]) == {"asset", "timeframe", "strategy", "layer"}
    strategies = {item["value"] for item in result["breakdowns"]["strategy"]}
    assert {"breakout", "mean_reversion", "(unattributed)"} <= strategies
    assert {item["value"] for item in result["breakdowns"]["layer"]} >= {"score", "ml", "risk", "market_data"}


def test_breakdown_shaping_orders_by_rejections_and_labels_missing_values():
    rows = [
        {"dimension": "strategy", "value": None, "decision": "rejected", "rows": 5},
        {"dimension": "strategy", "value": "breakout", "decision": "rejected", "rows": 9},
        {"dimension": "strategy", "value": "breakout", "decision": "issued", "rows": 1},
        {"dimension": "asset", "value": "BTCUSDT", "decision": "observed", "rows": 3},
        {"dimension": "bogus", "value": "x", "decision": "issued", "rows": 1},
    ]
    result = _quality_breakdowns(rows)
    assert [item["value"] for item in result["strategy"]] == ["breakout", "(unattributed)"]
    assert result["strategy"][0]["acceptance_rate"] == pytest.approx(0.1)
    assert result["asset"] == [{"value": "BTCUSDT", "issued": 0, "rejected_or_skipped": 0, "other": 3,
                                "acceptance_rate": None}]
    assert "bogus" not in result
