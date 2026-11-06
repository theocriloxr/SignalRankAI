"""Shadow labels record their source; stale-tick labels can be corrected (6 Nov 2026).

Until ``bec9a5f`` (4 Nov) the shadow tracker's live price for forex, metals,
oil, indices and stocks came from ``market_ticks`` rows last written in July.
The labels stored then did not say whether candles or a live price decided
them. The tracker now stores ``meta.outcome_label_source`` and
``scripts/correct_stale_tick_shadow_labels.py`` re-labels the old rows from
stored ``market_candles`` with the tracker's own candle rule.

PostgreSQL cases need ``SIGNALRANK_TEST_PG_DSN`` pointing at an owned scratch
database migrated to head (never production).
"""
from __future__ import annotations

import asyncio
import importlib.util
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from engine.shadow_outcome_worker import (
    LABEL_SOURCE_CANDLES,
    LABEL_SOURCE_LIVE_PRICE,
    UNVERIFIABLE_OUTCOME,
    ShadowOutcomeWorker,
    label_from_candles,
)
from utils.timeutils import now_utc_naive

ROOT = Path(__file__).resolve().parents[1]
_PG_DSN = os.getenv("SIGNALRANK_TEST_PG_DSN", "")


def _script():
    spec = importlib.util.spec_from_file_location("correct_labels", ROOT / "scripts" / "correct_stale_tick_shadow_labels.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _migration():
    path = ROOT / "db" / "migrations" / "versions" / "0059_close_pending_terminal_outcomes.py"
    spec = importlib.util.spec_from_file_location("m0059", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _row(created_at, asset="EURGBP", timeframe="15m"):
    return {"id": 1, "signal_id": None, "asset": asset, "timeframe": timeframe, "direction": "long",
            "entry": 0.83472, "stop_loss": 0.83388, "take_profit": [0.83714], "ml_probability": 0.4,
            "rejection_reason": "ml_filter", "features": {}, "created_at": created_at}


def _flat_candles(start, count, step, low=0.8344, high=0.8349):
    return [{"timestamp": (start + step * i).isoformat(), "open": 0.8346, "high": high, "low": low,
             "close": 0.8346} for i in range(count)]


# --- tracker: label source ---------------------------------------------------

@pytest.mark.asyncio
async def test_candle_labels_record_candles_as_source(monkeypatch):
    created = now_utc_naive() - timedelta(hours=2)
    step = timedelta(minutes=15)
    candles = _flat_candles(created - step, 8, step)
    candles[4]["low"] = 0.8330  # stop

    async def fake_candles(asset, tf):
        return candles

    async def fake_live(_asset):
        raise AssertionError("candles decide this row")

    monkeypatch.setattr("data.fetcher.async_get_candles", fake_candles)
    monkeypatch.setattr("engine.realtime_outcome_tracker._get_live_price", fake_live)
    [(row, outcome)] = await ShadowOutcomeWorker()._evaluate_rows([_row(created)])
    assert outcome == "sl"
    assert row["_label_source"] == LABEL_SOURCE_CANDLES


@pytest.mark.asyncio
async def test_live_price_labels_record_live_price_as_source(monkeypatch):
    created = now_utc_naive() - timedelta(minutes=8)

    async def no_candles(asset, tf):
        return []

    async def live(_asset):
        return 0.8330  # below the stop (0.83388)

    monkeypatch.setattr("data.fetcher.async_get_candles", no_candles)
    monkeypatch.setattr("engine.realtime_outcome_tracker._get_live_price", live)
    [(row, outcome)] = await ShadowOutcomeWorker()._evaluate_rows([_row(created)])
    assert outcome == "sl"
    assert row["_label_source"] == LABEL_SOURCE_LIVE_PRICE


# --- correction script: selection and labelling -----------------------------

SINCE = datetime(2026, 11, 1)
UNTIL = datetime(2026, 11, 4, 7, 0)


def _record(asset="EURGBP", label="tp1", tracked="2026-11-03T12:00:00", **meta):
    base = {"layer": "ml", "direction": "long", "entry": 0.83472, "stop_loss": 0.83388,
            "take_profit": [0.83714], "actual_outcome": label, "outcome_tracked_at": tracked}
    base.update(meta)
    return {"id": 7, "decision": "rejected", "asset": asset, "timeframe": "15m",
            "created_at": datetime(2026, 11, 3, 11, 55), "meta": base}


def test_selection_skips_binance_symbols_new_rows_and_corrected_rows():
    m = _script()
    pick = lambda r, **kw: m.candidate_row(r, since=SINCE, until=UNTIL, all_assets=kw.get("all_assets", False))
    assert pick(_record())
    assert not pick(_record(asset="BTCUSDT"))
    assert pick(_record(asset="BTCUSDT"), all_assets=True)
    assert not pick(_record(outcome_label_source="candles"))
    assert not pick(_record(label_correction={"reason": "x"}))
    assert not pick(_record(label="unverifiable"))
    assert not pick(_record(tracked="2026-11-04T08:00:00"))  # after the fix
    assert not pick(_record(tracked="2026-10-20T08:00:00"))  # before the window


def test_flat_market_relabels_a_stale_tick_win_as_unverifiable():
    m = _script()
    record = _record()
    step = timedelta(minutes=15)
    candles = _flat_candles(record["created_at"] - step, 30, step)
    assert m.relabel(record, candles) == UNVERIFIABLE_OUTCOME
    assert m.relabel(record, []) == UNVERIFIABLE_OUTCOME


def test_candles_that_reach_the_stop_relabel_the_win_as_sl():
    m = _script()
    record = _record()
    step = timedelta(minutes=15)
    candles = _flat_candles(record["created_at"] - step, 30, step)
    candles[10]["low"] = 0.8330
    assert m.relabel(record, candles) == "sl"
    # Same rule as the tracker.
    row = {**record["meta"], "created_at": record["created_at"], "timeframe": "15m"}
    assert label_from_candles(row, candles) == "sl"


def test_corrected_meta_keeps_the_previous_label_and_recomputes_shadow_r():
    m = _script()
    record = _record(layer="expectancy", shadow_r=0.5)
    now = datetime(2026, 11, 6, 18, 0)
    meta = m.corrected_meta(record, "sl", "expectancy", now)
    assert meta["actual_outcome"] == "sl"
    assert meta["shadow_r"] == -1.0
    assert meta["label_correction"]["previous"] == {"actual_outcome": "tp1", "shadow_r": 0.5}
    assert meta["label_correction"]["reason"] == "stale_market_ticks_live_price"
    assert meta["outcome_label_source"] == "candles_correction"
    meta = m.corrected_meta(_record(), UNVERIFIABLE_OUTCOME, "ml", now)
    assert meta["actual_outcome"] == UNVERIFIABLE_OUTCOME and "shadow_r" not in meta


def test_script_defaults_to_a_dry_run_and_needs_until(monkeypatch, capsys):
    m = _script()
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_PRIVATE_URL", raising=False)
    with pytest.raises(SystemExit):
        m.main([])
    assert m.main(["--until", "2026-11-04T07:00:00"]) == 2  # no DSN, nothing touched
    source = (ROOT / "scripts" / "correct_stale_tick_shadow_labels.py").read_text()
    assert 'action="store_true", help="write the corrections (default: dry run)"' in source
    assert "DELETE" not in source.upper()


# --- migration 0059 ----------------------------------------------------------

def test_migration_0059_chain_and_audit_fields():
    m = _migration()
    assert m.revision == "0059_close_pending_terminal"
    assert m.down_revision == "0058_exclude_no_trade_outcomes"
    assert len(m.revision) <= 32
    for column in ("corrected_by", "corrected_at", "correction_reason"):
        assert column in m.UPGRADE_SQL  # required by trg_terminal_outcome_finality
    assert "IN ('', 'pending')" in m.UPGRADE_SQL
    for untouched in ("r_multiple =", "percent =", "status =", "performance_inclusion_status ="):
        assert untouched not in m.UPGRADE_SQL
    assert "DELETE" not in m.UPGRADE_SQL.upper()


def test_migration_0059_mapping_matches_upsert_outcome():
    from db.pg_features import _derived_canonical_outcome

    sql = _migration().DERIVED_SQL
    for status in ("tp", "tp3", "win"):
        assert _derived_canonical_outcome(status) == "win"
    assert _derived_canonical_outcome("sl", {"tp_hit_index": 1}) == "partial_win"
    assert _derived_canonical_outcome("sl", {}) == "loss"
    assert "('tp', 'tp3', 'win') THEN 'win'" in sql
    assert "('sl', 'loss', 'stop', 'stop_loss')" in sql
    assert "THEN 'partial_win' ELSE 'loss'" in sql
    assert "('time_stop', 'missed_entry', 'expired') THEN LOWER(BTRIM(status))" in sql


# --- PostgreSQL ---------------------------------------------------------------

def _run(coro):
    return asyncio.get_event_loop_policy().new_event_loop().run_until_complete(coro)


@pytest.mark.skipif(not _PG_DSN, reason="set SIGNALRANK_TEST_PG_DSN to an owned scratch PostgreSQL at head")
def test_correction_script_end_to_end_on_postgres():
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    from db.session import _normalize_database_url

    m = _script()
    created = datetime(2026, 11, 3, 11, 0)
    step_ms = 15 * 60 * 1000
    start_ms = int((created - timedelta(minutes=15)).replace(tzinfo=timezone.utc).timestamp() * 1000)

    def meta(label, asset_layer="ml", **extra):
        value = {"layer": asset_layer, "direction": "long", "entry": 0.83472, "stop_loss": 0.83388,
                 "take_profit": [0.83714], "actual_outcome": label, "outcome_tracked_at": "2026-11-03T11:10:00"}
        value.update(extra)
        return json.dumps(value)

    async def scenario():
        engine = create_async_engine(_normalize_database_url(_PG_DSN, async_driver=True))
        try:
            async with engine.begin() as conn:
                await conn.execute(text("DELETE FROM ml_shadow_predictions WHERE meta::jsonb->>'test_case' = 'stale_tick'"))
                await conn.execute(text("DELETE FROM decision_log WHERE asset IN ('ZZEURGBP','ZZXAUUSD','ZZFLAT', 'ZZBTCUSDT')"))
                await conn.execute(text("DELETE FROM market_candles WHERE symbol IN ('ZZEURGBP','ZZXAUUSD','ZZFLAT')"))
                for symbol, stop_bar in (("ZZEURGBP", 6), ("ZZFLAT", None)):
                    for i in range(40):
                        low = 0.8330 if i == stop_bar else 0.8344
                        await conn.execute(text(
                            "INSERT INTO market_candles (symbol, timeframe, open_time_ms, open, high, low, close, volume, "
                            "is_final, updated_at) VALUES (:s, '15m', :t, 0.8346, 0.8349, :l, 0.8346, 0, true, NOW())"),
                            {"s": symbol, "t": start_ms + i * step_ms, "l": low})
                ids = {}
                for asset, label, extra in (("ZZEURGBP", "tp1", {}), ("ZZFLAT", "tp1", {}), ("ZZXAUUSD", "sl", {}),
                                            ("ZZBTCUSDT", "tp1", {}), ("ZZFLAT", "tp1", {"outcome_label_source": "candles"})):
                    ids[(asset, bool(extra))] = (await conn.execute(text(
                        "INSERT INTO decision_log (asset, timeframe, decision, reason, meta, created_at) "
                        "VALUES (:a, '15m', 'rejected', 'ml_filter', CAST(:m AS json), :c) RETURNING id"),
                        {"a": asset, "m": meta(label, **extra), "c": created})).scalar_one()
                await conn.execute(text(
                    "INSERT INTO ml_shadow_predictions (model_name, model_version, probability, is_shadow, "
                    "feature_schema_ok, meta, created_at) VALUES ('rejection_outcome_tracker', 'v1', 0.4, true, true, "
                    "CAST(:m AS json), NOW())"),
                    {"m": json.dumps({"actual_outcome": "tp1", "rejection_id": ids[("ZZEURGBP", False)],
                                      "test_case": "stale_tick"})})

            dry = await m.run(_PG_DSN, since=datetime(2026, 11, 1), until=datetime(2026, 11, 4, 7), apply=False,
                              batch=100, id_window=1_000_000, all_assets=False, out=lambda *_: None)
            assert dry["scanned"] == 3 and dry.get("written", 0) == 0
            assert dry["tp1->sl"] == 1 and dry["unverifiable"] == 2

            applied = await m.run(_PG_DSN, since=datetime(2026, 11, 1), until=datetime(2026, 11, 4, 7), apply=True,
                                  batch=100, id_window=1_000_000, all_assets=False, out=lambda *_: None)
            assert applied["written"] == 3 and applied["ml_shadow_predictions_updated"] == 1

            async with engine.connect() as conn:
                rows = {(r[0], r[2] is not None): (r[1], r[3]) for r in (await conn.execute(text(
                    "SELECT asset, meta::jsonb->>'actual_outcome', meta::jsonb->'label_correction', "
                    "meta::jsonb->'label_correction'->'previous'->>'actual_outcome' FROM decision_log "
                    "WHERE asset LIKE 'ZZ%'"))).all()}
                pred = (await conn.execute(text(
                    "SELECT meta::jsonb->>'actual_outcome' FROM ml_shadow_predictions "
                    "WHERE meta::jsonb->>'test_case' = 'stale_tick'"))).scalar_one()
            assert rows[("ZZEURGBP", True)] == ("sl", "tp1")
            assert rows[("ZZFLAT", True)] == ("unverifiable", "tp1")
            assert rows[("ZZXAUUSD", True)] == ("unverifiable", "sl")  # no stored candles
            assert rows[("ZZBTCUSDT", False)][0] == "tp1"  # Binance price, untouched
            assert rows[("ZZFLAT", False)][0] == "tp1"  # labelled after the fix, untouched
            assert pred == "sl"

            again = await m.run(_PG_DSN, since=datetime(2026, 11, 1), until=datetime(2026, 11, 4, 7), apply=True,
                                batch=100, id_window=1_000_000, all_assets=False, out=lambda *_: None)
            assert again.get("scanned", 0) == 0  # idempotent
        finally:
            async with engine.begin() as conn:
                await conn.execute(text("DELETE FROM ml_shadow_predictions WHERE meta::jsonb->>'test_case' = 'stale_tick'"))
                await conn.execute(text("DELETE FROM decision_log WHERE asset LIKE 'ZZ%'"))
                await conn.execute(text("DELETE FROM market_candles WHERE symbol LIKE 'ZZ%'"))
            await engine.dispose()

    _run(scenario())
