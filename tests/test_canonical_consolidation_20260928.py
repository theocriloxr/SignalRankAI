from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def source(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_performance_truth_reconciles_before_notification_outbox() -> None:
    worker = source("worker/worker.py")
    start = worker.index("async def _outcome_reconciliation_loop")
    end = worker.index("async def _adaptive_learning_loop", start)
    block = worker[start:end]

    performance = block.index('"outcome_reconciliation.performance"')
    outbox = block.index('"outcome_reconciliation.outbox"')
    assert performance < outbox
    assert "notification outbox repair deferred after truth reconciliation" in block
    assert "persist_performance_reconciliation_result" in block


def test_shadow_tracker_treats_analytics_backpressure_as_expected_deferral() -> None:
    source_text = source("engine/shadow_outcome_worker.py")
    start = source_text.index("async def _run_loop")
    block = source_text[start:]
    assert 'type(exc).__name__ == "AnalyticsWorkDeferred"' in block
    assert "deferred reason=db_foreground_pressure" in block
    assert 'self._publish_health("deferred"' in block


def test_platform_hardening_survives_canonical_merge() -> None:
    app = source("web/platform_app/app.js")
    api = source("web/platform_api.py")
    web = source("web/app.py")
    mail = source("services/platform/email_delivery.py")

    for marker in (
        "refreshBrowserSession",
        "showBootstrapError",
        "reconcilePendingSecureLink",
        "confirmPendingBillingReturn",
        "document.querySelectorAll('.billing-checkout')",
    ):
        assert marker in app
    assert '@router.post("/billing/confirm")' in api
    assert "/transaction/verify/" in api
    assert '@app.get("/billing/complete"' in web
    assert '@app.get("/readyz"' in web
    assert "select(func.count()).select_from(Signal)" in web
    assert "SignalRankAI <hello@criloxsolutions.com>" in mail

def test_cross_channel_command_catalog_and_operator_controls_are_real_routes() -> None:
    api = source("web/platform_api.py")
    html = source("web/platform_app/index.html")
    app = source("web/platform_app/app.js")

    for route in (
        '@router.get("/command-catalog")',
        '@router.get("/operator/overview")',
        '@router.get("/operator/diagnostics")',
        '@router.post("/operator/ai-test")',
        '@router.post("/operator/kill-switch")',
    ):
        assert route in api
    assert "visible_commands(effective_tier)" in api
    assert 'id="commandCatalog"' in html
    assert 'id="opsView"' in html
    assert "loadCommandCatalog" in app
    assert "loadOperatorDiagnostics" in app
    assert "$$('[data-view]').filter" in app
    assert "$('[data-view]').filter" not in app


def test_operator_kill_switch_is_owner_only_and_confirmed() -> None:
    api = source("web/platform_api.py")
    section = api[
        api.index('@router.post("/operator/kill-switch")'):
        api.index('@router.post("/auth/register"')
    ]
    assert 'authority != "OWNER"' in section
    assert "payload.confirm is not True" in section
    assert "set_killswitch(True" in section
    assert "set_killswitch(False" in section


def test_pwa_cache_rotated_for_canonical_workstation() -> None:
    worker = source("web/platform_app/service-worker.js")
    assert "signalrank-shell-v27" in worker

