"""ML retraining starved of shadow evidence (production 10 Nov 2026, 14 h signal drought).

The champion was six weeks old and every training run ended "insufficient_total_rows":
one unbounded read of every tracked rejected setup could time out, and its failure
dropped all shadow evidence. The read is now keyset-batched, newest first, with a
cap, and a failed batch keeps the rows already read.
"""
from __future__ import annotations

import asyncio
import json
import os
from datetime import timedelta

import pytest

_PG_DSN = os.getenv("SIGNALRANK_TEST_PG_DSN", "")


@pytest.mark.skipif(not _PG_DSN, reason="set SIGNALRANK_TEST_PG_DSN to an owned scratch PostgreSQL at head")
def test_tracked_rejections_load_in_batches_newest_first_on_postgres(monkeypatch):
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    from db.session import _normalize_database_url
    from utils.timeutils import now_utc_naive

    url = _normalize_database_url(_PG_DSN, async_driver=True)
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setenv("ML_TRAIN_SHADOW_CHUNK_ROWS", "500")
    monkeypatch.setenv("ML_TRAIN_SHADOW_MAX_ROWS", "1000")

    async def scenario():
        from db.session import dispose_engine_for_event_loop
        from ml.train_model import _load_tracked_rejections

        engine = create_async_engine(url)
        try:
            async with engine.begin() as conn:
                await conn.execute(text("DELETE FROM decision_log WHERE asset='SHLOAD'"))
                for i in range(1200):
                    meta = {"layer": "ml", "direction": "long", "entry": "1.1", "stop_loss": "1.0",
                            "take_profit": "[1.2]", "ml_probability": "0.5", "actual_outcome": "tp1",
                            "outcome_tracked_at": "2026-11-10T00:00:00", "features": {"score": i}}
                    if i % 7 == 0:
                        meta.pop("outcome_tracked_at")  # untracked rows are skipped
                    await conn.execute(text(
                        "INSERT INTO decision_log(asset,timeframe,decision,reason,meta,created_at) VALUES "
                        "('SHLOAD','1h','rejected','x',CAST(:m AS JSONB),:t)"),
                        {"m": json.dumps(meta), "t": now_utc_naive() - timedelta(hours=1)})
            diag: dict = {}
            rows = await _load_tracked_rejections(now_utc_naive() - timedelta(days=1), diag)
            mine = [r for r in rows if r.asset == "SHLOAD"]
            return rows, mine, diag
        finally:
            async with engine.begin() as conn:
                await conn.execute(text("DELETE FROM decision_log WHERE asset='SHLOAD'"))
            await engine.dispose()
            await dispose_engine_for_event_loop()

    rows, mine, diag = asyncio.run(scenario())
    assert len(rows) == 1000 and diag["capped"] is True and diag["batches"] == 2 and diag["error"] is None
    ids = [r.id for r in rows]
    assert ids == sorted(ids, reverse=True)  # newest first
    assert mine and mine[0].actual_outcome == "tp1" and mine[0].entry == pytest.approx(1.1)
    assert isinstance(mine[0].features, dict) and "score" in mine[0].features


def test_a_failed_batch_keeps_rows_already_read(monkeypatch):
    from contextlib import asynccontextmanager
    from types import SimpleNamespace

    import ml.train_model as tm

    calls = {"n": 0}

    class _Result:
        def __init__(self, rows):
            self._rows = rows

        def mappings(self):
            return SimpleNamespace(all=lambda: self._rows)

    class _Session:
        async def execute(self, *_a, **_k):
            calls["n"] += 1
            if calls["n"] > 1:
                raise TimeoutError()
            return _Result([{"id": 10 - i, "asset": "X", "features": "{}", "entry": "1"} for i in range(500)])

    @asynccontextmanager
    async def fake_session(**_k):
        yield _Session()

    monkeypatch.setattr("db.session.get_session", fake_session)
    monkeypatch.setenv("ML_TRAIN_SHADOW_CHUNK_ROWS", "500")
    diag: dict = {}
    rows = asyncio.run(tm._load_tracked_rejections(None, diag))
    assert len(rows) == 500 and diag["error"] == "TimeoutError"


def test_training_is_regularised_and_reports_the_overfit_gap():
    """Owner request: fix overfitting. A noisy dataset must stop early and report its gap."""
    import numpy as np
    import pandas as pd

    from ml.train_model import _promotion_quality_gate, train_model

    rng = np.random.default_rng(7)
    n = 900
    X = pd.DataFrame({f"f{i}": rng.normal(size=n) for i in range(8)})
    y = pd.Series(((X["f0"] + rng.normal(scale=2.5, size=n)) > 0).astype(int))  # weak signal, lots of noise
    ts = pd.Series(pd.date_range("2026-08-01", periods=n, freq="h"))
    result = train_model(X, y, list(X.columns), timestamps=ts)
    metrics = result[-1]
    assert metrics["train_auc"] is not None and metrics["overfit_gap"] is not None
    assert metrics["trees_used"] is None or metrics["trees_used"] < 400  # early stopping engaged
    assert metrics["overfit_gap"] < 0.25  # regularised trees no longer memorise the noise
    overfit = dict(metrics, overfit_gap=0.4, auc=0.9, accuracy=0.9, balanced_accuracy=0.9, positive_recall=0.9,
                   pr_auc=0.9, positive_rate=0.5, expected_r=1.0)
    assert _promotion_quality_gate(overfit, deployed_runtime=False)[0] is False
    assert _promotion_quality_gate(dict(overfit, overfit_gap=0.05), deployed_runtime=False)[0] is True
