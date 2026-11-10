"""Order type and pip/risk breakdown (owner request, 10 Nov 2026).

"Add the type of trade / pending order (buy limit, sell limit, market, buy
stop, sell stop, buy stop limit, sell stop limit) and show how many pips a
trade is: total risk = stop loss (pips) x pip value x lot size."
"""
from __future__ import annotations

import pytest

from engine.order_plan import build_order_plan, order_plan_lines, order_type, pip_spec


@pytest.mark.parametrize("direction,entry,current,expected", [
    ("long", 100.0, 100.05, "Buy (market)"),
    ("long", 100.0, 101.0, "Buy Limit"),
    ("long", 100.0, 99.0, "Buy Stop"),
    ("short", 100.0, 99.0, "Sell Limit"),
    ("short", 100.0, 101.0, "Sell Stop"),
    ("short", 100.0, None, "Sell (market)"),
])
def test_order_type_follows_where_price_is(direction, entry, current, expected):
    assert order_type(direction, entry, current, risk=1.0)["type"] == expected


def test_stop_orders_offer_a_stop_limit_with_a_slippage_cap():
    buy = order_type("long", 100.0, 99.0, risk=2.0)["alternative"]
    sell = order_type("short", 100.0, 101.0, risk=2.0)["alternative"]
    assert buy["type"] == "Buy Stop Limit" and buy["trigger"] == 100.0 and buy["limit"] == pytest.approx(100.2)
    assert sell["type"] == "Sell Stop Limit" and sell["limit"] == pytest.approx(99.8)


def test_pip_conventions():
    assert pip_spec("EURUSD").pip == 0.0001 and pip_spec("USDJPY").pip == 0.01
    assert pip_spec("XAUUSD").pip == 0.1 and pip_spec("XAUUSD").contract == 100
    assert pip_spec("US30").unit == "points" and pip_spec("BTCUSDT").unit == "points"


def test_risk_equals_stop_pips_times_pip_value_times_lots():
    plan = build_order_plan(dict(asset="EURUSD", direction="long", entry=1.0850, stop_loss=1.0825,
                                 take_profit=[1.0900], current_price=1.0870), risk_amount=50.0)
    assert plan["stop_pips"] == pytest.approx(25.0) and plan["pip_value_usd"] == pytest.approx(10.0)
    assert plan["lots"] == pytest.approx(0.2) and plan["check"] == pytest.approx(50.0)
    assert plan["target_pips"] == [pytest.approx(50.0)] and plan["order"]["type"] == "Buy Limit"
    gold = build_order_plan(dict(asset="XAUUSD", direction="short", entry=4100, stop_loss=4112), risk_amount=50.0)
    assert gold["stop_pips"] == pytest.approx(120.0) and gold["lots"] == pytest.approx(50 / 1200)
    usdjpy = build_order_plan(dict(asset="USDJPY", direction="long", entry=152.30, stop_loss=152.00), risk_amount=50.0)
    assert usdjpy["pip_value_usd"] == pytest.approx(1000 / 152.30)


def test_cross_pairs_give_the_pip_value_in_the_quote_currency():
    plan = build_order_plan(dict(asset="EURJPY", direction="short", entry=165.0, stop_loss=165.4), risk_amount=50.0)
    assert plan["lots"] is None and plan["pip_value_currency"] == "JPY" and plan["pip_value_per_lot"] == pytest.approx(1000)
    assert any("convert the pip value" in line for line in order_plan_lines(dict(asset="EURJPY", direction="short",
                                                                                   entry=165.0, stop_loss=165.4)))


def test_card_and_api_show_the_plan():
    from pathlib import Path

    from signalrank_telegram.tier_signal_formatter import format_vip_signal

    card = format_vip_signal(dict(asset="BTCUSDT", direction="long", entry=75969.4, stop_loss=75857.77,
                                  take_profit=[76284.19], timeframe="5m", strategy_name="x", score=56, signal_id="x",
                                  current_price=75950.9, suggested_position_size=0.448))
    assert "Order type: Buy Stop at 75,969.40" in card and "Buy Stop Limit" in card
    assert "Risk = stop (111.6 points)" in card and "lots (0.45) = $50.01" in card
    api = (Path(__file__).resolve().parents[1] / "web" / "platform_api.py").read_text("utf-8")
    assert '"order_plan": order_plan' in api


_PG_DSN = __import__("os").getenv("SIGNALRANK_TEST_PG_DSN", "")


@pytest.mark.skipif(not _PG_DSN, reason="set SIGNALRANK_TEST_PG_DSN to an owned scratch PostgreSQL at head")
def test_challenger_evidence_reads_only_its_own_shadow_rows_on_postgres(monkeypatch):
    """/ml_candidate timed out in production (9 Nov): the read now uses ix_ml_rejected_candidate_shadow."""
    import asyncio
    import json
    from datetime import timedelta

    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    from db.session import _normalize_database_url
    from utils.timeutils import now_utc_naive

    url = _normalize_database_url(_PG_DSN, async_driver=True)
    monkeypatch.setenv("DATABASE_URL", url)
    mine, other = "a" * 64, "b" * 64

    async def scenario():
        from db.session import dispose_engine_for_event_loop
        from ml.candidate_forward import evaluate_candidate_forward_evidence

        engine = create_async_engine(url)
        try:
            async with engine.begin() as conn:
                for i, artifact in enumerate([mine, mine, mine, other]):
                    meta = {"layer": "ml", "direction": "long", "entry": 100, "stop_loss": 99, "take_profit": "[102]",
                            "features": {"rejection_type": "candidate_shadow", "candidate_artifact_hash_sha256": artifact,
                                         "candidate_observation_key": f"k{i}", "asset_class": "crypto"}}
                    await conn.execute(text(
                        "INSERT INTO decision_log(asset,timeframe,decision,reason,meta,created_at) VALUES "
                        "('ORDPLAN','1h','rejected','x',CAST(:m AS JSONB),:t)"),
                        {"m": json.dumps(meta), "t": now_utc_naive() - timedelta(minutes=5)})
            return await evaluate_candidate_forward_evidence(
                {"artifact_hash_sha256": mine, "trained_at": (now_utc_naive() - timedelta(hours=1)).isoformat()})
        finally:
            async with engine.begin() as conn:
                await conn.execute(text("DELETE FROM decision_log WHERE asset='ORDPLAN'"))
            await engine.dispose()
            await dispose_engine_for_event_loop()

    evidence = asyncio.run(scenario())
    assert evidence["observations"] == 3
