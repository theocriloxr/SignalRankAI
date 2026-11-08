"""Signal cards show only the targets that are tracked, and the R each path books (8 Nov 2026).

Owner report, 4 Nov: the SUIUSDT 5m VIP card (entry 0.8976, stop 0.8921, one
stored target 0.917334) listed TP2 0.93707 "close 25%" and TP3 0.95680 with
"TP3 R:R 1:10.76" and "+6.60% to final target". Those two levels were made up
by the formatter (2x and 3x the TP1 distance); the lifecycle tracker followed
only 0.917334 and booked +1.79R (half at TP1, the rest at the protected stop)
although price later reached 0.9563.
"""
from signalrank_telegram.tier_signal_formatter import format_premium_signal, format_vip_signal

SUI = dict(asset="SUIUSDT", direction="long", entry=0.8976, stop_loss=0.8921, take_profit=0.917334,
           timeframe="5m", strategy_name="ADX Trend", score=62.1, signal_id="169707e7-845")


def test_vip_card_does_not_invent_tp2_or_tp3():
    card = format_vip_signal(dict(SUI))
    assert "TP1: 0.91733" in card
    assert "TP2" not in card and "TP3" not in card
    assert "0.93707" not in card and "0.95680" not in card
    assert "+6.60%" not in card and "+2.20%" in card


def test_premium_card_does_not_invent_tp2():
    card = format_premium_signal(dict(SUI))
    assert "TP2" not in card and "0.93707" not in card


def test_card_shows_the_r_the_ledger_books():
    card = format_vip_signal(dict(SUI))
    assert "stop first -1.00R" in card
    assert "TP1 then stop at entry +1.79R" in card  # the booked SUIUSDT result
    assert "remaining 50% has no further target" in card


def test_three_target_plan_lists_every_path():
    sig = dict(asset="ETHUSDT", direction="short", entry=100.0, stop_loss=102.0, take_profit=[98.0, 96.0, 94.0],
               timeframe="1h", score=70)
    card = format_vip_signal(sig)
    assert "TP1 then stop at entry +0.50R" in card
    assert "TP2 then stop at entry +1.00R" in card
    assert "TP3 +1.75R with the planned closes (recorded as TP3 +3.00R)" in card  # 0.5*1 + 0.25*2 + 0.25*3
    assert "no further target" not in card


def test_live_rr_uses_the_current_price():
    card = format_vip_signal(dict(SUI, current_price=0.9001))
    assert "R/R to TP1 from this price 1:2.15" in card  # (0.917334-0.9001)/(0.9001-0.8921)


def test_price_past_the_target_or_stop_is_flagged():
    assert "already past the first target" in format_vip_signal(dict(SUI, current_price=0.92))
    assert "already past the stop" in format_vip_signal(dict(SUI, current_price=0.89))


def test_targets_on_the_wrong_side_are_not_shown():
    card = format_vip_signal(dict(SUI, take_profit=[0.8800, 0.917334]))
    assert "0.88000" not in card and "TP1: 0.91733" in card
