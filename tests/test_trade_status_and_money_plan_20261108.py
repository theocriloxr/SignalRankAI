"""Owner findings, 8 Nov 2026: trade status, closed P/L, late entries, money calculator.

1. A triggered trade kept showing "Waiting for entry" (web read the outcome
   projection, which stays 'pending'; Telegram guessed from price distance).
2. Closed signals did not show the trade's result.
3. Entries arrived after price had run toward TP1.
4. The calculator gave a size and R/R but no money result.
"""
from pathlib import Path

from engine.signal_calculations import calculate_money_plan, format_enhanced_signal_data
from services.trade_status import describe_trade, trade_status_line
from signalrank_telegram.tier_signal_formatter import format_vip_signal

ROOT = Path(__file__).resolve().parents[1]
SUI = dict(entry=0.8976, stop_loss=0.8921, take_profit=[0.917334], direction="long")


def test_lifecycle_beats_a_pending_outcome_row():
    status = describe_trade(lifecycle_state="ACTIVE_TRADE", outcome_status="pending")
    assert status.code == "open" and status.entry_triggered and not status.closed
    assert "Entry triggered" in status.label


def test_tp1_hit_reports_the_banked_r_and_open_share():
    status = describe_trade(lifecycle_state="TP1_HIT", outcome_status="tp1", **SUI)
    assert status.highest_tp == 1 and not status.closed
    assert status.banked_r == 1.794 and status.open_share == 0.5
    assert "+1.79R banked" in trade_status_line(status)


def test_closed_trade_shows_r_money_and_move():
    status = describe_trade(lifecycle_state="BREAKEVEN_STOP", outcome_status="partial_win_be",
                            r_multiple=1.79, pnl_pct=1.1, **SUI)
    assert status.closed and status.realized_r == 1.79 and status.result_per_100_risk == 179.0
    line = trade_status_line(status)
    assert "+1.79R" in line and "$+179.00 per $100 risked" in line and "+1.10% price move" in line


def test_missed_entry_has_no_pnl_and_outcome_fallback_without_lifecycle():
    missed = describe_trade(lifecycle_state="MISSED_ENTRY", outcome_status="missed_entry", r_multiple=-1)
    assert missed.closed and not missed.entry_triggered and missed.realized_r is None
    assert "no position" in trade_status_line(missed)
    assert describe_trade(outcome_status="sl", r_multiple=-1).code == "closed_sl"
    assert describe_trade(outcome_status="sl", r_multiple=0.0, highest_tp_hit=1).code == "closed_protected"


def test_money_plan_uses_the_card_size_and_the_ledger_rule():
    plan = calculate_money_plan(dict(asset="BCHUSDT", direction="long", entry=275.17, stop_loss=273.63,
                                     take_profit=280.6955), position_size=32.47)
    assert plan["risk_amount"] == 50.0 and plan["position_value"] == 8934.77
    assert plan["targets"][0]["profit_if_all_closed"] == 179.41
    assert {p["path"]: p["money"] for p in plan["paths"]} == {"stop_first": -50.0, "tp1_then_entry": 89.71}


def test_money_plan_from_balance_and_three_targets():
    plan = calculate_money_plan(dict(direction="short", entry=100.0, stop_loss=102.0, take_profit=[98, 96, 94]),
                                account_balance=10000, risk_pct=1.0)
    assert plan["risk_amount"] == 100.0
    assert {p["path"]: p["money"] for p in plan["paths"]}["tp3_planned_closes"] == 175.0
    assert format_enhanced_signal_data(dict(direction="long", entry=100, stop_loss=98, take_profit=[104]))[
        "money_plan"]["risk_amount"] == 100.0


def test_card_shows_money_and_a_limit_hint_when_price_ran_past_entry():
    card = format_vip_signal(dict(asset="BCHUSDT", direction="long", entry=275.17, stop_loss=273.63,
                                  take_profit=280.6955, timeframe="5m", score=66, suggested_position_size=32.47,
                                  current_price=276.10))
    assert "$50.00 at risk" in card and "TP1 then entry +$89.71" in card and "+$179.41" in card
    assert "0.60R past entry" in card and "limit order at 275.1700" in card


def test_web_lists_join_the_lifecycle_and_present_trade_status():
    source = (ROOT / "web" / "platform_api.py").read_text(encoding="utf-8")
    assert source.count("LEFT JOIN signal_lifecycles l ON l.signal_id=s.signal_id") >= 4
    assert 'payload["trade_status"] = describe_trade(' in source
    web = (ROOT / "frontend" / "src" / "components" / "WorkspaceLive.tsx").read_text(encoding="utf-8")
    assert "function statusOf(signal: Row)" in web and "<TradeResult signal={signal}/>" in web
