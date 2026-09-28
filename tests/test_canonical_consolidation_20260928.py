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
