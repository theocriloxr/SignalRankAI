"""Regression tests: V2.0 provider failure taxonomy and canonical instruments."""
from __future__ import annotations

from decimal import Decimal

import pytest

from data.canonical_instruments import (
    CanonicalInstrument,
    InstrumentRegistry,
    InstrumentStatus,
    direction_canonical,
    normalize_symbol,
)
from data.provider_contracts import AssetClass, CanonicalInstrumentId, InstrumentKind
from data.provider_failures import (
    PERMANENT_REASONS,
    RETRYABLE_REASONS,
    ProviderFailureReason,
    classify_failure,
    classify_http_status,
)


# ── Failure taxonomy ─────────────────────────────────────────────────────────

def test_classify_http_status() -> None:
    assert classify_http_status(403) is ProviderFailureReason.HTTP_403
    assert classify_http_status(404) is ProviderFailureReason.HTTP_404
    assert classify_http_status(429) is ProviderFailureReason.HTTP_429
    assert classify_http_status(503) is ProviderFailureReason.PROVIDER_MAINTENANCE
    assert classify_http_status(418) is ProviderFailureReason.UNKNOWN


def test_permanent_vs_retryable_classification() -> None:
    assert ProviderFailureReason.UNSUPPORTED_SYMBOL in PERMANENT_REASONS
    assert ProviderFailureReason.RATE_LIMITED in RETRYABLE_REASONS
    assert ProviderFailureReason.UNSUPPORTED_SYMBOL not in RETRYABLE_REASONS


def test_classify_failure_infers_from_status() -> None:
    failure = classify_failure(
        provider="MetaApi",
        capability="live_quotes",
        status_code=429,
        message="rate limited",
    )
    assert failure.reason is ProviderFailureReason.HTTP_429
    assert failure.is_retryable is True
    assert failure.permanent is False


def test_classify_failure_explicit_reason() -> None:
    failure = classify_failure(
        provider="fcs",
        capability="live_quotes",
        reason=ProviderFailureReason.INVALID_INSTRUMENT,
    )
    assert failure.reason is ProviderFailureReason.INVALID_INSTRUMENT
    assert failure.is_retryable is False


# ── Canonical instruments ───────────────────────────────────────────────────

def _instrument(symbol: str = "BTC/USDT") -> CanonicalInstrument:
    return CanonicalInstrument(
        id=CanonicalInstrumentId(
            asset_class=AssetClass.CRYPTO,
            kind=InstrumentKind.SPOT,
            base="BTC",
            quote="USDT",
        ),
        venue="binance",
        provider_symbol=symbol,
        tick_size=Decimal("0.01"),
        quantity_step=Decimal("0.001"),
        minimum_quantity=Decimal("0.001"),
        minimum_notional=Decimal("5"),
        aliases=("BTCUSDT", "BTC-USD", "BTCUSD"),
    )


def test_instrument_validates_negative_calibration() -> None:
    with pytest.raises(ValueError):
        _instrument().price_after_split(price=100, split_ratio=0)
    with pytest.raises(ValueError):
        CanonicalInstrument(
            id=_instrument().id,
            venue="x",
            provider_symbol="X",
            tick_size=Decimal("-0.01"),
        )


def test_instrument_split_adjustment() -> None:
    instrument = _instrument()
    assert instrument.price_after_split(price=Decimal("100"), split_ratio=Decimal("2")) == Decimal("50")
    assert instrument.price_after_split(price=Decimal("100"), split_ratio=Decimal("0.5")) == Decimal("200")


def test_normalize_symbol() -> None:
    assert normalize_symbol("BTC/USDT") == "BTCUSDT"
    assert normalize_symbol(" btc_usdt ") == "BTCUSDT"
    assert normalize_symbol("BTCUSDT") == "BTCUSDT"


def test_direction_canonical() -> None:
    assert direction_canonical("BUY") == "long"
    assert direction_canonical("SHORT") == "short"
    assert direction_canonical("LONG") == "long"
    with pytest.raises(ValueError):
        direction_canonical("sideways")


def test_instrument_registry_alias_resolution() -> None:
    instrument = _instrument()
    registry = InstrumentRegistry(instruments={instrument.canonical_key: instrument})
    assert registry.resolve("BTCUSDT") is instrument
    assert registry.resolve("btc-usd") is instrument
    assert registry.resolve("DOGEUSDT") is None


def test_instrument_registry_active_filter() -> None:
    instrument = _instrument()
    delisted = CanonicalInstrument(
        id=CanonicalInstrumentId(
            asset_class=AssetClass.CRYPTO,
            kind=InstrumentKind.SPOT,
            base="DOGE",
            quote="USDT",
        ),
        venue="binance",
        provider_symbol="DOGE/USDT",
        status=InstrumentStatus.DELISTED,
    )
    registry = InstrumentRegistry(
        instruments={
            instrument.canonical_key: instrument,
            delisted.canonical_key: delisted,
        }
    )
    assert len(registry.active()) == 1
    assert registry.active()[0].provider_symbol == "BTC/USDT"
