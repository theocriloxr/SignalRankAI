from __future__ import annotations

from scripts import post_deploy_smoke


def test_ready_check_requires_true_ready_contract(monkeypatch):
    monkeypatch.setattr(
        post_deploy_smoke,
        "_http_json",
        lambda *args, **kwargs: (200, {"status": "ready", "ready": True}, "", 3),
    )
    result = post_deploy_smoke._check_ready("https://example.test")
    assert result.ok is True


def test_ready_check_rejects_degraded_even_with_http_200(monkeypatch):
    monkeypatch.setattr(
        post_deploy_smoke,
        "_http_json",
        lambda *args, **kwargs: (200, {"status": "degraded", "ready": False}, "", 3),
    )
    result = post_deploy_smoke._check_ready("https://example.test")
    assert result.ok is False


def test_webhook_smoke_sends_secret_header(monkeypatch):
    captured = {}

    def fake_http(method, url, payload=None, timeout_s=15, extra_headers=None):
        captured.update(
            method=method,
            url=url,
            payload=payload,
            timeout_s=timeout_s,
            extra_headers=extra_headers,
        )
        return 200, {"ok": True, "queue_backend": "delivery_redis"}, "", 5

    monkeypatch.setattr(post_deploy_smoke, "_http_json", fake_http)
    result = post_deploy_smoke._check_webhook_enqueue(
        "https://example.test",
        webhook_secret="test-secret",
    )
    assert result.ok is True
    assert captured["extra_headers"] == {
        "X-Telegram-Bot-Api-Secret-Token": "test-secret"
    }
