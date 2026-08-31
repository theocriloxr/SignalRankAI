import pytest

from core.candle_evidence import (
    assess_candle_evidence,
    attach_candle_evidence,
    build_candle_intelligence,
)


def _candle(open_, high, low, close, volume=100, **extra):
    return {"open": open_, "high": high, "low": low, "close": close, "volume": volume, **extra}


def test_reads_body_wicks_close_and_context_without_calling_it_proof():
    history = [_candle(100, 103, 99, 102, 100) for _ in range(20)]
    result = assess_candle_evidence(history + [_candle(100, 102, 94, 101.5, 180)], direction="long")
    assert result.rejection == "lower_price_rejection"
    assert result.lower_wick_ratio > 0.7
    assert result.close_location > 0.9
    assert result.relative_volume == pytest.approx(1.8)
    assert result.body_classification
    assert result.close_control == "buyers"
    assert result.confirmation == "pending"
    assert result.state == "observed"
    assert "not proof" in result.summary


def test_next_final_candle_can_confirm_but_live_last_candle_cannot():
    rows = [_candle(100, 102, 99, 101) for _ in range(20)]
    rows += [_candle(100, 102, 95, 101), _candle(101, 104, 100, 103, is_final=True)]
    historical = assess_candle_evidence(rows, focus_index=20, direction="long")
    live = assess_candle_evidence(rows, direction="long")
    assert historical.confirmation == "confirmed"
    assert live.confirmation == "pending"
    intelligence = build_candle_intelligence(rows, direction="long")
    assert intelligence["selected_focus"] == "previous_confirmed"
    assert intelligence["alignment"] == "supportive"


def test_non_final_next_candle_is_never_used_for_confirmation():
    rows = [_candle(100, 102, 99, 101) for _ in range(20)]
    rows += [_candle(100, 102, 95, 101), _candle(101, 110, 100, 109, is_final=False)]
    assert assess_candle_evidence(rows, focus_index=20, direction="long").confirmation == "pending"


def test_unmarked_live_tail_is_not_assumed_complete():
    rows = [_candle(100, 102, 99, 101) for _ in range(20)]
    rows += [_candle(100, 102, 95, 101, is_final=True), _candle(101, 110, 100, 109)]
    intelligence = build_candle_intelligence(rows, direction="long")
    assert intelligence["latest"]["confirmation"] == "pending"
    assert intelligence["latest"]["direction"] == "bullish"


def test_rejects_impossible_ohlc():
    with pytest.raises(ValueError, match="invalid OHLC"):
        assess_candle_evidence([_candle(100, 90, 95, 99)])


def test_same_wick_is_stronger_at_support_than_in_middle_of_range():
    history = [_candle(101, 104, 99, 102) for _ in range(20)]
    at_support = assess_candle_evidence(
        history + [_candle(102, 103, 98.5, 102.8, 150)],
        direction="long",
    )
    mid_range = assess_candle_evidence(
        history + [_candle(106, 108, 103, 107, 150)],
        direction="long",
    )
    assert at_support.rejection == "lower_price_rejection"
    assert at_support.at_key_level is True
    assert "location_context" in at_support.aligned_evidence
    assert mid_range.rejection == "lower_price_rejection"
    assert mid_range.at_key_level is False
    assert "location_context" not in mid_range.aligned_evidence
    assert at_support.evidence_score_pct > mid_range.evidence_score_pct


def test_breakout_context_requires_a_close_beyond_past_resistance():
    history = [_candle(101, 105, 99, 102) for _ in range(20)]
    result = assess_candle_evidence(
        history + [_candle(102, 108, 101, 107, 180)],
        direction="long",
    )
    assert result.breakout == "bullish_breakout"
    assert result.market_context == "bullish_breakout"
    assert "location_context" in result.aligned_evidence


def test_signal_attachment_exposes_structured_evidence_for_scoring_and_outputs():
    rows = [_candle(100, 102, 99, 101) for _ in range(20)]
    rows += [_candle(100, 102, 95, 101, 180), _candle(101, 104, 100, 103, 160, is_final=True)]
    signal = {"direction": "LONG"}
    attach_candle_evidence(signal, rows)
    assert signal["candle_evidence"]["selected_focus"] == "previous_confirmed"
    assert signal["candle_evidence_alignment"] == "supportive"
    assert signal["candle_confirmation"] == "confirmed"
    assert signal["candle_evidence_score"] >= 60
