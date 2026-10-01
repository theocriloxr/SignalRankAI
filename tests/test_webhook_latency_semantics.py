from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_webhook_latency_metrics_separate_queue_and_handler_time() -> None:
    source = (ROOT / "railway_main.py").read_text(encoding="utf-8")
    assert "signalrankai_webhook_queue_delay_seconds" in source
    assert "signalrankai_webhook_handler_duration_seconds" in source
    assert "WEBHOOK_QUEUE_DELAY_P99_SLO_SECONDS" in source
    assert "WEBHOOK_HANDLER_P99_SLO_SECONDS" in source
    assert '"webhook_queue_delay"' in source
    assert '"webhook_handler_duration"' in source
    assert '"webhook_dispatch_latency"' not in source[source.index("queue_p99 ="):source.index("out_p95 =")]
    assert "_record_dispatch_latency(str(payload_update_id), started_at, handler_started_at)" in source


def test_webhook_http_ingress_does_not_wait_for_handler_completion() -> None:
    source = (ROOT / "railway_main.py").read_text(encoding="utf-8")
    route = source[
        source.index('@app.post("/telegram/webhook")'):
        source.index("def _webhook_queue_diagnostics")
    ]
    assert "_bot_application.process_update" not in route
    assert "timeout=0.35" in route
    assert '"status": "queued"' in route
