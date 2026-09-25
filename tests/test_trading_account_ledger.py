from __future__ import annotations

from decimal import Decimal

import pytest

from services.trading_account_ledger import (
    ACCOUNT_LEDGER_ENTRY_TYPES,
    _decimal_or_none,
    _safe_metadata,
)


def test_account_ledger_entry_types_cover_required_broker_financial_events():
    assert {
        "deposit",
        "withdrawal",
        "realized_pnl",
        "unrealized_pnl_snapshot",
        "commission",
        "funding",
        "swap",
        "fee",
        "balance_snapshot",
        "equity_snapshot",
        "margin_snapshot",
        "order",
        "fill",
        "position_snapshot",
        "adjustment",
        "reconciliation_correction",
    }.issubset(ACCOUNT_LEDGER_ENTRY_TYPES)


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-Infinity", float("nan")])
def test_account_ledger_rejects_non_finite_financial_values(value):
    with pytest.raises(ValueError, match="invalid_amount"):
        _decimal_or_none(value, name="amount")


def test_account_ledger_decimal_conversion_is_exact_and_optional():
    assert _decimal_or_none("0.1000000001", name="amount") == Decimal("0.1000000001")
    assert _decimal_or_none(None, name="amount") is None
    assert _decimal_or_none("", name="amount") is None


def test_account_ledger_metadata_redacts_nested_credentials():
    cleaned = _safe_metadata(
        {
            "provider": "bybit",
            "api_key": "should-not-survive",
            "nested": {
                "password": "secret",
                "position": {"id": "position-1"},
            },
            "authorization_header": "bearer secret",
        }
    )
    assert cleaned["provider"] == "bybit"
    assert cleaned["api_key"] == "<redacted>"
    assert cleaned["nested"]["password"] == "<redacted>"
    assert cleaned["nested"]["position"]["id"] == "position-1"
    assert cleaned["authorization_header"] == "<redacted>"


def test_account_ledger_metadata_is_bounded():
    cleaned = _safe_metadata({"long": "x" * 10000, "many": list(range(200))})
    assert len(cleaned["long"]) == 2048
    assert len(cleaned["many"]) == 100
