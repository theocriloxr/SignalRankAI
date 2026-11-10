"""Why this rank, rank-change alerts and the daily top-3 teaser (owner: "build all that remains", 10 Nov 2026)."""
from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest

from engine.rank_factors import rank_factor_lines, rank_factors
from services.daily_teaser import day_key, due, teaser_text
from services.rank_alerts import alert_text, classify

_ROOT = Path(__file__).resolve().parents[1]
_PG_DSN = os.getenv("SIGNALRANK_TEST_PG_DSN", "")
_COMPONENTS = {
    "rr": {"value": 0.8, "weight": 0.2},
    "vol": {"value": 0.6, "weight": 0.1},
    "ml_probability": {"value": 0.64, "weight": 0.2},
    "confluence": {"value": 0.7, "weight": 0.15},
    "candle_evidence": {"value": 0.3, "weight": 0.1},
}


def test_factors_add_up_to_the_raw_weighted_score_and_group_into_sub_scores():
    info = rank_factors({"score_components": _COMPONENTS})
    total_weight = 0.75
    expected = sum(c["value"] * c["weight"] for c in _COMPONENTS.values()) / total_weight * 100
    assert info["raw_score"] == pytest.approx(expected, abs=0.3)
    assert info["factors"][0]["key"] == "rr" and info["weakest"] == "candle_evidence"
    assert info["sub_scores"]["Setup"] == pytest.approx((0.8 * 0.2 + 0.6 * 0.1) / 0.3 * 100, abs=0.1)
    assert info["sub_scores"]["Model"] == pytest.approx(64.0)
    assert rank_factors({}) is None and rank_factors({"score_components": "not json"}) is None


def test_card_lines_and_cards_show_why_this_rank():
    lines = rank_factor_lines({"score_components": _COMPONENTS})
    assert lines[0].startswith("🏅 Why this rank: Setup 73 • Technical 54 • Model 64")
    assert "Reward/risk 80 (+21.3)" in lines[1] and "weakest: Price action 30" in lines[1]
    from signalrank_telegram.tier_signal_formatter import format_premium_signal, format_vip_signal

    base = dict(asset="EURUSD", direction="long", entry=1.085, stop_loss=1.0825, take_profit=[1.09, 1.095],
                timeframe="1h", strategy_name="x", score=78, signal_id="abc", score_components=_COMPONENTS)
    vip, premium = format_vip_signal(dict(base)), format_premium_signal(dict(base))
    assert "Why this rank" in vip and "weakest: Price action" in vip
    assert "Why this rank" in premium and "weakest" not in premium


def test_issued_decision_keeps_components_and_api_returns_them():
    core = (_ROOT / "engine" / "core.py").read_text("utf-8")
    assert '"score_components": sig.get("score_components")' in core
    api = (_ROOT / "web" / "platform_api.py").read_text("utf-8")
    assert '"rank_factors": rank' in api and "decision='issued'" in api
    assert '@router.get("/public/daily-top")' in api
    ui = (_ROOT / "frontend" / "src" / "components" / "WorkspaceLive.tsx").read_text("utf-8")
    assert "<RankFactors rank=" in ui
    analytics = (_ROOT / "runtime" / "analytics.py").read_text("utf-8")
    assert "rank_alerts_loop" in analytics and "daily_teaser_loop" in analytics


@pytest.mark.parametrize("old_dir,old_score,new_dir,new_score,expected", [
    ("long", 70, "short", 72, "flip"),
    ("buy", 70, "long", 82, "upgrade"),
    ("short", 80, "sell", 69, "downgrade"),
    ("long", 70, "long", 75, None),
])
def test_rank_change_classification(old_dir, old_score, new_dir, new_score, expected):
    assert classify(old_dir, old_score, new_dir, new_score, delta=10) == expected


def test_alert_text_names_the_change_without_levels():
    title, body = alert_text("flip", {"asset": "XAUUSD", "old_direction": "long", "old_score": 74,
                                      "new_direction": "short", "new_score": 79, "old_id": "abcdef123456"})
    assert title == "Rank flip on XAUUSD" and "open BUY (74/100, ref abcdef12)" in body and "SELL setup ranked 79" in body


def test_teaser_text_and_schedule():
    text_ = teaser_text({"fx": [{"asset": "EURUSD", "side": "BUY", "timeframe": "1h", "score": 81.4}],
                         "crypto": [{"asset": "BTCUSDT", "side": "SELL", "timeframe": "4h", "score": 77}]})
    assert "FX: 1) EURUSD BUY 1h 81" in text_ and "Crypto: 1) BTCUSDT SELL 4h 77" in text_
    assert "not a chance of winning" in text_ and teaser_text({}) == ""
    noon = datetime(2026, 11, 10, 12, 5, tzinfo=timezone.utc)
    assert due(noon) and not due(noon.replace(hour=9)) and day_key(noon) == "daily_teaser:2026-11-10"


@pytest.mark.skipif(not _PG_DSN, reason="set SIGNALRANK_TEST_PG_DSN to an owned scratch PostgreSQL at head")
def test_rank_alert_and_daily_teaser_on_postgres(monkeypatch):
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    from db.session import _normalize_database_url

    url = _normalize_database_url(_PG_DSN, async_driver=True)
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setenv("DAILY_TEASER_MIN_AGE_MINUTES", "0")
    tag = uuid4().hex[:8]
    old_id, new_id, asset = f"ra-old-{tag}", f"ra-new-{tag}", f"RA{tag[:6].upper()}"
    noon = datetime.now(timezone.utc).replace(hour=13)

    async def scenario():
        from db.session import dispose_engine_for_event_loop
        from services import daily_teaser, rank_alerts

        engine = create_async_engine(url)
        try:
            async with engine.begin() as conn:
                await conn.execute(text("DELETE FROM runtime_state WHERE key=:k"), {"k": day_key(noon)})
                uid = (await conn.execute(text(
                    "INSERT INTO users(username, telegram_user_id, created_at, tier, auto_renew) "
                    "VALUES (:u, :tg, NOW(), 'free', FALSE) RETURNING id"),
                    {"u": f"ra_{tag}", "tg": 900000000 + int(tag[:6], 16) % 99999999})).scalar_one()
                for sid, direction, score, age in ((old_id, "long", 74, 180), (new_id, "short", 79, 1)):
                    await conn.execute(text(
                        "INSERT INTO signals (signal_id, asset, asset_class, timeframe, direction, entry, stop_loss,"
                        " take_profit, score, strategy_name, strategy_group, strength, created_at, display_id) VALUES"
                        " (:s,:a,'fx','1h',:d,1.1,1.09,'[1.12]',:sc,'x','trend',1,"
                        " (NOW() AT TIME ZONE 'utc') - make_interval(mins => :age),:disp)"),
                        {"s": sid, "a": asset, "d": direction, "sc": score, "age": age, "disp": sid[-10:]})
                await conn.execute(text(
                    "INSERT INTO signal_deliveries (signal_id, user_id, delivered_at, delivery_state, sent_ok) "
                    "VALUES (:s, :u, NOW(), 'confirmed', TRUE)"), {"s": old_id, "u": uid})
            posts = []

            async def fake_post(chat, message):
                posts.append((chat, message))
                return True

            first = await rank_alerts.run_once(telegram_post=fake_post)
            second = await rank_alerts.run_once(telegram_post=fake_post)
            teaser = await daily_teaser.publish_once(now=noon, telegram_post=fake_post)
            again = await daily_teaser.publish_once(now=noon, telegram_post=fake_post)
            async with engine.begin() as conn:
                kinds = [r[0] for r in (await conn.execute(text(
                    "SELECT channel_data->>'kind' FROM notification_events WHERE user_id=:u ORDER BY created_at"),
                    {"u": uid})).all()]
            return uid, first, second, teaser, again, kinds, posts
        finally:
            async with engine.begin() as conn:
                await conn.execute(text("DELETE FROM notification_events WHERE user_id IN "
                                        "(SELECT id FROM users WHERE username=:u)"), {"u": f"ra_{tag}"})
                await conn.execute(text("DELETE FROM runtime_state WHERE key=:k"), {"k": day_key(noon)})
                await conn.execute(text("DELETE FROM signal_deliveries WHERE signal_id IN (:a,:b)"), {"a": old_id, "b": new_id})
                await conn.execute(text("DELETE FROM signals WHERE signal_id IN (:a,:b)"), {"a": old_id, "b": new_id})
                await conn.execute(text("DELETE FROM users WHERE username=:u"), {"u": f"ra_{tag}"})
            await engine.dispose()
            await dispose_engine_for_event_loop()

    _uid, first, second, teaser, again, kinds, posts = asyncio.run(scenario())
    assert first["alerts"] >= 1 and first["telegram_sent"] >= 1
    assert second["alerts"] == 0  # sent once
    assert "rank_flip" in kinds
    assert teaser["status"] == "published" and again["status"] == "already_published"
    assert "daily_teaser" in kinds
    assert any(f"{asset} BUY" in message for _chat, message in posts if "top-ranked" in message)  # delivered only
