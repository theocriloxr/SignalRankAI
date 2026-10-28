"""Shadow evidence for the expectancy hard block (owner decision, 28 Oct 2026).

Production refuses every candidate with `risk/expectancy_unavailable` because no
delivered outcomes exist, so the gate can never reopen. Refused candidates are
now tracked as shadow trades; with the flag on, the gate may use that evidence
only when it is stricter than the live rule. The hard block itself stays on.
"""
from __future__ import annotations

import asyncio
import os
from datetime import timedelta
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.engine import make_url

import engine.core as engine_core
from engine import expectancy_shadow as es
from engine.risk import risk_check_with_reason


class FakeState:
    def __init__(self):
        self.values = {}

    def get_sync(self, key):
        return self.values.get(key)

    def set_sync(self, key, value, ex=None):
        self.values[key] = value


def _candidate(**overrides):
    base = {"asset": "BTCUSDT", "strategy_name": "EMA Trend", "timeframe": "1h", "direction": "LONG",
            "entry": 100.0, "stop_loss": 98.0, "take_profit": [103.0, 104.0], "rr_ratio": 2.0}
    return {**base, **overrides}


# --- pure rules ---------------------------------------------------------------

def test_one_setup_is_recorded_once_however_many_cycles_see_it():
    state = FakeState()
    first = es.claim(_candidate(), state)
    assert first and es.claim(_candidate(), state) is None
    assert es.claim(_candidate(entry=101.0), state) not in (None, first)
    assert es.shadow_key(_candidate(stop_loss=None)) is None


def test_realized_r_counts_ambiguous_bars_as_losses():
    assert es.realized_r("LONG", 100, 98, [103, 104], "tp3") == pytest.approx(2.0)
    assert es.realized_r("SHORT", 100, 102, "[97, 96]", "tp3") == pytest.approx(2.0)
    assert es.realized_r("LONG", 100, 98, [104], "sl") == -1.0
    assert es.realized_r("LONG", 100, 98, [104], "ambiguous") == -1.0
    assert es.realized_r("LONG", 100, 100, [104], "tp3") is None


def test_qualification_is_stricter_than_the_live_rule(monkeypatch):
    monkeypatch.setenv("EXPECTANCY_MIN_SAMPLE", "10")
    monkeypatch.delenv("EXPECTANCY_SHADOW_SAMPLE_MULTIPLIER", raising=False)
    monkeypatch.delenv("EXPECTANCY_SHADOW_COST_R", raising=False)
    strong = [2.0] * 14 + [-1.0] * 6                     # mean 1.1 R over 20 trades
    assert es.summarize(strong[:19])["reason"] == "insufficient_sample"   # live would accept 10
    good = es.summarize(strong)
    assert good["actionable"] and good["required_sample"] == 20
    assert good["expectancy_lower_95_r"] < good["mean_r"] - 0.05          # bound and haircut applied
    noisy = es.summarize([2.0] * 11 + [-1.0] * 9)                       # mean 0.65 R, wide interval
    assert noisy["mean_r"] > 0.15 and not noisy["actionable"]
    assert noisy["reason"] == "lower_bound_below_minimum"


# --- engine wiring --------------------------------------------------------------

def test_expectancy_refusals_become_shadow_rows_once_and_others_stay_skipped(monkeypatch):
    logged = []
    monkeypatch.setattr(engine_core, "_log_decision", lambda decision, sig, reason=None, meta=None:
                        logged.append((decision, reason, (meta or {}).get("layer"))))
    monkeypatch.setattr(engine_core, "state", FakeState())
    monkeypatch.delenv("EXPECTANCY_SHADOW_RECORDING_ENABLED", raising=False)
    refused = _candidate(risk_rejection_reason="expectancy_unavailable", rejection_reason="risk/expectancy_unavailable")
    engine_core._log_risk_refusal(dict(refused))
    engine_core._log_risk_refusal(dict(refused))
    engine_core._log_risk_refusal(_candidate(risk_rejection_reason="volatility", rejection_reason="risk/volatility"))
    assert logged == [("rejected", "risk/expectancy_unavailable", "expectancy"),
                      ("skipped", "risk/expectancy_unavailable", None),
                      ("skipped", "risk/volatility", None)]
    monkeypatch.setenv("EXPECTANCY_SHADOW_RECORDING_ENABLED", "0")
    engine_core._log_risk_refusal(_candidate(entry=120.0, risk_rejection_reason="expectancy_unavailable",
                                             rejection_reason="risk/expectancy_unavailable"))
    assert logged[-1][0] == "skipped"


def _shadow_context(actionable: bool):
    async def fake(asset, strategy=None, lookback_hours=720):
        return {"actionable": actionable, "expectancy_lower_95_r": 0.42 if actionable else None,
                "sample_size": 25, "reason": "ok" if actionable else "insufficient_sample"}
    return fake


def test_shadow_evidence_is_only_used_when_flagged_and_live_evidence_is_missing(monkeypatch):
    monkeypatch.setattr(es, "get_shadow_performance_context", _shadow_context(True))
    sig = _candidate()
    monkeypatch.delenv("EXPECTANCY_SHADOW_BOOTSTRAP_ENABLED", raising=False)
    engine_core._apply_shadow_expectancy(sig, "BTCUSDT")
    assert "live_expectancy" not in sig
    monkeypatch.setenv("EXPECTANCY_SHADOW_BOOTSTRAP_ENABLED", "1")
    engine_core._apply_shadow_expectancy(sig, "BTCUSDT")
    assert sig["live_expectancy"] == 0.42 and sig["expectancy_evidence_source"] == "shadow_bootstrap"
    live = _candidate(live_expectancy=0.3)
    engine_core._apply_shadow_expectancy(live, "BTCUSDT")
    assert live["live_expectancy"] == 0.3 and "expectancy_evidence_source" not in live
    monkeypatch.setattr(es, "get_shadow_performance_context", _shadow_context(False))
    weak = _candidate()
    engine_core._apply_shadow_expectancy(weak, "BTCUSDT")
    assert "live_expectancy" not in weak and weak["shadow_evidence_reason"] == "insufficient_sample"


def test_the_hard_block_stays_on_and_opens_only_on_qualified_evidence(monkeypatch):
    monkeypatch.setenv("EXPECTANCY_HARD_BLOCK_ENABLED", "1")
    monkeypatch.setenv("ENABLE_CORRELATION_GATE", "0")
    account = type("AccountState", (), {"drawdown": 0.0})()
    base = _candidate(volatility=0.01, asset_class="crypto", timeframe_minutes=60, take_profit=104.0)
    assert risk_check_with_reason(dict(base), account) == (False, "expectancy_unavailable")
    assert risk_check_with_reason({**base, "live_expectancy": 0.10}, account) == (False, "expectancy_below_minimum")
    assert risk_check_with_reason({**base, "live_expectancy": 0.42}, account)[0] is True


# --- real PostgreSQL --------------------------------------------------------------

@pytest_asyncio.fixture
async def isolated_postgres():
    from db.session import dispose_engine_for_event_loop, get_session

    url = os.getenv("DATABASE_URL", "")
    if not url:
        if os.getenv("SIGNALRANK_POSTGRES_INTEGRATION_REQUIRED") == "1":
            pytest.fail("real PostgreSQL integration required but DATABASE_URL is missing")
        pytest.skip("requires an isolated PostgreSQL test database")
    parsed = make_url(url)
    assert parsed.get_backend_name() == "postgresql"
    assert os.getenv("APP_ENV") == "test", "integration mutations require APP_ENV=test"
    assert parsed.host in {"127.0.0.1", "localhost"} and "test" in (parsed.database or "")
    async with get_session() as session:
        assert (await session.execute(text("SELECT version_num FROM alembic_version"))).scalar_one()
    yield
    await dispose_engine_for_event_loop()


async def _insert(asset: str, rows: list[tuple[str, dict]]) -> list[int]:
    from db.models import DecisionLog
    from db.session import get_session
    from utils.timeutils import now_utc_naive

    async with get_session() as session:
        records = [DecisionLog(signal_id=str(uuid4()), asset=asset, timeframe="1h", decision="rejected",
                               reason=reason, meta=meta, created_at=now_utc_naive() - timedelta(hours=2))
                   for reason, meta in rows]
        session.add_all(records)
        await session.commit()
        return [int(r.id) for r in records]


@pytest.mark.asyncio
async def test_expectancy_worker_stores_r_and_never_writes_ml_shadow_rows(isolated_postgres):
    from db.session import get_session
    from engine.shadow_outcome_worker import ShadowOutcomeWorker

    asset = "SHD" + uuid4().hex[:6].upper()
    meta = {"layer": "expectancy", "direction": "LONG", "entry": 100.0, "stop_loss": 98.0,
            "take_profit": [104.0], "strategy_name": "EMA Trend"}
    ids = await _insert(asset, [(es.REASON, dict(meta)), (es.REASON, dict(meta)), (es.REASON, dict(meta))])
    worker = ShadowOutcomeWorker(layer="expectancy")
    rows = [{"id": i, "signal_id": None, "asset": asset, "direction": "LONG", "entry": 100.0, "stop_loss": 98.0,
             "take_profit": [104.0], "ml_probability": 0.0, "rejection_reason": es.REASON, "features": {}}
            for i in ids]
    async with get_session() as session:
        before = int((await session.execute(text("SELECT COUNT(*) FROM ml_shadow_predictions"))).scalar_one())
    tracked = await worker._persist(list(zip(rows, ["tp3", "sl", "ambiguous"])))
    assert tracked == 3
    async with get_session() as session:
        stored = (await session.execute(text(
            "SELECT meta->>'shadow_r' FROM decision_log WHERE id = ANY(:ids) ORDER BY id"), {"ids": ids})).scalars().all()
        after = int((await session.execute(text("SELECT COUNT(*) FROM ml_shadow_predictions"))).scalar_one())
    assert [float(v) for v in stored] == [2.0, -1.0, -1.0]  # risk 2, reward 4
    assert after == before


@pytest.mark.asyncio
async def test_evidence_query_qualifies_only_a_strong_and_large_enough_sample(isolated_postgres, monkeypatch):
    monkeypatch.setenv("EXPECTANCY_MIN_SAMPLE", "10")
    asset = "SHD" + uuid4().hex[:6].upper()

    def tracked(r):
        return (es.REASON, {"layer": "expectancy", "strategy_name": "EMA Trend", "shadow_r": r,
                            "outcome_tracked_at": "2026-10-28T00:00:00"})

    await _insert(asset, [tracked(2.0)] * 12)
    context = await es.get_shadow_performance_context(asset, strategy="EMA Trend")
    assert context["actionable"] is False and context["sample_size"] == 12
    await _insert(asset, [tracked(2.0)] * 12 + [tracked(-1.0)] * 4)
    context = await es.get_shadow_performance_context(asset, strategy="EMA Trend")
    assert context["actionable"] is True and context["scope"] == "asset_strategy"
    assert context["sample_size"] == 28 and context["expectancy_lower_95_r"] >= 0.15
    # Pending (untracked) and other-layer rows never count.
    await _insert(asset, [(es.REASON, {"layer": "expectancy", "strategy_name": "EMA Trend"}),
                          ("ml", {"layer": "ml", "shadow_r": 5.0})])
    again = await es.get_shadow_performance_context(asset, strategy="EMA Trend")
    assert again["sample_size"] == 28
