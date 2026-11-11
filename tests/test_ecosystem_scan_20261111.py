"""Fixes from the 11 Nov 2026 ecosystem scan."""
from __future__ import annotations

import asyncio
import contextlib
import json

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
    se._HOURS_CACHE.clear()
    count = asyncio.run(se.refresh_once())
    assert count == 1
    assert calls["window"] in (25, 26)  # 24-25 hour-aligned windows + one retry
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


def test_settled_hours_are_read_once_and_reused(monkeypatch):
    """A refresh after the first reads only the recent (unsettled) hours."""
    import db.session as db_session
    from services import segment_evidence as se

    monkeypatch.setenv("SEGMENT_EVIDENCE_LOOKBACK_DAYS", "4")
    monkeypatch.setenv("SEGMENT_EVIDENCE_SETTLED_HOURS", "24")
    reads = {"n": 0}
    stored = {}

    class _Result:
        def __init__(self, rows):
            self._rows = rows

        def all(self):
            return self._rows

        def scalar_one_or_none(self):
            return None

    class _Session:
        async def execute(self, stmt, params=None):
            sql = str(stmt)
            if "ml_rejected_signals" in sql:
                reads["n"] += 1
                return _Result([("BTCUSDT", "5m", "ema trend", "long", reads["n"], "tp1"),
                                ("BTCUSDT", "4h", "ema trend", "long", 7, "sl")])
            if "INSERT INTO runtime_state" in sql:
                stored[params.get("key") or params.get("k")] = params.get("value") or params.get("v")
            return _Result([])

        async def commit(self):
            return None

        async def rollback(self):
            return None

    @contextlib.asynccontextmanager
    async def fake_get_session(**_kwargs):
        yield _Session()

    monkeypatch.setattr(db_session, "get_session", fake_get_session)
    se._HOURS_CACHE.clear()
    asyncio.run(se.refresh_once())
    first = reads["n"]
    asyncio.run(se.refresh_once())
    second = reads["n"] - first
    assert first >= 96 and second <= 26  # only the last ~24 hours re-read
    assert se.HOURS_CACHE_KEY in stored
    snapshot = json.loads(stored[se.SNAPSHOT_KEY])
    # one 4h bar seen in every hour still counts once; every 5m bar counts
    assert snapshot["segments"]["ema trend|4h|long"]["n"] == 1
    assert snapshot["segments"]["ema trend|5m|long"]["n"] == first


def test_ml_gate_mode_defaults_to_auto_and_keeps_the_evidence_guard(monkeypatch):
    from engine.core import _evidence_filter_required, _ml_gate_advisory, _ml_gate_mode

    monkeypatch.delenv("ML_GATE_MODE", raising=False)
    assert _ml_gate_mode() == "auto"
    assert _ml_gate_advisory() and _evidence_filter_required()
    monkeypatch.setenv("ML_GATE_MODE", "enforce")
    assert _ml_gate_mode() == "enforce" and not _ml_gate_advisory()
    monkeypatch.setenv("ML_GATE_MODE", "nonsense")
    assert _ml_gate_mode() == "auto"


def test_uncertified_ml_probability_neither_vetoes_nor_moves_the_score():
    from engine.scoring import score_signal

    base = {"asset": "EURUSD", "entry": 1.10, "stop_loss": 1.09, "take_profit": [1.13], "confidence": 0.8,
            "confluence": 70.0, "ml_probability": 0.01}
    vetoed = score_signal(dict(base))
    observed = score_signal(dict(base, ml_uncertified=True))
    without_ml = score_signal({k: v for k, v in base.items() if k != "ml_probability"})
    assert observed == without_ml and observed > 0
    assert vetoed < observed  # a 0.01 uncertified probability no longer drags the score


def test_scorer_names_the_check_behind_a_zero_score():
    from engine.scoring import score_signal
    from engine.ultra_quality_filter import UltraQualityFilter

    sig = {"asset": "EURUSD", "entry": 1.10, "stop_loss": 1.09, "take_profit": [1.13], "confidence": 0.1,
           "confluence": 70.0}
    sig["score"] = score_signal(sig)
    assert sig["score"] == 0.0 and sig["score_rejection"].startswith("confidence 0.10")
    ok, reason, _ = UltraQualityFilter().apply_ultra_filter(sig)
    assert not ok and reason == f"Score 0.0 ({sig['score_rejection']})"


def test_one_training_row_per_setup_per_bar(monkeypatch):
    from engine import signal_deduplicator as sd

    sd._REJECTION_BAR_SEEN.clear()
    f = {"strategy_name": "EMA Trend"}
    assert sd._first_rejection_of_bar("BTCUSDT", "5m", "long", f)
    assert not sd._first_rejection_of_bar("btcusdt", "5m", "LONG", f)  # same setup, same bar
    assert sd._first_rejection_of_bar("BTCUSDT", "5m", "short", f)
    assert sd._first_rejection_of_bar("BTCUSDT", "1h", "long", f)
    assert sd._first_rejection_of_bar("BTCUSDT", "5m", "long", {"strategy_name": "ADX Trend"})
    monkeypatch.setenv("SHADOW_REJECTION_DEDUP_ENABLED", "false")
    assert sd._first_rejection_of_bar("BTCUSDT", "5m", "long", f)
    sd._REJECTION_BAR_SEEN.clear()


def test_data_audit_flags_leakage_label_noise_and_collinearity():
    import numpy as np
    import pandas as pd

    from ml.data_audit import audit, blocks_promotion

    rng = np.random.default_rng(7)
    n = 1000
    y = rng.integers(0, 2, n)
    frame = pd.DataFrame({"noise": rng.normal(size=n), "const": np.ones(n)})
    frame["twin"] = frame["noise"] * 2.0
    clean = audit(frame, y, list(frame.columns))
    assert clean["leak_suspects"] == [] and blocks_promotion(clean) == []
    assert clean["constant_features"] == ["const"]
    assert clean["collinear_pairs"][0][:2] == ["noise", "twin"]
    assert len(clean["dataset_hash"]) == 16

    leaky = frame.assign(future=y + rng.normal(scale=0.05, size=n))
    report = audit(leaky, y, list(leaky.columns))
    assert report["leak_suspects"][0][0] == "future"
    assert blocks_promotion(report)[0].startswith("leak_suspects:future")

    noisy = pd.DataFrame({"a": np.zeros(400), "b": np.zeros(400)})
    labels = np.array([0, 1] * 200)
    noisy_report = audit(noisy, labels, ["a", "b"])
    assert noisy_report["label_conflict_share"] == 1.0
    assert any(r.startswith("label_conflict_share") for r in blocks_promotion(noisy_report))


def test_champion_comparison_uses_pr_auc_lift_not_raw_pr_auc(tmp_path, monkeypatch):
    """11 Nov 2026: 0.57 PR-AUC at a 19 % win rate (lift 2.95) was rejected against 0.84."""
    from ml.train_model import EXPECTED_R_BASIS_TP1, _champion_comparison_gate

    monkeypatch.setenv("ML_CHAMPION_COMPARISON_ENABLED", "true")
    base = {"auc": 0.85, "balanced_accuracy": 0.63, "expected_r": 0.40, "expected_r_basis": EXPECTED_R_BASIS_TP1}
    candidate = dict(base, pr_auc=0.5734, positive_rate=0.1942)
    champion = dict(base, auc=0.834, pr_auc=0.8355, positive_rate=0.55)  # lift 1.52
    ok, evidence = _champion_comparison_gate(candidate, tmp_path / "x.json", champion_metrics=champion)
    assert ok, evidence
    assert "pr_auc" not in evidence["compared"] and "pr_auc_lift" in evidence["compared"]

    weaker = dict(base, pr_auc=0.25, positive_rate=0.1942)  # lift 1.29 < 1.52 * 0.9
    ok, evidence = _champion_comparison_gate(weaker, tmp_path / "x.json", champion_metrics=champion)
    assert not ok and "pr_auc_lift" in evidence["regressions"]

    no_rate = {k: v for k, v in champion.items() if k != "positive_rate"}
    ok, evidence = _champion_comparison_gate(candidate, tmp_path / "x.json", champion_metrics=no_rate)
    assert "pr_auc" not in evidence["compared"] and "pr_auc_lift" not in evidence["compared"]


def test_embargoed_windows_keep_their_size_and_never_fall_back_to_a_leaky_split():
    import numpy as np
    import pandas as pd
    import pytest

    from ml.train_model import _embargoed_windows

    # 1,000 rows, most of them in the last two days (as production clusters).
    old = pd.date_range("2026-08-15", periods=300, freq="6h")
    recent = pd.date_range("2026-11-09", periods=700, freq="4min")
    ts = pd.Series(old.append(recent))
    idx = np.arange(len(ts))
    tr, cal, te = _embargoed_windows(idx[:700], idx[700:850], idx[850:], ts, 24.0,
                                     minimum_fit=50, minimum_calibration=30)
    assert len(te) == 150 and len(cal) == 150  # sizes kept, not purged away
    gap = pd.Timedelta(hours=24)
    assert ts.iloc[cal].max() <= ts.iloc[te].min() - gap
    assert ts.iloc[tr].max() <= ts.iloc[cal].min() - gap
    assert not set(tr) & set(cal) and not set(cal) & set(te)

    dense = pd.Series(pd.date_range("2026-11-10", periods=300, freq="1min"))  # five hours of rows
    with pytest.raises(ValueError, match="insufficient_rows_after_embargo"):
        _embargoed_windows(np.arange(200), np.arange(200, 250), np.arange(250, 300), dense, 24.0,
                           minimum_fit=50, minimum_calibration=30)
