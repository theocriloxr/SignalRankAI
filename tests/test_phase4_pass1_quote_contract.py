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
    assert _max_entry_drift_pct("BTCUSDT") == 0.50
    assert _max_entry_drift_pct("EURUSD") == 0.12
    assert _max_entry_drift_pct("META") == 0.35
    assert _max_entry_drift_pct("XAUUSD") == 0.30
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
async def test_twelvedata_metals_quote_preserves_source_time(monkeypatch):
    import requests
    import data.get_live_price as prices

    now = int(time.time())
    response = SimpleNamespace(
        ok=True,
        status_code=200,
        json=lambda: {
            "symbol": "XAG/USD",
            "close": "38.125",
            "timestamp": now,
            "is_market_open": True,
        },
    )
    monkeypatch.setenv("TWELVEDATA_API_KEY", "test-key")
    monkeypatch.setattr(requests, "get", lambda *_args, **_kwargs: response)
    prices._price_breakers.clear()

    quote = await prices._fetch_twelvedata_quote("XAGUSD")
    assert isinstance(quote, LivePriceQuote)
    assert quote.provider == "twelvedata"
    assert quote.provider_symbol == "XAG/USD"
    assert quote.price == pytest.approx(38.125)
    assert quote.source_timestamp == pytest.approx(now)
    assert quote.market_status == "open"


@pytest.mark.asyncio
async def test_twelvedata_quote_falls_back_to_timestamped_one_minute_bar(monkeypatch):
    import requests
    import data.get_live_price as prices

    now = int(time.time())
    calls = []

    def fake_get(url, **kwargs):
        calls.append((url, kwargs))
        if url.endswith("/quote"):
            return SimpleNamespace(ok=False, status_code=404, json=lambda: {})
        return SimpleNamespace(
            ok=True,
            status_code=200,
            json=lambda: {
                "status": "ok",
                "values": [{"datetime": datetime.fromtimestamp(now, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S"), "close": "38.250"}],
            },
        )

    monkeypatch.setenv("TWELVEDATA_API_KEY", "test-key")
    monkeypatch.setattr(requests, "get", fake_get)
    prices._price_breakers.clear()

    quote = await prices._fetch_twelvedata_quote("XAGUSD")
    assert isinstance(quote, LivePriceQuote)
    assert quote.provider_symbol == "XAG/USD"
    assert quote.price == pytest.approx(38.250)
    assert quote.source_timestamp == pytest.approx(now, abs=1.0)
    assert "quote_endpoint_fallback_time_series" in quote.confidence_reasons
    assert calls[-1][1]["params"]["interval"] == "1min"
    assert calls[-1][1]["params"]["outputsize"] == 1


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


@pytest.mark.asyncio
async def test_oanda_metals_quote_preserves_bid_ask_and_source_time(monkeypatch):
    import requests
    import data.get_live_price as prices

    captured = {}
    response = SimpleNamespace(
        ok=True,
        status_code=200,
        json=lambda: {
            "prices": [{
                "instrument": "XAG_USD",
                "status": "tradeable",
                "time": "2026-07-31T07:32:18.250000Z",
                "bids": [{"price": "38.120"}],
                "asks": [{"price": "38.130"}],
            }]
        },
    )

    def fake_get(url, **kwargs):
        captured["url"] = url
        captured.update(kwargs)
        return response

    monkeypatch.setenv("OANDA_API_KEY", "test-token")
    monkeypatch.setenv("OANDA_ACCOUNT_ID", "test-account")
    monkeypatch.setenv("OANDA_PRACTICE", "true")
    monkeypatch.setattr(requests, "get", fake_get)
    prices._price_breakers.clear()

    quote = await prices._fetch_oanda_quote("XAGUSD")
    assert isinstance(quote, LivePriceQuote)
    assert quote.provider == "oanda"
    assert quote.provider_symbol == "XAG_USD"
    assert quote.bid == pytest.approx(38.120)
    assert quote.ask == pytest.approx(38.130)
    assert quote.price == pytest.approx(38.125)
    assert quote.source_timestamp is not None
    assert "api-fxpractice.oanda.com" in captured["url"]
    assert captured["params"]["instruments"] == "XAG_USD"



@pytest.mark.parametrize(
    ("symbol", "expected"),
    [
        ("META", "META"),
        ("EURUSD", "EURUSD"),
        ("SPX500", "^GSPC"),
        ("NAS100", "^NDX"),
        ("XAUUSD", "GCUSD"),
        ("XAGUSD", "SIUSD"),
        ("WTI", "CLUSD"),
    ],
)
def test_fmp_symbol_mapping_is_asset_correct(symbol, expected):
    from services.asset_mapper import map_symbol

    assert map_symbol(symbol, "fmp") == expected


def test_fmp_is_preferred_before_rate_limited_public_traditional_fallbacks(monkeypatch):
    from data.get_live_price import _get_providers_for_asset

    monkeypatch.setenv("FMP_API_KEY", "test-fmp")
    monkeypatch.setenv("TWELVEDATA_API_KEY", "test-twelve")
    monkeypatch.setenv("POLYGON_API_KEY", "test-polygon")
    monkeypatch.delenv("META_API_TOKEN", raising=False)
    monkeypatch.delenv("METAAPI_TOKEN", raising=False)
    monkeypatch.delenv("OANDA_API_KEY", raising=False)
    monkeypatch.delenv("OANDA_TOKEN", raising=False)
    monkeypatch.delenv("OANDA_ACCOUNT_ID", raising=False)

    assert _get_providers_for_asset("EURUSD")[0] == "fmp"
    assert _get_providers_for_asset("META")[0] == "fmp"
    assert _get_providers_for_asset("US500")[0] == "fmp"
    assert _get_providers_for_asset("XAUUSD")[0] == "fmp"


@pytest.mark.asyncio
async def test_fmp_final_quote_preserves_provider_timestamp(monkeypatch):
    import requests
    import data.get_live_price as prices

    now = int(time.time())
    captured = {}
    response = SimpleNamespace(
        ok=True,
        status_code=200,
        json=lambda: [{
            "symbol": "^GSPC",
            "price": 6712.25,
            "timestamp": now,
        }],
    )

    def fake_get(url, **kwargs):
        captured["url"] = url
        captured.update(kwargs)
        return response

    monkeypatch.setenv("FMP_API_KEY", "test-key")
    monkeypatch.setattr(requests, "get", fake_get)
    prices._price_breakers.clear()

    quote = await prices._fetch_fmp_quote("US500")
    assert isinstance(quote, LivePriceQuote)
    assert quote.provider == "fmp"
    assert quote.provider_symbol == "^GSPC"
    assert quote.asset_class == "index"
    assert quote.price == pytest.approx(6712.25)
    assert quote.source_timestamp == pytest.approx(now)
    assert quote.quote_kind == QuoteKind.TICKER.value
    assert quote.confidence == pytest.approx(1.0)
    assert "timestamped_fmp_stable_quote" in quote.confidence_reasons
    assert captured["url"] == "https://financialmodelingprep.com/stable/quote"
    assert captured["params"]["symbol"] == "^GSPC"
    assert captured["params"]["apikey"] == "test-key"


@pytest.mark.asyncio
async def test_fmp_quote_without_source_timestamp_fails_closed(monkeypatch):
    import requests
    import data.get_live_price as prices

    response = SimpleNamespace(
        ok=True,
        status_code=200,
        json=lambda: [{"symbol": "META", "price": 742.10}],
    )
    monkeypatch.setenv("FMP_API_KEY", "test-key")
    monkeypatch.setattr(requests, "get", lambda *_args, **_kwargs: response)
    prices._price_breakers.clear()

    result = await prices._fetch_fmp_quote("META")
    assert isinstance(result, LivePriceFailure)
    assert result.provider == "fmp"
    assert result.reason == "source_timestamp_missing"



@pytest.mark.asyncio
async def test_delivery_fresh_failover_skips_stale_provider_quote(monkeypatch):
    import data.get_live_price as prices

    now = time.time()
    stale = _quote(
        symbol="EURUSD",
        asset_class="fx",
        price=1.17,
        source_age=45.0,
    )
    fresh = _quote(
        symbol="EURUSD",
        asset_class="fx",
        price=1.1702,
        source_age=2.0,
    )
    stale = LivePriceQuote(
        **{
            field: getattr(stale, field)
            for field in stale.__dataclass_fields__
            if field not in {"provider", "source_timestamp", "request_id"}
        },
        provider="fmp",
        source_timestamp=now - 45.0,
    )
    fresh = LivePriceQuote(
        **{
            field: getattr(fresh, field)
            for field in fresh.__dataclass_fields__
            if field not in {"provider", "source_timestamp", "request_id"}
        },
        provider="twelvedata",
        source_timestamp=now - 2.0,
    )

    monkeypatch.setattr(prices, "_get_providers_for_asset", lambda _symbol: ["fmp", "twelvedata"])

    async def fake_fetch(provider, _symbol, timeout):
        return stale if provider == "fmp" else fresh

    monkeypatch.setattr(prices, "_fetch_structured_quote", fake_fetch)

    result = await prices.get_live_price_result(
        "EURUSD",
        timeout=4.0,
        require_delivery_freshness=True,
    )
    assert isinstance(result, LivePriceQuote)
    assert result.provider == "twelvedata"
    assert result.price == pytest.approx(1.1702)


@pytest.mark.asyncio
async def test_analysis_quote_path_keeps_backward_compatible_first_timestamped_quote(monkeypatch):
    import data.get_live_price as prices

    stale = _quote(symbol="EURUSD", asset_class="fx", source_age=45.0)
    stale = LivePriceQuote(
        **{
            field: getattr(stale, field)
            for field in stale.__dataclass_fields__
            if field not in {"provider", "request_id"}
        },
        provider="fmp",
    )
    monkeypatch.setattr(prices, "_get_providers_for_asset", lambda _symbol: ["fmp", "twelvedata"])

    calls = []

    async def fake_fetch(provider, _symbol, timeout):
        calls.append(provider)
        return stale

    monkeypatch.setattr(prices, "_fetch_structured_quote", fake_fetch)

    result = await prices.get_live_price_result("EURUSD", timeout=4.0)
    assert isinstance(result, LivePriceQuote)
    assert result.provider == "fmp"
    assert calls == ["fmp"]


def test_final_delivery_fetch_requests_delivery_fresh_provider_failover():
    from pathlib import Path

    source = Path("engine/delivery_freshness.py").read_text(encoding="utf-8")
    section = source[
        source.index("async def _fetch_final_live_quote"):
        source.index("async def fetch_trusted_live_quote")
    ]
    assert "require_delivery_freshness=True" in section



@pytest.mark.asyncio
async def test_fcs_current_v4_flat_response_is_accepted(monkeypatch):
    import requests
    import data.get_live_price as prices

    now = int(time.time())
    response = SimpleNamespace(
        ok=True,
        status_code=200,
        json=lambda: {
            "status": True,
            "code": 200,
            "response": [{
                "ticker": "FX:EURUSD",
                "symbol": "EURUSD",
                "a": 1.1740,
                "b": 1.1738,
                "c": 1.1739,
                "t": now,
            }],
            "info": {"server_time": datetime.fromtimestamp(now, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")},
        },
    )
    monkeypatch.setenv("FCS_API_KEY", "test-key")
    monkeypatch.setattr(requests, "get", lambda *_args, **_kwargs: response)
    prices._price_breakers.clear()

    quote = await prices._fetch_fcs_quote("EURUSD")
    assert isinstance(quote, LivePriceQuote)
    assert quote.provider == "fcs"
    assert quote.bid == pytest.approx(1.1738)
    assert quote.ask == pytest.approx(1.1740)
    assert quote.source_timestamp == pytest.approx(now)


@pytest.mark.asyncio
async def test_fcs_current_v4_data_wrapper_and_utc_server_time_are_accepted(monkeypatch):
    import requests
    import data.get_live_price as prices

    now = int(time.time())
    server_time = datetime.fromtimestamp(now, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    response = SimpleNamespace(
        ok=True,
        status_code=200,
        json=lambda: {
            "status": True,
            "code": 200,
            "response": {
                "data": [{
                    "ticker": "FX:USDJPY",
                    "active": {"a": 148.34, "b": 148.32, "c": 148.33},
                }]
            },
            "info": {"server_time": server_time},
        },
    )
    monkeypatch.setenv("FCS_API_KEY", "test-key")
    monkeypatch.setattr(requests, "get", lambda *_args, **_kwargs: response)
    prices._price_breakers.clear()

    quote = await prices._fetch_fcs_quote("USDJPY")
    assert isinstance(quote, LivePriceQuote)
    assert quote.source_timestamp == pytest.approx(now, abs=1.0)
    assert quote.confidence == pytest.approx(1.0)
