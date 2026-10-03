import importlib
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient
import pytest


@pytest.mark.parametrize("path", ["/app", "/api/v1/platform/me"])
def test_throttled_http_requests_return_429_and_retry_after(monkeypatch, path):
    web = importlib.import_module("web.app")
    monkeypatch.setattr(web.state, "rate_limited", AsyncMock(return_value=True))
    client = TestClient(web.app, raise_server_exceptions=False)
    response = client.get(path)
    assert response.status_code == 429
    assert response.json() == {"detail": "Rate limit exceeded. Try again shortly."}
    assert response.headers["Retry-After"] == "60"


def test_health_probe_remains_available_when_clients_are_throttled(monkeypatch):
    web = importlib.import_module("web.app")
    limited = AsyncMock(return_value=True)
    monkeypatch.setattr(web.state, "rate_limited", limited)
    client = TestClient(web.app, raise_server_exceptions=False)
    assert client.get("/healthz").status_code == 200
    limited.assert_not_awaited()
