"""Evidence-based setup filter (owner decision, 2 Nov 2026)."""
from __future__ import annotations

import time
from uuid import uuid4

import pytest

from services import segment_evidence as se


def _signal(**extra):
    return {"strategy_name": "MACD Momentum", "timeframe": "1d", "direction": "SELL", "entry": 100.0,
            "stop_loss": 102.0, "take_profit": [95.0, 92.0, 88.0], **extra}


def test_wilson_bound_is_cautious_on_small_samples():
    z = se.confidence_z()
    assert z == pytest.approx(1.6449, abs=1e-3)  # one-sided 95 %
    assert se.wilson_lower_bound(9, 10, z) < 0.9 and se.wilson_lower_bound(900, 1000, z) > 0.88
    assert se.wilson_lower_bound(0, 0, z) == 0.0


def test_breakeven_follows_the_published_exit_plan(monkeypatch):
    # close 50 % at TP1 (2.5R), remainder at entry, loss = 1R: p * 1.25 = 1 - p
    assert se.breakeven_tp1_rate(2.5) == pytest.approx(1 / 2.25)
    monkeypatch.setenv("SIGNAL_TP1_CLOSE_FRACTION", "1.0")
    monkeypatch.setenv("SIGNAL_TP2_CLOSE_FRACTION", "0")
    assert se.breakeven_tp1_rate(2.5) == pytest.approx(1 / 3.5)
    assert se.breakeven_tp1_rate(0) is None


def test_a_proven_setup_passes_and_a_losing_one_is_blocked():
    segments = {"macd momentum|1d|short": {"n": 159, "wins": 144},   # production, 60 days: 90.6 %
                "ema trend|5m|long": {"n": 300, "wins": 64}}         # about 21 %
    ok = se.evaluate(_signal(), segments)
    assert ok.allowed and ok.lower_bound > ok.breakeven and "144/159" in ok.reason
    bad = se.evaluate(_signal(strategy_name="EMA Trend", timeframe="5m", direction="long", stop_loss=98.0,
                              take_profit=[105.0]), segments)
    assert not bad.allowed and bad.lower_bound < bad.breakeven


def test_a_setup_without_evidence_or_valid_levels_is_blocked():
    assert not se.evaluate(_signal(strategy_name="New Strategy"), {}).allowed
    assert not se.evaluate(_signal(take_profit=[]), {"macd momentum|1d|short": {"n": 159, "wins": 144}}).allowed


def test_snapshot_age_follows_the_refresh_interval(monkeypatch):
    monkeypatch.setenv("SEGMENT_EVIDENCE_REFRESH_SECONDS", "900")
    now = time.time()
    assert se.snapshot_is_current({"computed_at": now - 1700}, now=now)
    assert not se.snapshot_is_current({"computed_at": now - 1900}, now=now)
    assert not se.snapshot_is_current(None)


# --- Real PostgreSQL: worker refresh -> snapshot -> engine gate ---------------------------------------

from tests.test_master_p0_postgres_integration import postgres_database  # noqa: E402,F401


@pytest.mark.asyncio
async def test_worker_snapshot_drives_the_engine_gate(postgres_database):  # noqa: F811
    from db.models import DecisionLog
    from db.session import get_session
    from engine.core import _segment_quarantine_gate
    from utils.timeutils import now_utc_naive

    strategy = f"Proven {uuid4().hex[:6]}"
    async with get_session() as session:
        for i in range(60):  # 57 of 60 shadow candidates reached TP1 (written as the rejection tracker does)
            session.add(DecisionLog(asset="BTCUSDT", timeframe="1d", decision="rejected", reason="ml",
                                    created_at=now_utc_naive(),
                                    meta={"layer": "ml", "direction": "short", "entry": 100, "stop_loss": 102,
                                          "features": {"strategy_name": strategy},
                                          "actual_outcome": "tp1" if i < 57 else "sl"}))
        await session.commit()
    assert await se.refresh_once() >= 1
    allowed, reason = await _segment_quarantine_gate(_signal(strategy_name=strategy))
    assert allowed, reason
    blocked, reason = await _segment_quarantine_gate(_signal(strategy_name=f"Unproven {uuid4().hex[:6]}"))
    assert not blocked and "0/0" in reason
