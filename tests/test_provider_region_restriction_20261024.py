"""Region blocks are classified, surfaced and backed off — never silently retried."""
from __future__ import annotations

import asyncio
import logging

from data.provider_failures import (
    PERMANENT_REASONS,
    ProviderFailureReason,
    classify_failure,
    classify_http_status,
)


def test_http_451_is_a_permanent_region_restriction():
    assert classify_http_status(451) is ProviderFailureReason.REGION_RESTRICTED
    assert ProviderFailureReason.REGION_RESTRICTED in PERMANENT_REASONS
    failure = classify_failure(provider="binance", capability="candles", status_code=451)
    assert failure.reason is ProviderFailureReason.REGION_RESTRICTED
    assert failure.is_retryable is False


def test_explicit_specific_reason_is_not_overwritten_by_generic_status():
    failure = classify_failure(
        provider="binance",
        capability="candles",
        reason=ProviderFailureReason.REGION_RESTRICTED,
        status_code=403,
    )
    assert failure.reason is ProviderFailureReason.REGION_RESTRICTED
    # Without an explicit reason the status mapping is still used.
    assert classify_failure(provider="x", status_code=403).reason is ProviderFailureReason.HTTP_403
    assert classify_failure(provider="x", status_code=429).is_retryable is True


class _Response:
    def __init__(self, status_code: int, text: str):
        self.status_code = status_code
        self.text = text

    def json(self):  # pragma: no cover - never reached for failures
        raise AssertionError("failure bodies must not be parsed as candles")


class _Client:
    def __init__(self, response):
        self.calls = 0
        self.response = response

    async def get(self, url, params=None, timeout=None):
        self.calls += 1
        return self.response


def test_binance_region_block_is_logged_once_and_backs_off(monkeypatch, caplog):
    from data.connectors import binance_adapter

    monkeypatch.setattr(binance_adapter, "_region_blocked_until", 0.0)
    client = _Client(_Response(451, '{"code":0,"msg":"Service unavailable from a restricted location"}'))
    monkeypatch.setattr(binance_adapter.httpx_client, "get_client", lambda name: client)
    caplog.set_level(logging.WARNING, logger=binance_adapter.logger.name)

    first = asyncio.run(binance_adapter._async_get_candles("BTCUSDT", "1h"))
    second = asyncio.run(binance_adapter._async_get_candles("ETHUSDT", "1h"))

    assert first == [] and second == []
    assert client.calls == 1, "a region-blocked provider must not be called again during the cooldown"
    assert binance_adapter.region_restricted() is True
    warnings = [r for r in caplog.records if "region_restricted" in r.getMessage()]
    assert len(warnings) == 1


def test_ordinary_binance_errors_do_not_trigger_the_region_cooldown(monkeypatch):
    from data.connectors import binance_adapter

    monkeypatch.setattr(binance_adapter, "_region_blocked_until", 0.0)
    client = _Client(_Response(500, "internal error"))
    monkeypatch.setattr(binance_adapter.httpx_client, "get_client", lambda name: client)
    asyncio.run(binance_adapter._async_get_candles("BTCUSDT", "1h"))
    asyncio.run(binance_adapter._async_get_candles("BTCUSDT", "1h"))
    assert client.calls == 2
    assert binance_adapter.region_restricted() is False
