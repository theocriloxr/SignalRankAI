"""Asset-class specialists (owner: "different strategies work for different assets in different asset
classes; keep the gates"). Each specialist must pass the unchanged promotion gate on its own class."""
from __future__ import annotations

import numpy as np
import pytest
from pathlib import Path
import pandas as pd

from ml import specialists


def _data(n=2400, seed=3):
    rng = np.random.default_rng(seed)
    cls = np.repeat([0.0, 1.0], n // 2)
    strat = rng.integers(0, 4, size=n).astype(float)
    noise = rng.normal(size=n)
    # crypto: strategy 2 works; fx: strategy 1 works — the global mix blurs both
    edge = np.where(cls == 0, strat == 2, strat == 1).astype(float)
    y = ((edge * 1.4 + rng.normal(scale=1.0, size=n)) > 0.7).astype(int)
    X = pd.DataFrame({"asset_class_enc": cls, "strategy_enc": strat, "noise": noise,
                      "risk_reward_ratio": rng.uniform(1, 3, size=n)})
    ts = pd.Series(pd.date_range("2026-08-01", periods=n, freq="h"))
    return X, pd.Series(y), ts


def test_each_class_gets_its_own_model_and_gate_verdict(monkeypatch):
    monkeypatch.setenv("ML_SPECIALIST_MIN_ROWS", "600")
    X, y, ts = _data()
    results = specialists.train_specialists(X, y, list(X.columns), timestamps=ts, deployed_runtime=False)
    assert set(results) == {"0", "1"}
    for r in results.values():
        assert r["rows"] == 1200 and r["reason"] in {"passed", "quality_gate", "calibration"}
        assert r["metrics"]["auc"] > 0.6  # each class's own pattern is learnable on its held-out window
    summary = specialists.summary(results)
    assert set(summary) == {"crypto", "fx"} and all("overfit_gap" in v for v in summary.values())


def test_router_uses_the_specialist_for_its_class_only(monkeypatch):
    monkeypatch.setenv("ML_SPECIALIST_MIN_ROWS", "600")
    X, y, ts = _data()
    results = specialists.train_specialists(X, y, list(X.columns), timestamps=ts, deployed_runtime=False)
    for r in results.values():
        r["passed"] = True  # exercise routing regardless of the synthetic gate verdict
    router = specialists.Router(specialists.payload(results))
    assert router.route({"asset_class_enc": 0.0})["name"] == "crypto"
    assert router.route({"asset_class_enc": 3.0}) is None  # no specialist: the global model scores it
    raw, calibrated = router.predict(router.route({"asset_class_enc": 1.0}),
                                     {"asset_class_enc": 1.0, "strategy_enc": 1.0, "noise": 0.0, "risk_reward_ratio": 2})
    assert 0.0 <= raw <= 1.0 and 0.0 <= calibrated <= 1.0


def test_too_small_classes_are_skipped(monkeypatch):
    monkeypatch.setenv("ML_SPECIALIST_MIN_ROWS", "5000")
    X, y, ts = _data()
    results = specialists.train_specialists(X, y, list(X.columns), timestamps=ts)
    assert all(r["reason"] == "too_few_rows" and not r["passed"] for r in results.values())
    assert specialists.payload(results) == {}


def test_serving_and_shadow_scoring_route_through_specialists():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    assert "self.specialists = Router(" in (root / "ml" / "inference.py").read_text("utf-8")
    assert '_SHADOW_CACHE["router"] = Router(' in (root / "engine" / "ml.py").read_text("utf-8")
    assert "specialist_payload or None" in (root / "ml" / "train_model.py").read_text("utf-8")


def test_replay_rows_carry_the_same_macro_trends_as_live_scoring():
    import pandas as pd

    from ml import external_replay as er

    idx = pd.date_range("2026-01-01", periods=300, freq="D", tz="UTC")
    closes = pd.Series([100.0 + i for i in range(300)], index=idx)
    when = pd.Timestamp("2026-08-01 12:00", tz="UTC")
    trend = er.macro_trend_at(closes, when, 200)
    end = closes.index.searchsorted(when.normalize())
    assert trend == pytest.approx(closes.iloc[end - 1] / closes.iloc[end - 200] - 1)  # earlier days only
    rows = [{"created_at": when.tz_convert(None).to_pydatetime(), "dxy_trend": 0.0}]
    assert er.fill_macro(rows, {"dxy_trend": closes}) == 1 and rows[0]["dxy_trend"] == pytest.approx(trend)
    core = (Path(__file__).resolve().parents[1] / "engine" / "core.py").read_text("utf-8")
    assert 'closes = closes[-_bars:]' in core  # live uses the same trailing window


def test_training_rows_use_the_live_asset_class_encoding():
    from ml.features import live_asset_class_enc

    assert live_asset_class_enc("BTCUSDT") == 0.0 and live_asset_class_enc("EURUSD") == 1.0
    assert live_asset_class_enc("XAUUSD") in {1.0, 2.0}  # the engine's own predicates decide
    assert live_asset_class_enc("AAPL") == 3.0
    root = Path(__file__).resolve().parents[1]
    assert "live_asset_class_enc(a)" in (root / "ml" / "train_model.py").read_text("utf-8")
    assert "live_asset_class_enc(asset)" in (root / "ml" / "external_replay.py").read_text("utf-8")


def test_crypto_history_falls_back_to_okx_when_binance_is_unreachable(monkeypatch):
    import time as _time

    from ml import strategy_discovery as sd

    now = int(_time.time() * 1000)

    class _Resp:
        def __init__(self, code, body):
            self.status_code, self._body = code, body

        def json(self):
            return self._body

    class _Client:
        calls: list = []

        def get(self, url, params=None):
            self.calls.append(url)
            if "binance" in url:
                return _Resp(451, {})
            after = (params or {}).get("after") or now
            bar = 3_600_000 if params["bar"] == "1H" else 900_000 if params["bar"] == "15m" else 300_000
            data = [[str(after - (i + 1) * bar), "1", "2", "0.5", "1.5", "10", "0", "0", "1" if i else "0"]
                    for i in range(100)]
            return _Resp(200, {"data": data})

    monkeypatch.setenv("DISCOVERY_OKX_MAX_PAGES", "3")
    monkeypatch.setattr(sd.time, "sleep", lambda *_: None)
    frames, source = sd.load_history("BTCUSDT", "crypto", _Client())
    assert source == "okx" and len(frames["1h"]) >= 290 and {"4h", "1d"} <= set(frames)
    assert sd.okx_inst_id("ETHUSDT") == "ETH-USDT" and sd.okx_inst_id("EURUSD") is None
