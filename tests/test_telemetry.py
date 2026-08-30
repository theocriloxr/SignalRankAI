from fastapi.testclient import TestClient

from core.telemetry import (
    observe_engine_cycle,
    observe_http_request,
    observe_ml_confidence,
    observe_signal_dispatch,
    prometheus_metrics_text,
)


def test_prometheus_metrics_text_contains_observations():
    observe_engine_cycle(0.25)
    observe_signal_dispatch(0.12, tier="vip", regime="trending", status="ok")
    observe_ml_confidence(0.73)
    observe_http_request("GET", "/health", 200, 0.01)

    metrics_text = prometheus_metrics_text()

    assert "signalrank_engine_cycle_seconds" in metrics_text
    assert "signalrank_signal_dispatch_seconds" in metrics_text
    assert "signalrank_ml_confidence" in metrics_text
    assert "signalrank_http_request_seconds" in metrics_text


def test_prometheus_endpoint_exposes_text_metrics():
    from web.app import app

    client = TestClient(app)
    response = client.get("/metrics/prometheus")

    assert response.status_code == 200
    assert "text/plain" in response.headers.get("content-type", "")
    assert "signalrank_service_up" in response.text


def test_shutdown_tracer_is_idempotent(monkeypatch):
    import core.telemetry as telemetry

    class Provider:
        def __init__(self):
            self.calls = 0

        def shutdown(self):
            self.calls += 1

    provider = Provider()
    monkeypatch.setattr(telemetry, "_TRACER", object())
    monkeypatch.setattr(telemetry, "_TRACER_PROVIDER", provider)
    monkeypatch.setattr(telemetry, "_TRACER_INITIALIZED", True)

    telemetry.shutdown_tracer()
    telemetry.shutdown_tracer()

    assert provider.calls == 1
    assert telemetry._TRACER is None
    assert telemetry._TRACER_PROVIDER is None
    assert telemetry._TRACER_INITIALIZED is True
