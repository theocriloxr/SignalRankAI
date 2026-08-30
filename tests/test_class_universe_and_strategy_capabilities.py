from core.asset_classes import AssetClass, canonical_asset_class
from data.class_universe import build_class_complete_universe
from strategies.capabilities import strategy_is_supported


def test_asset_class_aliases_have_one_canonical_internal_value():
    assert canonical_asset_class("fx") is AssetClass.FOREX
    assert canonical_asset_class("stock") is AssetClass.EQUITY
    assert canonical_asset_class("commodity_spot") is AssetClass.COMMODITY


def test_missing_classes_are_discovered_independently():
    symbols, health = build_class_complete_universe(
        ["BTCUSDT"],
        enabled_classes=["crypto", "fx", "stock"],
        discoverers={
            AssetClass.FOREX: lambda: ["EURUSD"],
            AssetClass.EQUITY: lambda: ["AAPL"],
        },
    )
    assert symbols == ["BTCUSDT", "EURUSD", "AAPL"]
    assert health["crypto"].source == "database"
    assert health["forex"].usable_count == 1
    assert health["equity"].usable_count == 1


def test_one_healthy_class_cannot_mask_a_missing_class():
    _, health = build_class_complete_universe(
        ["BTCUSDT"],
        enabled_classes=["crypto", "index"],
        discoverers={},
    )
    assert health["crypto"].degraded is False
    assert health["index"].degraded is True
    assert health["index"].failure_reason == "provider_not_configured"


def test_stock_strategy_never_runs_on_crypto_or_fx():
    assert strategy_is_supported("stock", "equity", "1h", "TRENDING")
    assert not strategy_is_supported("stock", "crypto", "1h", "TRENDING")
    assert not strategy_is_supported("stock", "forex", "1h", "TRENDING")
    assert not strategy_is_supported("stock", "equity", "1m", "TRENDING")
