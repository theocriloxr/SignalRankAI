from __future__ import annotations

from pathlib import Path

from services.profile_demand import aggregate_profile_demand
from services.user_intelligence import preferences_from_payload, preferences_to_payload


def test_canonical_profile_overrides_telegram_legacy_without_double_counting():
    snapshot = aggregate_profile_demand(
        {
            101: {
                "modern": {"asset_classes": ["crypto"], "trade_profile": "day"},
                "canonical": {"asset_classes": ["fx", "commodity"], "trade_profile": "swing"},
            }
        },
        active_user_ids={101},
    )
    assert snapshot.active_profiles == 1
    assert set(snapshot.asset_classes) == {"fx", "commodity"}
    assert snapshot.trade_profile_counts == {"swing": 1}


def test_trading_preferences_preserve_all_supported_asset_classes():
    prefs = preferences_from_payload(
        {
            "trade_profile": "all",
            "asset_classes": ["crypto", "forex", "stock", "indices", "commodity"],
            "preferred_assets": ["btcusdt", "eurusd", "xauusd", "nas100", "aapl"],
        }
    )
    payload = preferences_to_payload(prefs)
    assert payload["asset_classes"] == ["crypto", "fx", "stock", "index", "commodity"]
    assert payload["preferred_assets"] == ["BTCUSDT", "EURUSD", "XAUUSD", "NAS100", "AAPL"]


def test_web_api_exposes_cross_channel_trading_profile_contract():
    source = Path("web/platform_api.py").read_text(encoding="utf-8")
    assert '@router.get("/trading-profile")' in source
    assert '@router.put("/trading-profile")' in source
    assert "get_platform_user_trading_preferences" in source
    assert "set_platform_user_trading_preferences" in source
    assert '"crypto", "fx", "stock", "index", "commodity"' in source


def test_web_app_exposes_same_profile_and_multi_asset_signal_filters():
    html = Path("web/platform_app/index.html").read_text(encoding="utf-8")
    js = Path("web/platform_app/app.js").read_text(encoding="utf-8")
    assert 'id="tradingProfileForm"' in html
    for market in ("crypto", "fx", "stock", "index", "commodity"):
        assert f'value="{market}"' in html
    assert "request('/trading-profile')" in js
    assert "request('/trading-profile',{method:'PUT'" in js
    assert "signalClassFilter" in js
    assert "signalTimeframeFilter" in js
