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
    assert prefs.asset_classes == ("crypto", "fx", "stocks", "index", "commodities")
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
