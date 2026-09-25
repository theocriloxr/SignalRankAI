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



def test_profile_backfill_is_idempotent_and_never_overwrites_canonical_records():
    source = Path("services/user_intelligence.py").read_text(encoding="utf-8")
    script = Path("scripts/backfill_cross_channel_profiles.py").read_text(encoding="utf-8")
    assert "async def backfill_linked_platform_trading_preferences" in source
    assert "NOT EXISTS" in source
    assert "ON CONFLICT (key) DO NOTHING" in source
    assert "ON CONFLICT (key) DO UPDATE" not in source[
        source.index("async def _insert_runtime_json_if_absent"):
        source.index("async def backfill_linked_platform_trading_preferences")
    ]
    assert "merge_preference_payloads(modern, legacy, profile)" in source
    assert 'parser.add_argument("--apply", action="store_true"' in script
    assert "sys.path.insert(0, str(Path(__file__).resolve().parents[1]))" in script
    assert "if apply:" in script
    assert "await session.rollback()" in script



def test_canonical_mt5_helpers_do_not_require_telegram_identity():
    source = Path("services/mt5_client.py").read_text(encoding="utf-8")
    assert "async def link_platform_mt5_account(" in source
    assert "async def get_platform_mt5_link_status(" in source
    section = source[source.index("async def link_platform_mt5_account("):]
    assert "WHERE id=:uid" in section
    assert "WHERE user_id=:uid" in section
    assert "telegram_user_id" not in section[:section.index("async def get_platform_mt5_account_id")]


def test_web_execution_settings_reuse_canonical_cross_channel_preferences():
    source = Path("web/platform_api.py").read_text(encoding="utf-8")
    section = source[source.index('@router.put("/execution-settings")'):source.index('@router.delete("/devices/{session_id}")')]
    assert "get_platform_user_trading_preferences" in section
    assert "set_platform_user_trading_preferences" in section
    assert "autoexec_user_optin:" in section
    assert "copyexec_user_optin:" in section



def test_telegram_and_web_events_share_the_canonical_event_writer():
    source = Path("db/pg_features.py").read_text(encoding="utf-8")
    assert "async def record_user_event(" in source
    bot = source[source.index("async def record_bot_event("):source.index("def _env_int", source.index("async def record_bot_event("))]
    assert "record_user_event(" in bot
    assert "BotEvent(" not in bot



def test_web_fanout_reuses_canonical_platform_preferences():
    source = Path("services/platform/signal_delivery.py").read_text(encoding="utf-8")
    assert "get_platform_user_trading_preferences" in source
    assert "preferences_from_payload" in source
    assert "signal_matches_preferences" in source
    assert "telegram_user_id" not in source



def test_mt5_router_uses_one_identity_aware_execution_path():
    source = Path("services/mt5_signal_router.py").read_text(encoding="utf-8")
    assert "async def route_platform_signal_to_mt5(" in source
    assert 'user_identity="platform"' in source
    assert "get_platform_user_trading_preferences" in source
    assert "get_platform_execution_evidence" in source
    assert "reserve_platform_user_execution_quota" in source
    assert "ensure_platform_mt5_account_id" in source
    assert "canonical_id = await self._resolve_canonical_user_id(" in source
    assert "user_id=canonical_id" in source


def test_platform_execution_optins_are_canonical_and_telegram_mirrored_when_linked():
    source = Path("web/platform_api.py").read_text(encoding="utf-8")
    section = source[
        source.index('@router.put("/execution-settings")'):
        source.index('@router.delete("/devices/{session_id}")')
    ]
    assert "autoexec_platform_optin:" in section
    assert "copyexec_platform_optin:" in section
    assert "autoexec_user_optin:" in section
    assert "copyexec_user_optin:" in section
    assert '"source": "platform"' in section


def test_execution_quota_and_evidence_have_platform_entrypoints():
    quota = Path("services/execution_quota.py").read_text(encoding="utf-8")
    evidence = Path("services/execution_evidence.py").read_text(encoding="utf-8")
    assert "async def reserve_platform_user_execution_quota(" in quota
    assert "get_platform_user_trading_preferences" in quota
    assert "async def get_platform_execution_evidence(" in evidence
    assert "notification_events" in evidence
    telegram_section = evidence[
        evidence.index("async def get_execution_evidence("):
        evidence.index("__all__")
    ]
    assert "web_receipt_count=0" in telegram_section



def test_web_and_telegram_share_tier_visibility_source_of_truth():
    api = Path("web/platform_api.py").read_text(encoding="utf-8")
    formatter = Path("signalrank_telegram/tier_gated_formatter.py").read_text(encoding="utf-8")
    assert "get_entitlements(tier)" in api
    assert "get_entitlements(tier)" in formatter
    assert 'policy.has("exact_levels")' in api
    assert 'evaluate_feature_access(tier, "exact_levels")' in formatter
    assert "policy.max_tp_levels" in api
    assert "policy.max_tp_levels" in formatter
