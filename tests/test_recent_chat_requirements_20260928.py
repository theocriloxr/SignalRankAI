from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def source(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_recent_web_session_billing_and_secure_link_requirements_are_locked() -> None:
    app = source("web/platform_app/app.js")
    api = source("web/platform_api.py")
    web = source("web/app.py")
    mt5 = source("services/mt5_client.py")
    assert "refreshBrowserSession" in app
    assert "showBootstrapError" in app
    assert "reconcilePendingSecureLink" in app
    assert "confirmPendingBillingReturn" in app
    assert '@router.post("/billing/confirm")' in api
    assert "/transaction/verify/" in api
    assert '@app.get("/billing/complete"' in web
    assert "execution_enabled=False" in mt5
    assert 'status="awaiting_credentials"' in mt5


def test_recent_multi_asset_and_full_decision_learning_requirements_are_locked() -> None:
    asset_classes = source("core/asset_classes.py")
    profile = source("services/user_intelligence.py")
    model_training = source("ml/train_model.py")
    decisions = source("services/decision_intelligence.py")
    for name in ("crypto", "fx", "commodity", "index", "stock"):
        assert name in asset_classes or name in profile
    assert "shadow_rejected" in model_training
    assert "source_weight" in model_training
    for disposition in ("issued", "rejected", "skipped", "delayed", "suppressed"):
        assert disposition in decisions


def test_recent_openai_and_cross_channel_parity_requirements_are_locked() -> None:
    ai = source("services/openai_ai.py")
    api = source("web/platform_api.py")
    html = source("web/platform_app/index.html")
    catalog = source("signalrank_telegram/command_catalog.py")
    assert "provider_order" in ai
    assert "OPENAI_SIGNAL_REVIEW_ENABLED" in ai
    assert "OPENAI_AI_CIRCUIT_BREAKER_ENABLED" in ai
    assert '@router.get("/command-catalog")' in api
    assert "from signalrank_telegram.command_catalog import COMMANDS" in api
    assert "for spec in COMMANDS" in api
    assert '"telegram_menu_limit": 100' in api
    assert 'id="commandCatalog"' in html
    assert 'id="opsView"' in html
    assert catalog.count("CommandSpec(") > 100


def test_recent_tier_and_multi_account_execution_requirements_are_locked() -> None:
    policy = source("core/tier_policy.py")
    api = source("web/platform_api.py")
    models = source("db/mt5_models.py")
    html = source("web/platform_app/index.html")
    assert '"broker_connection": Tier.PREMIUM' in policy
    assert '@router.get("/entitlements")' in api
    assert "/signals/{signal_id}/execute" in api
    assert "multiple MT5 accounts" in models
    assert "Connection ≠ execution permission" in html
    assert "Only signals delivered to your account can execute" in html


def test_recent_email_identity_and_reconciliation_safety_are_locked() -> None:
    mail = source("services/platform/email_delivery.py")
    worker = source("worker/worker.py")
    shadow = source("engine/shadow_outcome_worker.py")
    assert "SignalRankAI <hello@criloxsolutions.com>" in mail
    assert "EMAIL_REPLY_TO" in mail
    reconciliation = worker[
        worker.index("async def _outcome_reconciliation_loop"):
        worker.index("async def _adaptive_learning_loop")
    ]
    assert reconciliation.index('"outcome_reconciliation.performance"') < reconciliation.index('"outcome_reconciliation.outbox"')
    assert "notification outbox repair deferred after truth reconciliation" in reconciliation
    assert 'type(exc).__name__ == "AnalyticsWorkDeferred"' in shadow


def test_canonical_frontend_is_a_responsive_workstation_not_a_single_dashboard() -> None:
    html = source("web/platform_app/index.html")
    css = source("web/platform_app/styles.css")
    app = source("web/platform_app/app.js")
    sw = source("web/platform_app/service-worker.js")
    for view in ("overview", "signals", "evidence", "markets", "tools", "paper", "portfolio", "performance", "journal", "support", "account", "ops"):
        assert f'id="{view}View"' in html
    assert "workspace-nav" in html
    assert "workspaceSearch" in html
    assert "commandSearch" in html
    assert "@media(max-width:700px)" in css
    assert "@media(min-width:1320px)" in css
    assert "initTheme" in app
    assert "signalrank-shell-v34" in sw

def test_worker_db_backpressure_is_classified_as_expected_deferral() -> None:
    worker = source("worker/worker.py")
    assert '[worker] task deferred by DB admission:' in worker
    assert '[outcome_reconciliation] deferred reason=db_foreground_pressure' in worker
    task_block = worker[
        worker.index("def _log_task_result"):
        worker.index("def _spawn_task")
    ]
    assert 'type(exc).__name__ == "AnalyticsWorkDeferred"' in task_block
    reconciliation = worker[
        worker.index("async def _outcome_reconciliation_loop"):
        worker.index("async def _adaptive_learning_loop")
    ]
    assert 'type(exc).__name__ == "AnalyticsWorkDeferred"' in reconciliation

