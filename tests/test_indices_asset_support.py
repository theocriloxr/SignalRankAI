from datetime import datetime, timezone

from data.fetcher import (
    get_asset_type,
    get_strict_provider_for_asset,
    is_index,
    is_stock,
    market_closed_reason,
    normalize_index_symbol,
    normalize_symbol,
)
from data.pair_discovery import get_all_tradable_assets, get_all_trending_pairs
from engine.core import _asset_class_key, _production_quality_gate
from engine.ml import _asset_class_to_int
from engine.risk import get_asset_class, get_asset_class_config


def test_index_symbols_are_first_class_assets():
    assert is_index("US500")
    assert is_index("NAS100")
    assert is_index("^GSPC")
    assert not is_stock("US500")
    assert get_asset_type("INDEX:US500") == "index"
    assert get_asset_type("US30") == "index"
    assert normalize_symbol("US500") == "INDEX:US500"
    assert normalize_index_symbol("US500") == "^GSPC"
    assert normalize_index_symbol("GER40") == "^GDAXI"


def test_index_provider_contract_is_not_stock_routing():
    asset_type, providers = get_strict_provider_for_asset("US500")

    assert asset_type == "index"
    assert "yahoo" in providers
    assert "tradingview" in providers


def test_index_market_hours_supports_cfd_and_cash_modes(monkeypatch):
    monkeypatch.delenv("INDEX_MARKET_MODE", raising=False)

    sunday_midday = datetime(2026, 6, 28, 12, 0, tzinfo=timezone.utc)
    monday_open = datetime(2026, 6, 29, 14, 0, tzinfo=timezone.utc)

    assert "Sunday" in (market_closed_reason("US500", sunday_midday) or "")
    assert market_closed_reason("US500", monday_open) is None

    monkeypatch.setenv("INDEX_MARKET_MODE", "cash")
    monday_after_cash_close = datetime(2026, 6, 29, 21, 0, tzinfo=timezone.utc)
    assert "cash-index" in (market_closed_reason("^GSPC", monday_after_cash_close) or "")


def test_index_discovery_bucket_is_included(monkeypatch):
    monkeypatch.setenv("INDEX_TICKERS", "US500,GER40")
    monkeypatch.setenv("CRYPTO_TRENDING_TOP_N", "1")
    monkeypatch.setenv("FX_TRENDING_TOP_N", "1")
    monkeypatch.setenv("STOCK_TRENDING_TOP_N", "1")
    monkeypatch.setenv("COMMODITY_TRENDING_TOP_N", "1")

    assets = get_all_tradable_assets()
    flattened = get_all_trending_pairs()

    assert assets["indices"] == ["US500", "GER40"]
    assert "US500" in flattened
    assert "GER40" in flattened


def test_index_engine_and_risk_contracts(monkeypatch):
    monkeypatch.delenv("PRODUCTION_QUALITY_GUARD_ENABLED", raising=False)

    assert _asset_class_key("US500") == "index"
    assert _asset_class_to_int("US500") == 4.0
    assert get_asset_class("US500") == "index"
    assert get_asset_class_config("index")["min_rr"] == 2.0

    ok, reason = _production_quality_gate(
        {
            "asset": "US500",
            "direction": "long",
            "timeframe": "4h",
            "entry": 6500.0,
            "stop_loss": 6450.0,
            "take_profit": 6605.0,
            "score": 93.0,
            "ml_probability": 0.70,
            "adx": 28.0,
        }
    )

    assert ok, reason

    ok, reason = _production_quality_gate(
        {
            "asset": "US500",
            "direction": "long",
            "timeframe": "4h",
            "entry": 6500.0,
            "stop_loss": 6350.0,
            "take_profit": 7000.0,
            "score": 96.0,
            "ml_probability": 0.80,
            "adx": 30.0,
        }
    )

    assert not ok
    assert "quality_stop_loss_pct" in reason or "quality_rr" in reason
