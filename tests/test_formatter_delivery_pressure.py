import time
from types import SimpleNamespace

import pytest


def _valid_signal(**overrides):
    signal = {
        "signal_id": "sig-test",
        "asset": "BTCUSDT",
        "direction": "long",
        "timeframe": "1h",
        "entry": 100.0,
        "stop_loss": 95.0,
        "take_profit": [110.0],
        "score": 50.0,
    }
    signal.update(overrides)
    return signal


def test_owner_low_score_is_not_silently_filtered():
    from signalrank_telegram.formatter import format_signal

    message = format_signal(_valid_signal(), user_tier="owner", display_tier="vip")

    assert message and "BTCUSDT" in message


def test_formatter_returns_safe_fallback_when_rich_formatter_is_empty(monkeypatch):
    from signalrank_telegram import formatter

    monkeypatch.setattr(formatter, "_format_signal_primary", lambda *args, **kwargs: "")
    message = formatter.format_signal(_valid_signal(reason=None, ai_reason=None), user_tier="owner")

    assert message
    assert "Entry" in message
    assert "Stop Loss" in message
    assert "Take Profit 1" in message


def test_formatter_fails_only_when_required_trade_fields_are_missing(monkeypatch):
    from signalrank_telegram import formatter

    monkeypatch.setattr(formatter, "_format_signal_primary", lambda *args, **kwargs: "")
    signal = _valid_signal(stop_loss=None)
    diagnostics = formatter.signal_format_diagnostics(signal)

    assert formatter.format_signal(signal, user_tier="owner") is None
    assert diagnostics["missing_required"] == ["stop_loss"]
    assert diagnostics["can_render_fallback"] is False


def test_formatter_failed_is_a_terminal_resend_state():
    from signalrank_telegram.bot import is_formatter_failure_terminal

    assert is_formatter_failure_terminal("formatter_failed") is True
    assert is_formatter_failure_terminal("failed") is False


@pytest.mark.asyncio
async def test_disabled_decision_log_never_opens_db_session(monkeypatch):
    from db import repository

    monkeypatch.setenv("DECISION_LOG_WRITE_ENABLED", "0")

    def fail_if_called(*args, **kwargs):
        raise AssertionError("DB session should not be opened")

    monkeypatch.setattr(repository, "get_session", fail_if_called)
    assert await repository.persist_decision_log(None, "BTCUSDT", "1h", "skipped") == 0


@pytest.mark.asyncio
async def test_noncritical_session_drops_immediately_when_gate_is_saturated(monkeypatch):
    from db import session as db_session

    monkeypatch.setenv("DB_NONCRITICAL_WRITE_DROP_ON_GATE_TIMEOUT", "1")
    acquired = 0
    try:
        for _ in range(db_session._session_gate_limit):
            if db_session._session_gate.acquire(blocking=False):
                acquired += 1
        started = time.monotonic()
        with pytest.raises(db_session.NoncriticalWriteDropped):
            async with db_session.get_session(noncritical=True):
                pass
        assert time.monotonic() - started < 0.5
    finally:
        for _ in range(acquired):
            db_session._session_gate.release()


def test_configured_crypto_provider_order(monkeypatch):
    from data.connector_registry import _provider_order

    connectors = SimpleNamespace(
        coinbase_get_candles=lambda *args: [],
        okx_get_candles=lambda *args: [],
        bybit_get_candles=lambda *args: [],
        kraken_get_candles=lambda *args: [],
        cryptocompare_get_candles=lambda *args: [],
        cryptocompare_get_candles_async=lambda *args: [],
    )
    monkeypatch.setenv("CRYPTO_MARKET_DATA_PROVIDERS", "coinbase,okx,bybit")

    names = [name for name, _ in _provider_order("crypto", connectors, async_mode=True)]

    assert names == ["coinbase_connector", "okx_connector", "bybit_connector"]


@pytest.mark.asyncio
async def test_configured_crypto_order_beats_health_reordering(monkeypatch):
    from data import fetcher
    from data import connector_registry

    attempts = []

    async def provider(name, symbol, timeframe, timeout=5):
        attempts.append(name)
        return [{"close": 1.0}] * 20

    providers = [
        ("coinbase_connector", lambda symbol, timeframe, timeout=5: provider("coinbase", symbol, timeframe, timeout)),
        ("okx_connector", lambda symbol, timeframe, timeout=5: provider("okx", symbol, timeframe, timeout)),
        ("bybit_connector", lambda symbol, timeframe, timeout=5: provider("bybit", symbol, timeframe, timeout)),
    ]
    monkeypatch.setenv("CRYPTO_MARKET_DATA_PROVIDERS", "coinbase,okx,bybit")
    monkeypatch.setenv("CRYPTO_PREFERRED_PROVIDER", "coinbase")
    monkeypatch.setattr(connector_registry, "get_async_providers_for_asset", lambda asset_type: providers)
    monkeypatch.setattr(fetcher, "provider_is_healthy", lambda name: name != "coinbase_connector")

    candles = await fetcher.async_get_candles("BTCUSDT", "5m")

    assert len(candles) == 20
    assert attempts == ["coinbase"]


@pytest.mark.asyncio
async def test_gemini_429_is_fail_open_degraded(monkeypatch):
    import urllib.error
    from engine import core

    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("GEMINI_SIGNAL_REVIEW_ENABLED", "1")

    def rate_limited(*args, **kwargs):
        raise urllib.error.HTTPError("https://example.invalid", 429, "rate limited", {}, None)

    monkeypatch.setattr(core.urllib.request, "urlopen", rate_limited)
    ok, score, reason = await core._gemini_review_signal(
        _valid_signal(ml_probability=0.7, confidence=0.8),
        [],
        0.0,
    )

    assert ok is True
    assert "ai_review_status=rate_limited_degraded" in reason


def test_cycle_progress_and_scheduler_stagger_are_observable():
    from pathlib import Path

    core_source = Path("engine/core.py").read_text(encoding="utf-8")
    bot_source = Path("signalrank_telegram/bot.py").read_text(encoding="utf-8")

    assert "cycle_progress cycle=%s status=in_progress" in core_source
    assert "status=completed assets=" in core_source
    assert "OUTCOME_NOTIFICATION_START_DELAY_SECONDS" in bot_source
    assert "RESEND_START_DELAY_SECONDS" in bot_source
