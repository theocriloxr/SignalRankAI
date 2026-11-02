"""Evidence-based setup filter (owner decision, 2 Nov 2026)."""
from __future__ import annotations

import time
from datetime import timedelta
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
        for i in range(55):  # one candidate per daily bar; 52 of 55 reached TP1 (written as the tracker does)
            session.add(DecisionLog(asset="BTCUSDT", timeframe="1d", decision="rejected", reason="ml",
                                    created_at=now_utc_naive() - timedelta(days=i),
                                    meta={"layer": "ml", "direction": "short", "entry": 100, "stop_loss": 102,
                                          "features": {"strategy_name": strategy},
                                          "actual_outcome": "tp1" if i < 52 else "sl"}))
        await session.commit()
    assert await se.refresh_once() >= 1
    allowed, reason = await _segment_quarantine_gate(_signal(strategy_name=strategy))
    assert allowed, reason
    blocked, reason = await _segment_quarantine_gate(_signal(strategy_name=f"Unproven {uuid4().hex[:6]}"))
    assert not blocked and "0/0" in reason


def test_ml_is_advisory_by_default_and_enforce_restores_the_veto(monkeypatch):
    from engine.core import _ml_gate_advisory

    monkeypatch.delenv("ML_GATE_MODE", raising=False)
    assert _ml_gate_advisory()
    monkeypatch.setenv("ML_GATE_MODE", "enforce")
    assert not _ml_gate_advisory()


def test_advisory_signals_stay_paper_only_and_say_why():
    from signalrank_telegram.tier_signal_formatter import _execution_status_line

    line = _execution_status_line({"ml_recovery_mode": True, "ml_recovery_reason": "ml_advisory_mode"})
    assert "PAPER ONLY" in line and "setup-evidence filter" in line and "advisory" in line


@pytest.mark.asyncio
async def test_without_current_evidence_the_filter_blocks_while_ml_is_advisory(postgres_database, monkeypatch):  # noqa: F811
    from sqlalchemy import text

    from db.session import get_session
    from engine.core import _segment_quarantine_gate

    monkeypatch.delenv("ML_GATE_MODE", raising=False)
    async with get_session() as session:
        await session.execute(text("DELETE FROM runtime_state WHERE key = :k"), {"k": se.SNAPSHOT_KEY})
        await session.commit()
    allowed, reason = await _segment_quarantine_gate(_signal())
    assert not allowed and reason == "segment_evidence_unavailable"


@pytest.mark.asyncio
async def test_a_setup_logged_on_every_scan_counts_once_per_bar(postgres_database):  # noqa: F811
    from db.models import DecisionLog
    from db.session import get_session
    from utils.timeutils import now_utc_naive

    strategy = f"Rescanned {uuid4().hex[:6]}"
    bar_start = now_utc_naive().replace(minute=0, second=0, microsecond=0) - timedelta(hours=1)
    async with get_session() as session:
        for i in range(500):  # one 1h bar, re-logged on every scan
            session.add(DecisionLog(asset="BTCUSDT", timeframe="1h", decision="rejected", reason="ml",
                                    created_at=bar_start.replace(second=i % 60), meta={
                                        "layer": "ml", "direction": "short", "features": {"strategy_name": strategy},
                                        "actual_outcome": "tp1"}))
        await session.commit()
    async with get_session() as session:
        snapshot = await se.compute_snapshot(session)
        await session.rollback()
    assert snapshot["segments"][se.segment_key(strategy, "1h", "short")] == {"n": 1, "wins": 1}


@pytest.mark.asyncio
async def test_a_bar_read_in_several_windows_counts_once(postgres_database):  # noqa: F811
    from db.models import DecisionLog
    from db.session import get_session
    from utils.timeutils import now_utc_naive

    strategy = f"Spanning {uuid4().hex[:6]}"
    day = (now_utc_naive() - timedelta(days=2)).replace(hour=0, minute=0, second=0, microsecond=0)
    # One 1d bar read in hourly windows: its first and last minute fall in different windows.
    async with get_session() as session:
        for created_at, outcome in ((day + timedelta(minutes=1), "sl"), (day + timedelta(hours=23, minutes=59), "tp1")):
            session.add(DecisionLog(asset="ETHUSDT", timeframe="1d", decision="rejected", reason="ml",
                                    created_at=created_at, meta={
                                        "layer": "ml", "direction": "long", "features": {"strategy_name": strategy},
                                        "actual_outcome": outcome}))
        await session.commit()
    async with get_session() as session:
        snapshot = await se.compute_snapshot(session)
        await session.rollback()
    assert snapshot["segments"][se.segment_key(strategy, "1d", "long")] == {"n": 1, "wins": 0}
