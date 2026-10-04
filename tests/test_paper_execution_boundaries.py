from __future__ import annotations

import pytest

from core import paper_trading_service as paper


@pytest.mark.parametrize("value", [None, "", "sideways", "unknown", 1, True, {}, "long or short"])
def test_unknown_paper_direction_never_becomes_a_short(value):
    assert paper.canonical_direction(value) == ""


@pytest.mark.parametrize("value,expected", [
    ("BUY", "long"), (" long ", "long"), ("bull", "long"), ("bullish", "long"),
    ("SELL", "short"), (" short ", "short"), ("bear", "short"), ("bearish", "short"),
])
def test_paper_direction_preserves_supported_aliases(value, expected):
    assert paper.canonical_direction(value) == expected


@pytest.mark.asyncio
@pytest.mark.parametrize("price", [None, 0, -1, float("nan"), float("inf"), -float("inf"), True, False, "invalid"])
async def test_bad_mark_price_is_rejected_before_any_database_access(monkeypatch, price):
    def forbidden_session(*args, **kwargs):
        pytest.fail("invalid price must not reach a database transaction")
    monkeypatch.setattr(paper, "get_session", forbidden_session)
    with pytest.raises(ValueError, match="paper_mark_price_invalid"):
        await paper.PaperTradingService()._mark_one("test-position", price)


@pytest.mark.parametrize("value", ["inf", "-inf", "nan", "invalid"])
def test_nonfinite_position_age_does_not_disable_stale_recovery(monkeypatch, value):
    monkeypatch.setenv("PAPER_POSITION_MAX_AGE_HOURS", value)
    assert paper.position_max_age_hours("5m") == 12.0
