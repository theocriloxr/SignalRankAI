from __future__ import annotations

import asyncio

from data.provider_catalog import (
    CertificationStatus,
    get_provider_spec,
    list_provider_specs,
    providers_for_asset_class,
    validate_candles,
)
from scripts.certify_providers import certify_one


def _valid_rows():
    return [
        {"timestamp": 1_700_000_000_000, "open": 100, "high": 102, "low": 99, "close": 101, "volume": 5},
        {"timestamp": 1_700_000_300_000, "open": 101, "high": 103, "low": 100, "close": 102, "volume": 6},
    ]


def test_catalog_has_unique_keys_and_known_capabilities():
    specs = list_provider_specs()
    assert len(specs) == len({spec.key for spec in specs})
    assert "crypto_options" in get_provider_spec("bybit").asset_classes
    assert "forex" in get_provider_spec("oanda").asset_classes
    assert any(spec.key == "coinbase" for spec in providers_for_asset_class("crypto_spot"))


def test_normalized_candle_validator_enforces_geometry_and_order():
    assert validate_candles(_valid_rows())["valid"] is True

    invalid = _valid_rows()
    invalid[1] = dict(invalid[1], high=99)
    report = validate_candles(invalid)
    assert report["valid"] is False
    assert any("high geometry" in error for error in report["errors"])

    reverse = list(reversed(_valid_rows()))
    report = validate_candles(reverse)
    assert report["valid"] is False
    assert "timestamps are not ascending" in report["errors"]


def test_static_certification_is_not_reported_as_live():
    result = asyncio.run(certify_one(get_provider_spec("coinbase"), live=False, timeout=1, limit=2))
    assert result.implemented is True
    assert result.certification_status == CertificationStatus.IMPLEMENTED_AND_MOCK_VERIFIED.value
    assert "LIVE" not in result.certification_status


def test_missing_key_blocks_live_keyed_provider(monkeypatch):
    monkeypatch.setenv("FMP_ENABLED", "1")
    monkeypatch.delenv("FMP_API_KEY", raising=False)
    result = asyncio.run(certify_one(get_provider_spec("fmp"), live=True, timeout=1, limit=2))
    assert result.certification_status == CertificationStatus.BLOCKED_MISSING_CREDENTIAL.value


def test_external_plan_providers_are_opt_in_even_when_keys_exist(monkeypatch):
    monkeypatch.setenv("FMP_API_KEY", "present")
    monkeypatch.setenv("ALPHAVANTAGE_API_KEY", "present")
    monkeypatch.delenv("FMP_ENABLED", raising=False)
    monkeypatch.delenv("ALPHAVANTAGE_ENABLED", raising=False)

    fmp = get_provider_spec("fmp")
    alpha = get_provider_spec("alphavantage")
    assert fmp.configured() is True
    assert alpha.configured() is True
    assert fmp.enabled() is False
    assert alpha.enabled() is False


def test_oanda_and_fred_require_explicit_operator_enablement(monkeypatch):
    monkeypatch.setenv("OANDA_API_KEY", "present")
    monkeypatch.setenv("FRED_API_KEY", "present")
    monkeypatch.delenv("OANDA_ENABLED", raising=False)
    monkeypatch.delenv("FRED_ENABLED", raising=False)

    assert get_provider_spec("oanda").configured() is True
    assert get_provider_spec("oanda").enabled() is False
    assert get_provider_spec("fred").configured() is True
    assert get_provider_spec("fred").enabled() is False

    monkeypatch.setenv("OANDA_ENABLED", "1")
    monkeypatch.setenv("FRED_ENABLED", "1")
    assert get_provider_spec("oanda").enabled() is True
    assert get_provider_spec("fred").enabled() is True


def test_disabled_provider_is_not_misreported_as_live():
    result = asyncio.run(certify_one(get_provider_spec("deribit"), live=False, timeout=1, limit=2))
    assert result.implemented is True
    assert result.enabled is False
    assert result.certification_status == CertificationStatus.IMPLEMENTED_AND_MOCK_VERIFIED.value
    assert "LIVE" not in result.certification_status
