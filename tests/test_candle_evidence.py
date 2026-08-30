import pytest

from core.candle_evidence import assess_candle_evidence


def _candle(open_, high, low, close, volume=100, **extra):
    return {"open": open_, "high": high, "low": low, "close": close, "volume": volume, **extra}


def test_reads_body_wicks_close_and_context_without_calling_it_proof():
    history = [_candle(100, 103, 99, 102, 100) for _ in range(20)]
    result = assess_candle_evidence(history + [_candle(100, 102, 94, 101.5, 180)], direction="long")
    assert result.rejection == "lower_price_rejection"
    assert result.lower_wick_ratio > 0.7
    assert result.close_location > 0.9
    assert result.relative_volume == pytest.approx(1.8)
    assert result.confirmation == "pending"
    assert result.state == "observed"


def test_next_final_candle_can_confirm_but_live_last_candle_cannot():
    rows = [_candle(100, 102, 99, 101) for _ in range(20)]
    rows += [_candle(100, 102, 95, 101), _candle(101, 104, 100, 103, is_final=True)]
    historical = assess_candle_evidence(rows, focus_index=20, direction="long")
    live = assess_candle_evidence(rows, direction="long")
    assert historical.confirmation == "confirmed"
    assert live.confirmation == "pending"


def test_non_final_next_candle_is_never_used_for_confirmation():
    rows = [_candle(100, 102, 99, 101) for _ in range(20)]
    rows += [_candle(100, 102, 95, 101), _candle(101, 110, 100, 109, is_final=False)]
    assert assess_candle_evidence(rows, focus_index=20, direction="long").confirmation == "pending"


def test_rejects_impossible_ohlc():
    with pytest.raises(ValueError, match="invalid OHLC"):
        assess_candle_evidence([_candle(100, 90, 95, 99)])
