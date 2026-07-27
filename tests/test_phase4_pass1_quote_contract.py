import time
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from data.provider_types import (
    LivePriceFailure,
    LivePriceQuote,
    QuoteKind,
    validate_quote_for_final_delivery,
)


def _quote(
    *,
    symbol="BTCUSDT",
    asset_class="crypto",
    price=100.1,
    source_age=1.0,
    quote_kind="bid_ask",
    provider_health="healthy",
    breaker_state="closed",
    confidence=1.0,
):
    now = time.time()
    return LivePriceQuote(
        symbol=symbol,
        provider_symbol=symbol,
        asset_class=asset_class,
        price=price,
        bid=price - 0.01,
        ask=price + 0.01,
        provider="test-provider",
        fetched_at=now,
        received_at=now,
        completed_at=now,
        source_timestamp=now - source_age if source_age is not None else None,
        latency_ms=12,
        quote_kind=quote_kind,
        provider_health=provider_health,
        breaker_state=breaker_state,
        confidence=confidence,
        confidence_reasons=("fixture",),
    )


def _signal(**overrides):
    signal = {
        "asset": "BTCUSDT",
        "timeframe": "5m",
        "direction": "long",
        "entry": 100.0,
        "stop_loss": 98.0,
        "take_profit": [104.0, 108.0, 112.0],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    signal.update(overrides)
    return signal


@pytest.mark.parametrize(
    ("asset_class", "accepted_age", "rejected_age"),
    [
        ("crypto", 10.0, 10.001),
        ("fx", 15.0, 15.001),
        ("commodity", 15.0, 15.001),
        ("stock", 30.0, 30.001),
        ("index", 30.0, 30.001),
    ],
)
def test_final_quote_policy_enforces_asset_source_age_ceiling(asset_class, accepted_age, rejected_age):
    now = 2_000_000_000.0
    accepted = _quote(asset_class=asset_class)
    accepted = LivePriceQuote(
        **{
            field: getattr(accepted, field)
            for field in accepted.__dataclass_fields__
            if field not in {"source_timestamp", "request_id"}
        },
        source_timestamp=now - accepted_age,
    )
    rejected = LivePriceQuote(
        **{
            field: getattr(accepted, field)
            for field in accepted.__dataclass_fields__
            if field not in {"source_timestamp", "request_id"}
        },
        source_timestamp=now - rejected_age,
    )

    assert validate_quote_for_final_delivery(accepted, market_open=True, now=now).ok
    decision = validate_quote_for_final_delivery(rejected, market_open=True, now=now)
    assert not decision.ok
    assert decision.state == "BLOCKED_STALE"


def test_previous_close_is_analysis_only_at_final_send():
    decision = validate_quote_for_final_delivery(
        _quote(quote_kind=QuoteKind.PREVIOUS_CLOSE.value),
        market_open=True,
    )
    assert not decision.ok
    assert decision.reason == "analysis_only_previous_close"
    assert decision.state == "BLOCKED_PROVIDER_UNTRUSTED"


def test_db_tick_without_source_timestamp_is_rejected():
    decision = validate_quote_for_final_delivery(
        _quote(quote_kind=QuoteKind.DB_TICK.value, source_age=None),
        market_open=True,
    )
    assert not decision.ok
    assert decision.reason == "db_tick_missing_source_timestamp"


@pytest.mark.parametrize(
    ("changes", "reason_prefix"),
    [
        ({"provider_health": "unhealthy"}, "provider_health:"),
        ({"breaker_state": "open"}, "provider_breaker:"),
        ({"confidence": 0.5}, "confidence_too_low:"),
    ],
)
def test_untrusted_provider_evidence_fails_closed(changes, reason_prefix):
    decision = validate_quote_for_final_delivery(_quote(**changes), market_open=True)
    assert not decision.ok
    assert decision.reason.startswith(reason_prefix)
    assert decision.state == "BLOCKED_PROVIDER_UNTRUSTED"


def test_closed_market_blocks_otherwise_trusted_quote():
    decision = validate_quote_for_final_delivery(
        _quote(asset_class="stock", symbol="META"),
        market_open=False,
        market_reason="US cash market closed weekend",
    )
    assert not decision.ok
    assert decision.state == "BLOCKED_MARKET_CLOSED"


def test_cross_provider_divergence_blocks_quote():
    quote = _quote()
    quote = LivePriceQuote(
        **{
            field: getattr(quote, field)
            for field in quote.__dataclass_fields__
            if field not in {"cross_provider_deviation_pct", "request_id"}
        },
        cross_provider_deviation_pct=1.01,
    )
    decision = validate_quote_for_final_delivery(quote, market_open=True)
    assert not decision.ok
    assert decision.reason.startswith("cross_provider_deviation:")
    assert decision.state == "BLOCKED_PROVIDER_UNTRUSTED"


def test_instrument_registry_covers_required_asset_classes():
    from services.asset_mapper import canonicalize_symbol, get_instrument_spec

    expected = {
        "BNBUSDT": ("BNBUSDT", "crypto", "BNB-USD"),
        "META": ("META", "stock", "META"),
        "XAUUSD": ("XAUUSD", "commodity", "GC=F"),
        "EURUSD": ("EURUSD", "forex", "EURUSD=X"),
        "SPX500": ("US500", "index", "^GSPC"),
    }
    for symbol, (canonical, asset_class, yahoo_symbol) in expected.items():
        spec = get_instrument_spec(symbol)
        assert spec.canonical_symbol == canonical
        assert spec.asset_class == asset_class
        assert spec.provider_symbols["yfinance"] == yahoo_symbol
    assert canonicalize_symbol("BRK-B") == "BRK-B"


@pytest.mark.parametrize(
    ("symbol", "when", "is_open", "reason_fragment"),
    [
        ("BTCUSDT", datetime(2026, 7, 11, 12, tzinfo=timezone.utc), True, "24_7"),
        ("EURUSD", datetime(2026, 7, 11, 12, tzinfo=timezone.utc), False, "Saturday"),
        ("EURUSD", datetime(2026, 7, 12, 22, 1, tzinfo=timezone.utc), True, "open"),
        ("XAUUSD", datetime(2026, 7, 13, 21, 30, tzinfo=timezone.utc), False, "maintenance"),
        ("AAPL", datetime(2026, 1, 15, 15, 0, tzinfo=timezone.utc), True, "open"),
        ("AAPL", datetime(2026, 7, 14, 14, 0, tzinfo=timezone.utc), True, "open"),
        ("AAPL", datetime(2026, 7, 3, 15, 0, tzinfo=timezone.utc), False, "holiday"),
        ("US500", datetime(2026, 7, 12, 12, 0, tzinfo=timezone.utc), False, "Sunday"),
        ("US500", datetime(2026, 7, 13, 14, 0, tzinfo=timezone.utc), True, "open"),
    ],
)
def test_canonical_market_calendar_boundaries(monkeypatch, symbol, when, is_open, reason_fragment):
    from data.market_hours import get_market_session_status

    monkeypatch.delenv("INDEX_MARKET_MODE", raising=False)
    status = get_market_session_status(symbol, now_utc=when)
    assert status.is_open is is_open
    assert reason_fragment.lower() in status.reason.lower()


@pytest.mark.asyncio
async def test_final_validation_accepts_trusted_fresh_quote_and_records_provenance(monkeypatch):
    import engine.delivery_freshness as delivery
    import engine.stale_signal_validator as stale

    quote = _quote(price=100.1)

    async def trusted_quote(_symbol):
        return quote

    async def fresh(_signal, cached_live_price=None):
        return True, "fresh", cached_live_price

    monkeypatch.setattr(delivery, "_fetch_final_live_quote", trusted_quote)
    monkeypatch.setattr(stale, "validate_signal_freshness", fresh)

    result = await delivery.validate_delivery_freshness(
        _signal(),
        final_send=True,
        delivery_tier="premium",
    )

    assert result.ok
    assert result.state == "LIVE_CHECK_PASSED"
    assert result.quote_provider == quote.provider
    assert result.quote_request_id == quote.request_id
    assert result.quote_source_age_seconds is not None
    assert "quote_trust_passed" in result.rule_results
    assert "risk_geometry_passed" in result.rule_results


@pytest.mark.asyncio
async def test_final_validation_ignores_cached_price_and_rejects_stale_provider_quote(monkeypatch):
    import engine.delivery_freshness as delivery

    quote = _quote(price=100.1, source_age=20.0)
    calls = 0

    async def stale_quote(_symbol):
        nonlocal calls
        calls += 1
        return quote

    monkeypatch.setattr(delivery, "_fetch_final_live_quote", stale_quote)

    result = await delivery.validate_delivery_freshness(
        _signal(current_price=100.0),
        cached_live_price=100.0,
        final_send=True,
        delivery_tier="vip",
    )

    assert calls == 1
    assert not result.ok
    assert result.state == "BLOCKED_STALE"
    assert result.quote_request_id == quote.request_id


@pytest.mark.asyncio
async def test_final_validation_rejects_invalid_risk_geometry(monkeypatch):
    import engine.delivery_freshness as delivery

    async def trusted_quote(_symbol):
        return _quote(price=100.1)

    monkeypatch.setattr(delivery, "_fetch_final_live_quote", trusted_quote)
    result = await delivery.validate_delivery_freshness(
        _signal(stop_loss=101.0),
        final_send=True,
        delivery_tier="premium",
    )
    assert not result.ok
    assert result.state == "BLOCKED_RISK_INVALID"
    assert result.reason == "long_stop_must_be_below_entry"


def test_versioned_default_drift_limits_are_always_active(monkeypatch):
    from engine.delivery_freshness import _max_entry_drift_pct

    for env_name in (
        "FINAL_SEND_MAX_DRIFT_CRYPTO_PCT",
        "FINAL_SEND_MAX_DRIFT_FOREX_PCT",
        "FINAL_SEND_MAX_DRIFT_STOCK_PCT",
        "FINAL_SEND_MAX_DRIFT_COMMODITY_PCT",
        "FINAL_SEND_MAX_DRIFT_INDEX_PCT",
        "FINAL_SEND_MAX_DRIFT_DEFAULT_PCT",
    ):
        monkeypatch.delenv(env_name, raising=False)
    assert _max_entry_drift_pct("BTCUSDT") == 0.20
    assert _max_entry_drift_pct("EURUSD") == 0.08
    assert _max_entry_drift_pct("META") == 0.35
    assert _max_entry_drift_pct("XAUUSD") == 0.20
    assert _max_entry_drift_pct("US500") == 0.25


@pytest.mark.asyncio
async def test_yahoo_previous_close_payload_is_typed_as_analysis_only(monkeypatch):
    import requests
    import data.get_live_price as prices

    response = SimpleNamespace(
        ok=True,
        status_code=200,
        json=lambda: {
            "chart": {
                "result": [
                    {"meta": {"previousClose": 501.25, "chartPreviousClose": 500.0}}
                ]
            }
        },
    )
    monkeypatch.setattr(requests, "get", lambda *_args, **_kwargs: response)
    prices._price_breakers.clear()

    quote = await prices._fetch_yahoo_quote("META")
    assert isinstance(quote, LivePriceQuote)
    assert quote.quote_kind == QuoteKind.PREVIOUS_CLOSE.value
    assert quote.source_timestamp is None
    assert quote.untrusted_reason == "missing_source_timestamp"


@pytest.mark.asyncio
async def test_binance_adapter_preserves_source_time_and_bid_ask(monkeypatch):
    import requests
    import data.get_live_price as prices

    now_ms = int(time.time() * 1000)
    response = SimpleNamespace(
        ok=True,
        status_code=200,
        json=lambda: {
            "lastPrice": "601.10",
            "bidPrice": "601.09",
            "askPrice": "601.11",
            "closeTime": now_ms,
        },
    )
    monkeypatch.setattr(requests, "get", lambda *_args, **_kwargs: response)
    prices._price_breakers.clear()

    quote = await prices._fetch_binance_quote("BNBUSDT")
    assert isinstance(quote, LivePriceQuote)
    assert quote.quote_kind == QuoteKind.BID_ASK.value
    assert quote.source_timestamp == pytest.approx(now_ms / 1000.0)
    assert quote.bid == pytest.approx(601.09)
    assert quote.ask == pytest.approx(601.11)
    assert quote.provider_health == "healthy"


@pytest.mark.asyncio
async def test_price_result_exposes_typed_terminal_failure(monkeypatch):
    import data.get_live_price as prices

    async def failed(provider, symbol, timeout):
        return LivePriceFailure(symbol, provider, "fixture_failure")

    monkeypatch.setattr(prices, "_get_providers_for_asset", lambda _symbol: ["one", "two"])
    monkeypatch.setattr(prices, "_fetch_structured_quote", failed)
    result = await prices.get_live_price_result("BTCUSDT")
    assert isinstance(result, LivePriceFailure)
    assert result.reason.startswith("all_providers_failed:")
    assert "one:fixture_failure" in result.reason
