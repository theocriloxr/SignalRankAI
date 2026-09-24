from __future__ import annotations

from pathlib import Path

from engine.signal_lifecycle import _lifecycle_lock_timeout_ms
from services.profile_demand import aggregate_profile_demand
from services.user_intelligence import preferences_from_payload


ROOT = Path(__file__).resolve().parents[1]


def test_lifecycle_lock_timeout_is_bounded(monkeypatch):
    monkeypatch.setenv("OUTCOME_LIFECYCLE_LOCK_TIMEOUT_MS", "50")
    assert _lifecycle_lock_timeout_ms() == 250
    monkeypatch.setenv("OUTCOME_LIFECYCLE_LOCK_TIMEOUT_MS", "1500")
    assert _lifecycle_lock_timeout_ms() == 1500
    monkeypatch.setenv("OUTCOME_LIFECYCLE_LOCK_TIMEOUT_MS", "99999")
    assert _lifecycle_lock_timeout_ms() == 10000


def test_profile_payload_normalizes_all_supported_market_classes():
    prefs = preferences_from_payload(
        {
            "trade_profile": "day",
            "risk_profile": "balanced",
            "asset_classes": ["crypto", "forex", "stocks", "indices", "commodities"],
            "preferred_timeframes": ["5m", "1hr", "4hr", "daily"],
        }
    )
    assert prefs.trade_profile == "day"
    assert prefs.asset_classes == ("crypto", "fx", "stock", "index", "commodity")
    assert prefs.preferred_timeframes == ("5m", "1h", "4h", "1d")


def test_profile_demand_canonical_overlay_wins_over_legacy_values():
    snapshot = aggregate_profile_demand(
        {
            7: {
                "modern": {"asset_classes": ["crypto"], "trade_profile": "scalp"},
                "canonical": {"asset_classes": ["fx", "stock"], "trade_profile": "swing"},
            }
        },
        active_user_ids={7},
    )
    assert snapshot.active_profiles == 1
    assert set(snapshot.asset_classes) == {"fx", "stock"}
    assert snapshot.trade_profile_counts == {"swing": 1}


def test_web_profile_and_multi_asset_signal_filters_are_exposed():
    source = (ROOT / "web/platform_api.py").read_text(encoding="utf-8")
    assert '@router.get("/trading-profile")' in source
    assert '@router.put("/trading-profile")' in source
    assert 'asset_class: str | None = Query' in source
    assert 'timeframe: str | None = Query' in source
    assert 'strategy: str | None = Query' in source
    assert '"asset_classes": ["crypto", "fx", "stock", "index", "commodity"]' in source


def test_web_trading_profile_ui_is_cross_channel_and_responsive():
    html = (ROOT / "web/platform_app/index.html").read_text(encoding="utf-8")
    js = (ROOT / "web/platform_app/app.js").read_text(encoding="utf-8")
    css = (ROOT / "web/platform_app/styles.css").read_text(encoding="utf-8")
    assert 'id="tradingProfileForm"' in html
    assert 'Stocks / equities' in html
    assert "request('/trading-profile'" in js
    assert "Synced with your linked Telegram account" in js
    assert ".profile-settings-grid" in css
    assert "@media(max-width:760px)" in css


def test_outcome_reconciliation_is_split_into_bounded_transactions():
    source = (ROOT / "worker/worker.py").read_text(encoding="utf-8")
    for label in (
        "outcome_reconciliation.projections",
        "outcome_reconciliation.outbox",
        "outcome_reconciliation.partial_exits",
        "outcome_reconciliation.performance",
    ):
        assert label in source
    assert "OUTCOME_RECONCILIATION_PHASE_BUDGET_SECONDS" in source
    assert "OUTCOME_OUTBOX_REPAIR_BATCH_LIMIT" in source
    assert "asyncio.wait_for" in source


def test_outbox_repair_stops_after_transaction_poisoning():
    source = (ROOT / "services/outcome_reconciliation.py").read_text(encoding="utf-8")
    block = source[source.index("async def repair_outcome_notification_outbox"):source.index("async def outcome_projection_health")]
    assert "await session.rollback()" in block
    assert "queued = 0" in block
    assert "break" in block


def test_lifecycle_observation_uses_short_postgres_lock_wait():
    source = (ROOT / "engine/signal_lifecycle.py").read_text(encoding="utf-8")
    block = source[source.index("async def update_lifecycle_observation"):source.index("async def record_lifecycle_event")]
    assert "SET LOCAL lock_timeout" in block
    assert "outcome.lifecycle_observation" in block
    assert "lifecycle_observation_deferred" in block


def test_web_tools_cover_live_quote_recap_ai_watchlists_alerts_and_notifications():
    api = (ROOT / "web/platform_api.py").read_text(encoding="utf-8")
    html = (ROOT / "web/platform_app/index.html").read_text(encoding="utf-8")
    js = (ROOT / "web/platform_app/app.js").read_text(encoding="utf-8")
    for route in (
        '@router.get("/live-price")',
        '@router.get("/recap")',
        '@router.post("/ai/analyze")',
        '@router.get("/watchlists")',
        '@router.get("/alerts")',
        '@router.get("/notifications")',
    ):
        assert route in api
    for element_id in (
        'id="toolsView"',
        'id="liveQuoteForm"',
        'id="aiAnalyzeForm"',
        'id="watchlistForm"',
        'id="alertForm"',
        'id="notificationCenter"',
    ):
        assert element_id in html
    assert "async function loadTools()" in js
    assert "get_live_price_result" in api
    assert "get_market_state_async" in api
    assert "explain_signal" in api


def test_paid_web_surfaces_enforce_canonical_tier_policy_without_breaking_login_boot():
    api = (ROOT / "web/platform_api.py").read_text(encoding="utf-8")
    js = (ROOT / "web/platform_app/app.js").read_text(encoding="utf-8")
    assert '_assert_feature(user, "paper_trading")' in api
    assert '_assert_feature(user, "portfolio_analytics")' in api
    assert '_assert_feature(user, "performance_analytics")' in api
    assert '_assert_feature(user, "custom_alerts")' in api
    assert '_assert_command(user, "analyze")' in api
    assert "Promise.allSettled(initial)" in js
    assert "if(hasFeature('paper_trading'))initial.push(loadPaper())" in js


def test_signal_detail_exposes_delivery_proof_outcome_and_lifecycle_without_cross_user_access():
    api = (ROOT / "web/platform_api.py").read_text(encoding="utf-8")
    block = api[api.index('@router.get("/signals/{signal_id}")'):api.index('@router.get("/live-price")')]
    assert "d.user_id=:uid" in block
    assert "d.sent_ok=TRUE" in block
    assert "signal_lifecycles" in block
    assert "signal_tracking_events" in block
    assert '"delivery_proven"' in block


def test_signal_detail_ui_and_tool_handlers_use_query_selector_all():
    html = (ROOT / "web/platform_app/index.html").read_text(encoding="utf-8")
    js = (ROOT / "web/platform_app/app.js").read_text(encoding="utf-8")
    css = (ROOT / "web/platform_app/styles.css").read_text(encoding="utf-8")
    assert 'id="signalDetailPanel"' in html
    assert "async function loadSignalDetail(" in js
    assert "$$('.signal-detail').forEach" in js
    for selector in (
        "market-watch",
        "watchlist-delete",
        "alert-delete",
        "notification-read",
    ):
        assert f"$('.{selector}').forEach" in js
    assert ".signal-detail-panel" in css
    assert ".timeline-event" in css


def test_notification_preferences_expose_quiet_hours_and_locale_on_web():
    html = (ROOT / "web/platform_app/index.html").read_text(encoding="utf-8")
    js = (ROOT / "web/platform_app/app.js").read_text(encoding="utf-8")
    assert 'name="locale"' in html
    assert 'name="quiet_hours_start"' in html
    assert 'name="quiet_hours_end"' in html
    assert "quiet_hours_start','quiet_hours_end','timezone" in js


def test_weekly_recap_uses_delivery_proof_not_raw_generated_signals():
    api = (ROOT / "web/platform_api.py").read_text(encoding="utf-8")
    block = api[api.index('@router.get("/recap")'):api.index('@router.post("/ai/analyze")')]
    assert "signal_deliveries" in block
    assert "d.sent_ok=TRUE" in block
    assert "delivery_confirmed_at" in block
    assert "resolved_win_rate" in block
    assert "not a forecast" in block
