"""Per-asset strategy scorecard learned from issued and shadow outcomes (2 Nov 2026)."""
from __future__ import annotations

import json

import pytest

from services import strategy_scorecard as sc


def _rows(asset, tf, strategy, direction, wins, losses, win_r=2.0, source="shadow"):
    return [
        {"asset": asset, "timeframe": tf, "strategy": strategy, "direction": direction, "r": win_r, "source": source}
        for _ in range(wins)
    ] + [
        {"asset": asset, "timeframe": tf, "strategy": strategy, "direction": direction, "r": -1.0, "source": source}
        for _ in range(losses)
    ]


def test_outcome_r_uses_the_target_actually_reached():
    # long, entry 100, stop 99, targets 102/103/105
    assert sc.outcome_r("long", 100, 99, [102, 103, 105], "tp1") == pytest.approx(2.0)
    assert sc.outcome_r("long", 100, 99, "[102, 103, 105]", "tp3") == pytest.approx(5.0)
    assert sc.outcome_r("short", 100, 101, [98], "tp2") == pytest.approx(2.0)
    assert sc.outcome_r("long", 100, 99, [102], "sl") == -1.0
    assert sc.outcome_r("long", 100, 99, [102], "ambiguous") == -1.0
    assert sc.outcome_r("long", 100, 100, [102], "tp1") is None  # degenerate stop
    assert sc.outcome_r("long", 100, 99, [102], "expired") is None


def test_strategy_is_scored_per_asset():
    rows = _rows("BTCUSDT", "4h", "EMA Trend", "long", 60, 40) + _rows("XRPUSDT", "5m", "EMA Trend", "long", 10, 90)
    card = sc.build_scorecard(rows)
    btc = sc.lookup(card, asset="BTCUSDT", timeframe="4h", strategy="EMA Trend", direction="long", asset_class="crypto")
    xrp = sc.lookup(card, asset="XRPUSDT", timeframe="5m", strategy="EMA Trend", direction="long", asset_class="crypto")
    assert btc["scope"] == "asset_tf_dir" and btc["multiplier"] > 1.0
    assert xrp["scope"] == "asset_tf_dir" and xrp["multiplier"] < 1.0
    assert 0.85 <= xrp["multiplier"] < 1.0 < btc["multiplier"] <= 1.15


def test_thin_or_undecided_evidence_never_moves_the_score():
    thin = sc.build_scorecard(_rows("ETHUSDT", "1h", "Breakout", "short", 8, 4))
    assert sc.lookup(thin, asset="ETHUSDT", timeframe="1h", strategy="Breakout", direction="short",
                     asset_class="crypto")["multiplier"] == 1.0
    # 34% wins at 2R is right at break-even (33%): undecided.
    even = sc.build_scorecard(_rows("ETHUSDT", "1h", "Breakout", "short", 34, 66))
    result = sc.lookup(even, asset="ETHUSDT", timeframe="1h", strategy="Breakout", direction="short",
                       asset_class="crypto")
    assert result["multiplier"] == 1.0 and result["reason"] == "undecided"


def test_falls_back_to_broader_scope_when_the_asset_is_new():
    card = sc.build_scorecard(_rows("BTCUSDT", "1h", "VWAP", "long", 70, 30) + _rows("ETHUSDT", "1h", "VWAP", "long", 70, 30))
    result = sc.lookup(card, asset="SOLUSDT", timeframe="1h", strategy="VWAP", direction="long", asset_class="crypto")
    assert result["scope"] == "class_tf" and result["multiplier"] > 1.0


def test_issued_outcomes_weigh_more_than_shadow():
    card = sc.build_scorecard(_rows("EURUSD", "1h", "Mean Reversion", "short", 5, 5, source="issued"), issued_weight=3)
    cell = card["cells"]["asset_tf_dir"]["EURUSD|1h|mean reversion|short"]
    assert cell["n"] == 30 and cell["issued"] == 10


def test_modes(monkeypatch):
    card = sc.build_scorecard(_rows("BTCUSDT", "4h", "EMA Trend", "long", 70, 30))
    monkeypatch.setattr(sc, "_load_cached", lambda: card)
    sig = {"asset": "BTCUSDT", "timeframe": "4h", "strategy_name": "EMA Trend", "direction": "LONG",
           "asset_class": "crypto"}
    monkeypatch.setenv("STRATEGY_SCORECARD_MODE", "shadow")
    shadow = sc.scorecard_adjustment(sig)
    assert shadow["multiplier"] > 1.0 and shadow["applied"] is False
    monkeypatch.setenv("STRATEGY_SCORECARD_MODE", "apply")
    assert sc.scorecard_adjustment(sig)["applied"] is True
    monkeypatch.setenv("STRATEGY_SCORECARD_MODE", "off")
    assert sc.scorecard_adjustment(sig) == {"mode": "off", "multiplier": 1.0, "applied": False}


def test_scorecard_is_json_serialisable():
    card = sc.build_scorecard(_rows("NVDA", "1h", "Breakout", "long", 30, 20))
    assert json.loads(json.dumps(card))["rows_used"] == 50


def test_missing_scorecard_is_neutral(monkeypatch):
    monkeypatch.setattr(sc, "_load_cached", lambda: None)
    monkeypatch.setenv("STRATEGY_SCORECARD_MODE", "apply")
    result = sc.scorecard_adjustment({"asset": "BTCUSDT", "timeframe": "1h", "strategy_name": "X", "direction": "long"})
    assert result["multiplier"] == 1.0 and result["applied"] is False


def test_market_breaker_scope_defaults_to_crypto(monkeypatch):
    from engine import core as engine_core

    monkeypatch.delenv("MARKET_CIRCUIT_BREAKER_SCOPE", raising=False)
    assert engine_core._market_breaker_scope() == "crypto"
    monkeypatch.setenv("MARKET_CIRCUIT_BREAKER_SCOPE", "all")
    assert engine_core._market_breaker_scope() == "all"
    assert engine_core._is_crypto_symbol("BTCUSDT")
    assert not engine_core._is_crypto_symbol("EURUSD")
    src = open(engine_core.__file__, encoding="utf-8").read()
    assert "assets = [a for a in assets if not _is_crypto_symbol(a)]" in src


def test_repeated_logs_of_one_setup_in_one_bar_count_once():
    from datetime import datetime

    base = datetime(2026, 10, 30, 8, 0)
    # 300 identical rejected rows inside one 4h bar (re-scans) plus 50 distinct bars.
    storm = [
        {"asset": "XAGUSD", "timeframe": "4h", "strategy": "EMA Trend", "direction": "long", "r": -1.0,
         "source": "shadow", "bar": sc.bar_index(base.replace(minute=i % 60), "4h")}
        for i in range(300)
    ]
    distinct = [
        {"asset": "XAGUSD", "timeframe": "4h", "strategy": "EMA Trend", "direction": "long",
         "r": 2.0 if i % 2 else -1.0, "source": "shadow", "bar": 1000 + i}
        for i in range(50)
    ]
    card = sc.build_scorecard(storm + distinct)
    cell = card["cells"]["asset_tf_dir"]["XAGUSD|4h|ema trend|long"]
    assert cell["n"] == 51
    assert card["duplicates_skipped"] == 299
    # A short in the same bar and an issued outcome are separate opportunities.
    extra = [dict(storm[0], direction="short"), dict(storm[0], source="issued")]
    assert sc.build_scorecard(storm + extra, issued_weight=1)["rows_used"] == 3


def test_bar_index_uses_the_timeframe():
    from datetime import datetime

    assert sc.bar_index(datetime(2026, 11, 2, 3, 59), "4h") == sc.bar_index(datetime(2026, 11, 2, 0, 1), "4h")
    assert sc.bar_index(datetime(2026, 11, 2, 4, 0), "4h") != sc.bar_index(datetime(2026, 11, 2, 3, 59), "4h")
    assert sc.bar_index(None, "1h") is None
