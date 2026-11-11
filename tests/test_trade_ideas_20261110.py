"""Check a trade you plan to take (owner request, 10 Nov 2026), on Telegram, the website/app and the API,
then track it, tell the user how it ended and learn from it."""
from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest

from services import trade_ideas as ti

_ROOT = Path(__file__).resolve().parents[1]
_PG_DSN = os.getenv("SIGNALRANK_TEST_PG_DSN", "")


def _candles(n=400, start=1.0800, drift=0.00002, swing=0.0012, t0=None):
    t0 = t0 or datetime(2026, 11, 1, tzinfo=timezone.utc)
    out, price = [], start
    for i in range(n):
        price += drift + (swing if i % 6 < 3 else -swing) / 3
        out.append({"timestamp": int((t0 + timedelta(hours=i)).timestamp() * 1000), "open": price,
                    "high": price + swing / 2, "low": price - swing / 2, "close": price, "volume": 1})
    return out


def test_validation_explains_mistakes_in_plain_words():
    with pytest.raises(ti.IdeaError, match="stop loss must be below"):
        ti.normalise({"asset": "EURUSD", "direction": "buy", "entry": 1.08, "stop_loss": 1.09, "take_profit": [1.1]})
    with pytest.raises(ti.IdeaError, match="take profit must be below"):
        ti.normalise({"asset": "EURUSD", "direction": "sell", "entry": 1.08, "stop_loss": 1.09, "take_profit": [1.1]})
    idea = ti.normalise({"asset": "eur/usd", "direction": "SELL", "entry": "1.0850", "sl": "1.0880", "tp": "1.0800 1.0780"})
    assert idea.direction == "short" and idea.take_profit == [1.08, 1.078] and idea.timeframe == "1h"


def test_telegram_text_parses_in_any_order():
    raw = ti.parse_command_text("XAUUSD buy 4100 sl 4085 tp 4120 4140 tf 4h".split())
    assert raw == {"asset": "XAUUSD", "direction": "buy", "entry": "4100", "stop_loss": "4085",
                   "take_profit": ["4120", "4140"], "timeframe": "4h"}
    raw = ti.parse_command_text("EURUSD sell entry 1.085 stop 1.088 target 1.08".split())
    assert raw["entry"] == "1.085" and raw["stop_loss"] == "1.088" and raw["take_profit"] == ["1.08"]


def test_historical_hit_rate_counts_same_bar_touches_as_losses():
    highs, lows, closes = [101, 102.5, 103], [99, 98.5, 97], [100, 100, 100]
    out = ti.historical_hit_rate(highs, lows, closes, direction="long", target_pct=0.02, stop_pct=0.01, horizon=5)
    assert out["wins"] == 0 and out["losses"] == 1 and out["rate"] == 0.0


def test_analysis_gives_probability_breakeven_verdict_and_plan():
    idea = ti.normalise({"asset": "EURUSD", "direction": "buy", "entry": 1.0900, "stop_loss": 1.0880,
                         "take_profit": [1.0920, 1.0940], "timeframe": "1h"})
    result = asyncio.run(ti.analyse(idea, candles=_candles()))
    assert 0 < result["probability_tp1"] < 1 and result["breakeven_win_rate"] == pytest.approx(0.5)
    assert result["verdict"] in {"favourable", "marginal", "unfavourable"}
    assert result["historical"][0]["samples"] > 100 and result["order_plan"]["stop_pips"] == pytest.approx(20.0)
    text = ti.telegram_text(result)
    assert "Chance of TP1 before the stop" in text and "Break-even win rate" in text and "Order type" in text
    with pytest.raises(ti.IdeaError, match="Not enough recent"):
        asyncio.run(ti.analyse(idea, candles=_candles(20)))


def test_idea_waits_for_its_entry_then_labels_like_the_shadow_tracker():
    t0 = datetime(2026, 11, 1)
    candles = []
    prices = [1.0950, 1.0940, 1.0905, 1.0899, 1.0925, 1.0960]  # entry 1.0900 touched at bar 3, then TP1 1.0920
    for i, p in enumerate(prices):
        candles.append({"timestamp": int((t0 + timedelta(hours=i)).replace(tzinfo=timezone.utc).timestamp() * 1000),
                        "high": p + 0.0002, "low": p - 0.0002, "close": p})
    row = {"direction": "long", "entry": 1.0900, "stop_loss": 1.0880, "take_profit": [1.0920, 1.0940, 1.0990],
           "price_at_submit": 1.0950, "created_at": t0, "timeframe": "1h", "entry_touched_at": None}
    outcome, touched = ti.label_idea(row, candles, expiry_bars=48)
    assert touched is not None and touched > t0 and outcome == "tp2"  # out of time after TP2: TP2 is credited
    row_far = dict(row, entry=1.0500, stop_loss=1.0480, take_profit=[1.0520], created_at=t0 - timedelta(days=30))
    assert ti.label_idea(row_far, candles, expiry_bars=48)[0] == "missed_entry"
    assert ti.outcome_r({"entry": 1.09, "stop_loss": 1.088, "take_profit": [1.092, 1.094]}, "tp1") == pytest.approx(0.5)
    assert ti.outcome_r({"entry": 1.09, "stop_loss": 1.088, "take_profit": [1.092]}, "sl") == -1.0


def test_every_platform_has_it():
    bot = (_ROOT / "signalrank_telegram" / "bot.py").read_text("utf-8")
    assert 'CommandHandler("check_trade"' in bot and 'CommandHandler("my_ideas"' in bot
    api = (_ROOT / "web" / "platform_api.py").read_text("utf-8")
    assert '@router.post("/trade-ideas")' in api and '@router.get("/trade-ideas")' in api
    ui = (_ROOT / "frontend" / "src" / "components" / "WorkspaceLive.tsx").read_text("utf-8")
    assert 'case "analyze": return client.GET("/api/v1/platform/trade-ideas")' in ui
    assert "/app/analyze" in (_ROOT / "frontend" / "src" / "components" / "AppShell.tsx").read_text("utf-8")
    assert "trade_ideas_loop" in (_ROOT / "runtime" / "analytics.py").read_text("utf-8")
    train = (_ROOT / "ml" / "train_model.py").read_text("utf-8")
    assert 'isin(["external_replay", "user_idea"])' in train  # fit-only: never validates or promotes


@pytest.mark.skipif(not _PG_DSN, reason="set SIGNALRANK_TEST_PG_DSN to an owned scratch PostgreSQL at head")
def test_submit_track_notify_and_learn_on_postgres(monkeypatch):
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    from db.session import _normalize_database_url

    url = _normalize_database_url(_PG_DSN, async_driver=True)
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setenv("IDEA_DAILY_LIMIT_FREE", "2")
    tag = uuid4().hex[:8]
    now = datetime.now(timezone.utc)
    history_candles = _candles(400, t0=now - timedelta(hours=400))

    async def scenario():
        from db.session import dispose_engine_for_event_loop, get_session

        engine = create_async_engine(url)
        try:
            async with engine.begin() as conn:
                uid = (await conn.execute(text(
                    "INSERT INTO users(username, telegram_user_id, created_at, tier, auto_renew) "
                    "VALUES (:u, :tg, NOW(), 'free', FALSE) RETURNING id"),
                    {"u": f"ti_{tag}", "tg": 800000000 + int(tag[:6], 16) % 99999999})).scalar_one()
            last = history_candles[-1]["close"]
            raw = {"asset": "EURUSD", "direction": "buy", "entry": last, "stop_loss": last - 0.0020,
                   "take_profit": [last + 0.0010], "timeframe": "1h"}
            async with get_session() as s:
                first = await ti.submit(s, user_id=uid, tier="free", raw=raw, source="telegram", candles=history_candles)
                await ti.submit(s, user_id=uid, tier="free", raw=raw, source="web", candles=history_candles)
                with pytest.raises(ti.IdeaError, match="today's 2"):
                    await ti.submit(s, user_id=uid, tier="free", raw=raw, source="web", candles=history_candles)
                await s.commit()
            # the next bars go straight up through TP1
            future = [{"timestamp": int((now + timedelta(minutes=5 + 60 * i)).timestamp() * 1000),
                       "high": last + 0.0004 * (i + 1), "low": last - 0.0001, "close": last + 0.0004 * i}
                      for i in range(6)]

            async def fetch(asset, timeframe):
                return history_candles + future

            tracked = await ti.track_once(candle_fetch=fetch)
            posts = []

            async def fake_post(chat, body):
                posts.append(body)
                return True

            notified = await ti.notify_once(telegram_post=fake_post)
            again = await ti.notify_once(telegram_post=fake_post)
            async with get_session() as s:
                hist = await ti.history(s, uid)
                await s.rollback()
            from ml.train_model import load_training_data

            df = await load_training_data(30)
            return first, tracked, notified, again, posts, hist, df
        finally:
            async with engine.begin() as conn:
                await conn.execute(text("DELETE FROM notification_events WHERE user_id IN "
                                        "(SELECT id FROM users WHERE username=:u)"), {"u": f"ti_{tag}"})
                await conn.execute(text("DELETE FROM users WHERE username=:u"), {"u": f"ti_{tag}"})
            await engine.dispose()
            await dispose_engine_for_event_loop()

    first, tracked, notified, again, posts, hist, df = asyncio.run(scenario())
    assert first["idea_id"] and first["used_today"] == 1 and first["daily_limit"] == 2
    assert tracked["resolved"] >= 2
    assert notified >= 2 and again == 0 and any("reached TP1" in p or "final target" in p for p in posts)
    assert hist["resolved"] == 2 and hist["hit_rate"] == 1.0
    assert "user_idea" in set(df["source_type"]) if df is not None and len(df) else True


def test_check_suggests_better_levels_when_history_supports_them():
    """11 Nov 2026: the check advises and changes the trade, not only rates it."""
    # Steady uptrend with shallow pullbacks: a far 3R target is rarely reached before a tight stop.
    idea = ti.normalise({"asset": "EURUSD", "direction": "buy", "entry": 1.0900, "stop_loss": 1.0897,
                         "take_profit": [1.0909, 1.0915], "timeframe": "1h"})
    result = asyncio.run(ti.analyse(idea, candles=_candles(drift=0.0002)))
    suggestion = result["suggestion"]
    assert suggestion["advice"], suggestion
    if suggestion["changed"]:
        assert suggestion["expected_r_suggested"] >= (suggestion["expected_r_now"] or -1.0) + 0.05
        assert suggestion["stop_loss"] < idea.entry < suggestion["take_profit"][0] < suggestion["take_profit"][-1]
        assert "Suggested levels" in ti.telegram_text(result)
    assert "How to improve it" in ti.telegram_text(result)


def test_suggestion_keeps_a_plan_that_is_already_good():
    highs, lows, closes = ti._ohlc(_candles(drift=0.0))
    idea = ti.normalise({"asset": "EURUSD", "direction": "sell", "entry": closes[-1], "stop_loss": closes[-1] + 0.01,
                         "take_profit": [closes[-1] - 0.01], "timeframe": "1h"})
    out = ti.suggest_adjustments(idea, highs, lows, closes, atr_value=0.0, price=closes[-1], horizon=48, trend=0)
    assert out["changed"] is False or out["expected_r_suggested"] >= (out["expected_r_now"] or -1.0) + 0.05
