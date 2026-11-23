"""Trade reviews and lessons (ml/trade_review.py, 23 Nov 2026)."""
from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

from ml import trade_review as tr


def _row(i, *, win, trend, news=0.0, asset="EURUSD", strategy="EMA Trend", days_ago=60):
    entry = 1.10
    return {
        "signal_id": f"s{i}", "asset": asset, "timeframe": "15m", "direction": "long", "strategy_name": strategy,
        "regime": "trending", "entry": entry, "stop_loss": entry - 0.001, "take_profit": entry + 0.002,
        "mtf_4h_trend": trend, "mtf_1d_trend": 0.0, "adx": 25.0, "relative_volume": 1.0, "atr_regime": 1.0,
        "minutes_until_high_impact_news": news, "minutes_since_high_impact_news": 0.0,
        "created_at": datetime(2026, 11, 20, 9, 0) - timedelta(days=days_ago, minutes=i),
        "target": 1 if win else 0, "source_type": "live_delivery",
    }


def _history(seed=3, n=400):
    rng = random.Random(seed)
    rows = []
    for i in range(n):
        against = i % 2 == 1
        win_p = 0.15 if against else 0.55   # against the 4h trend loses money at 2R
        rows.append(_row(i, win=rng.random() < win_p, trend=-1.0 if against else 1.0))
    return rows


def test_realised_r_uses_tp1_geometry():
    assert abs(tr.realised_r(_row(0, win=True, trend=1.0)) - 2.0) < 1e-6
    assert tr.realised_r(_row(0, win=False, trend=1.0)) == -1.0
    assert tr.realised_r({**_row(0, win=True, trend=1.0), "target": None}) is None


def test_factors_read_context_without_guessing():
    f = tr.factors(_row(0, win=True, trend=-1.0, news=30.0))
    assert f["trend_4h"] == "against" and f["news"] == "before_release" and f["session"] == "london"
    assert "trend_1d" not in f  # 0 means unknown, not "against"


def test_lessons_find_the_real_effect_and_gate_it():
    snap = tr.build_snapshot(_history(), now=datetime(2026, 11, 23, tzinfo=timezone.utc))
    against = [t for t in snap["factors"] if t["asset_class"] == "forex" and t["factor"] == "trend_4h"
               and t["value"] == "against"][0]
    assert against["edge_r"] < 0 and against["q"] <= tr.GATE_Q
    assert any(t["factor"] == "trend_4h" and t["value"] == "against" for t in snap["harmful"])
    lesson = tr.harmful_lesson(snap, _row(999, win=True, trend=-1.0))
    assert lesson and lesson["factor"] == "trend_4h"
    assert tr.harmful_lesson(snap, _row(999, win=True, trend=1.0)) is None
    assert "4h trend" in tr.lessons_text(snap)


def test_no_lessons_from_noise():
    rng = random.Random(11)
    rows = [_row(i, win=rng.random() < 0.4, trend=rng.choice([-1.0, 1.0])) for i in range(400)]
    snap = tr.build_snapshot(rows, now=datetime(2026, 11, 23, tzinfo=timezone.utc))
    assert snap["harmful"] == []


def test_gate_never_targets_a_whole_class_or_strategy():
    rows = [_row(i, win=False, trend=1.0, asset="EURUSD", strategy="Bad") for i in range(120)] + \
           [_row(500 + i, win=i % 2 == 0, trend=1.0, asset="EURUSD", strategy="Good") for i in range(120)]
    snap = tr.build_snapshot(rows, now=datetime(2026, 11, 23, tzinfo=timezone.utc))
    assert any(t["factor"] == "strategy" for t in snap["lessons"])
    assert all(t["factor"] in tr.GATE_FACTORS for t in snap["harmful"])


def test_review_explains_and_advises():
    snap = tr.build_snapshot(_history(), now=datetime(2026, 11, 23, tzinfo=timezone.utc))
    loss = tr.review_trade(_row(1, win=False, trend=-1.0), snap)
    assert loss["realised_r"] == -1.0 and any("4h trend" in w for w in loss["why"])
    assert any("direction of the 4h trend" in a for a in loss["improve"])
    win = tr.review_trade(_row(2, win=True, trend=1.0), snap)
    assert "Worked" in win["headline"] and any("4h trend with" in w for w in win["why"])
    assert "Why it worked" in tr.review_text(win)
    assert snap["reviews"] and "text" in next(iter(snap["reviews"].values()))


def test_setup_trend_detects_improvement():
    rng = random.Random(5)
    rows = [_row(i, win=rng.random() < 0.2, trend=1.0, days_ago=90) for i in range(80)] + \
           [_row(200 + i, win=rng.random() < 0.7, trend=1.0, days_ago=5) for i in range(80)]
    snap = tr.build_snapshot(rows, now=datetime(2026, 11, 23, tzinfo=timezone.utc))
    assert snap["trends"] and snap["trends"][0]["direction"] == "improving"


def test_engine_and_bot_are_wired():
    from pathlib import Path

    engine = Path("engine/core.py").read_text()
    assert "harmful_lesson(load_snapshot_sync()" in engine and 'LESSON_GATE_ENABLED' in engine
    bot = Path("signalrank_telegram/bot.py").read_text()
    assert 'CommandHandler("lessons"' in bot and 'CommandHandler("why"' in bot and "OUTCOME_WHY_LINE_ENABLED" in bot
    assert "trade_review_loop" in Path("runtime/analytics.py").read_text()
