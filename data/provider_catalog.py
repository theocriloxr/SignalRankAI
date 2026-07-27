"""Canonical provider capability and certification catalogue.

This module is deliberately side-effect free.  Importing it never opens a
network or Redis connection.  Live certification is performed explicitly by
``scripts/certify_providers.py``.

The catalogue is the authoritative mapping between product asset classes and
implemented connector adapters.  A connector being importable is *not* proof
that the provider is production certified; certification status is recorded
separately by the certification script.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
import importlib
import math
import os
from typing import Any, Callable, Iterable, Mapping, Sequence


class CertificationStatus(str, Enum):
    IMPLEMENTED_NOT_LIVE_VERIFIED = "IMPLEMENTED_NOT_LIVE_VERIFIED"
    IMPLEMENTED_AND_PUBLIC_ENDPOINT_VERIFIED = "IMPLEMENTED_AND_PUBLIC_ENDPOINT_VERIFIED"
    IMPLEMENTED_AND_SANDBOX_VERIFIED = "IMPLEMENTED_AND_SANDBOX_VERIFIED"
    IMPLEMENTED_AND_LIVE_VERIFIED = "IMPLEMENTED_AND_LIVE_VERIFIED"
    IMPLEMENTED_AND_MOCK_VERIFIED = "IMPLEMENTED_AND_MOCK_VERIFIED"
    BLOCKED_MISSING_CREDENTIAL = "BLOCKED_MISSING_CREDENTIAL"
    BLOCKED_REGION = "BLOCKED_REGION"
    BLOCKED_NETWORK = "BLOCKED_NETWORK"
    BLOCKED_ACCOUNT_APPROVAL = "BLOCKED_ACCOUNT_APPROVAL"
    BLOCKED_PAID_PLAN = "BLOCKED_PAID_PLAN"
    DEPRECATED = "DEPRECATED"
    UNSUITABLE_FOR_PRODUCTION = "UNSUITABLE_FOR_PRODUCTION"
    ANALYSIS_ONLY = "ANALYSIS_ONLY"
    DISABLED = "DISABLED"
    FAILED = "FAILED"


@dataclass(frozen=True, slots=True)
class ProviderSpec:
    key: str
    display_name: str
    connector_module: str | None
    connector_attr: str | None
    asset_classes: tuple[str, ...]
    market_types: tuple[str, ...]
    timeframes: tuple[str, ...]
    roles: tuple[str, ...]
    docs_url: str
    required_env: tuple[str, ...] = ()
    required_env_all: tuple[tuple[str, ...], ...] = ()
    public_endpoint: bool = False
    sandbox: bool = False
    realtime_capable: bool = True
    regional_caveat: str | None = None
    enabled_env: str | None = None
    default_enabled: bool = True
    sample_symbol: str | None = None
    sample_timeframe: str = "1h"
    notes: str = ""

    def configured(self, env: Mapping[str, str] | None = None) -> bool:
        source = os.environ if env is None else env
        any_group_ok = True if not self.required_env else any(
            str(source.get(name, "")).strip() for name in self.required_env
        )
        all_groups_ok = all(
            any(str(source.get(name, "")).strip() for name in group)
            for group in self.required_env_all
        )
        return any_group_ok and all_groups_ok

    def enabled(self, env: Mapping[str, str] | None = None) -> bool:
        if not self.enabled_env:
            return self.default_enabled
        source = os.environ if env is None else env
        raw = source.get(self.enabled_env)
        if raw is None:
            return self.default_enabled
        return str(raw).strip().lower() in {"1", "true", "yes", "on"}

    def resolve_connector(self) -> Callable[..., Any] | None:
        if not self.connector_module or not self.connector_attr:
            return None
        module = importlib.import_module(self.connector_module)
        value = getattr(module, self.connector_attr)
        if not callable(value):
            raise TypeError(f"{self.connector_module}.{self.connector_attr} is not callable")
        return value

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


PROVIDER_SPECS: tuple[ProviderSpec, ...] = (
    ProviderSpec(
        "coinbase", "Coinbase Exchange", "data.connectors.coinbase_adapter", "get_candles",
        ("crypto_spot",), ("spot",), ("1m", "5m", "15m", "1h", "4h", "1d"),
        ("primary_realtime", "public"),
        "https://docs.cdp.coinbase.com/exchange/reference/exchangerestapi_getproductcandles",
        public_endpoint=True, sample_symbol="BTCUSD", sample_timeframe="5m",
    ),
    ProviderSpec(
        "okx", "OKX", "data.connectors.okx_adapter", "get_candles",
        ("crypto_spot", "crypto_perpetual", "crypto_futures", "crypto_options"),
        ("spot", "swap", "futures", "options"), ("1m", "5m", "15m", "1h", "4h", "1d"),
        ("primary_realtime", "public"),
        "https://www.okx.com/docs-v5/en/#rest-api-market-data-get-candlesticks",
        public_endpoint=True, sample_symbol="BTCUSDT", sample_timeframe="5m",
    ),
    ProviderSpec(
        "kraken", "Kraken", "data.connectors.kraken_adapter", "get_candles",
        ("crypto_spot",), ("spot",), ("1m", "5m", "15m", "1h", "4h", "1d"),
        ("secondary_realtime", "public"),
        "https://docs.kraken.com/api/docs/rest-api/get-ohlc-data/",
        public_endpoint=True, sample_symbol="BTCUSD", sample_timeframe="5m",
    ),
    ProviderSpec(
        "kucoin", "KuCoin", "data.connectors.kucoin_adapter", "get_candles",
        ("crypto_spot",), ("spot",), ("1m", "5m", "15m", "1h", "4h", "1d"),
        ("fallback_realtime", "public"),
        "https://www.kucoin.com/docs/rest/spot-trading/market-data/get-klines",
        public_endpoint=True, sample_symbol="BTCUSDT", sample_timeframe="5m",
    ),
    ProviderSpec(
        "bybit", "Bybit V5", "data.connectors.bybit_adapter", "get_candles",
        ("crypto_spot", "crypto_perpetual", "crypto_futures", "crypto_options"),
        ("spot", "linear", "inverse", "options"), ("1m", "5m", "15m", "1h", "4h", "1d"),
        ("fallback_realtime", "public"),
        "https://bybit-exchange.github.io/docs/v5/market/kline",
        public_endpoint=True, sample_symbol="BTCUSDT", sample_timeframe="5m",
    ),
    ProviderSpec(
        "binance", "Binance", "data.connectors.binance_adapter", "get_candles",
        ("crypto_spot", "crypto_perpetual", "crypto_futures"),
        ("spot", "linear", "inverse"), ("1m", "5m", "15m", "1h", "4h", "1d"),
        ("regional_fallback", "public"),
        "https://developers.binance.com/docs/binance-spot-api-docs/rest-api/market-data-endpoints",
        public_endpoint=True, regional_caveat="May be inaccessible from some Railway regions.",
        enabled_env="BINANCE_MARKET_DATA_ENABLED", default_enabled=False,
        sample_symbol="BTCUSDT", sample_timeframe="5m",
    ),
    ProviderSpec(
        "cryptocompare", "CryptoCompare", "data.connectors.cryptocompare_adapter", "cryptocompare_get_candles_sync",
        ("crypto_spot",), ("spot",), ("1m", "5m", "15m", "1h", "4h", "1d"),
        ("guarded_fallback",), "https://min-api.cryptocompare.com/documentation",
        required_env=("CRYPTOCOMPARE_API_KEY",), public_endpoint=True,
        sample_symbol="BTCUSD", sample_timeframe="1h",
    ),
    ProviderSpec(
        "yfinance", "Yahoo Finance / yfinance", "data.connectors.yfinance_adapter", "get_candles",
        ("equity", "index", "commodity_spot", "commodity_future", "forex", "macro", "volatility", "yield"),
        ("cash", "future", "index", "fx", "analysis"), ("1m", "5m", "15m", "1h", "4h", "1d"),
        ("best_effort_fallback", "historical"), "https://pypi.org/project/yfinance/",
        public_endpoint=True, realtime_capable=False, sample_symbol="AAPL", sample_timeframe="1d",
        notes="Unofficial/best-effort data source; never sole execution truth.",
    ),
    ProviderSpec(
        "twelvedata", "Twelve Data", "data.connectors.twelvedata_adapter", "get_candles",
        ("equity", "index", "forex", "commodity_spot", "crypto_spot"),
        ("cash", "index", "fx", "spot"), ("1m", "5m", "15m", "1h", "4h", "1d"),
        ("keyed_primary",), "https://twelvedata.com/docs",
        required_env=("TWELVEDATA_API_KEY", "TWELVE_DATA_API_KEY"), sample_symbol="AAPL", sample_timeframe="1h",
    ),
    ProviderSpec(
        "polygon", "Polygon", "data.connectors.polygon_adapter", "get_candles",
        ("equity", "index", "forex", "crypto_spot", "equity_option"),
        ("cash", "index", "fx", "spot", "options"), ("1m", "5m", "15m", "1h", "4h", "1d"),
        ("keyed_primary",), "https://polygon.io/docs/rest",
        required_env=("POLYGON_API_KEY",), sample_symbol="AAPL", sample_timeframe="1h",
    ),
    ProviderSpec(
        "tiingo", "Tiingo", "data.connectors.tiingo_adapter", "get_candles",
        ("equity", "forex", "crypto_spot"), ("cash", "fx", "spot"),
        ("1m", "5m", "15m", "1h", "4h", "1d"), ("keyed_fallback", "historical"),
        "https://api.tiingo.com/documentation/general/overview",
        required_env=("TIINGO_API_KEY",), sample_symbol="AAPL", sample_timeframe="1d",
    ),
    ProviderSpec(
        "fmp", "Financial Modeling Prep", "data.connectors.fmp_adapter", "get_candles",
        ("equity", "index", "forex", "commodity_spot", "macro"),
        ("cash", "index", "fx", "analysis"), ("1m", "5m", "15m", "1h", "4h", "1d"),
        ("keyed_primary",), "https://site.financialmodelingprep.com/developer/docs",
        required_env=("FMP_API_KEY",), sample_symbol="AAPL", sample_timeframe="1h",
    ),
    ProviderSpec(
        "alphavantage", "Alpha Vantage", "data.connectors.alphavantage_adapter", "get_candles",
        ("equity", "forex", "commodity_spot", "crypto_spot", "macro"),
        ("cash", "fx", "spot", "analysis"), ("1m", "5m", "15m", "1h", "1d"),
        ("keyed_fallback",), "https://www.alphavantage.co/documentation/",
        required_env=("ALPHAVANTAGE_API_KEY", "ALPHA_VANTAGE_API_KEY"),
        sample_symbol="AAPL", sample_timeframe="1h",
    ),
    ProviderSpec(
        "oanda", "OANDA v20", "data.connectors.oanda_adapter", "get_candles",
        ("forex", "commodity_spot", "index"), ("fx", "cfd"),
        ("1m", "5m", "15m", "1h", "4h", "1d"), ("practice_broker", "broker_validation"),
        "https://developer.oanda.com/rest-live-v20/instrument-ep/",
        required_env=("OANDA_API_KEY", "OANDA_TOKEN"), sandbox=True,
        sample_symbol="EURUSD", sample_timeframe="1h",
    ),
    ProviderSpec(
        "ecb", "European Central Bank", "data.connectors.ecb_adapter", "get_candles",
        ("forex", "macro"), ("reference_rate", "analysis"), ("1d",),
        ("analysis_only",), "https://data-api.ecb.europa.eu/",
        public_endpoint=True, realtime_capable=False, sample_symbol="EURUSD", sample_timeframe="1d",
        notes="Daily reference-rate context; not execution or intraday truth.",
    ),
    ProviderSpec(
        "deribit", "Deribit", "data.connectors.deribit_adapter", "get_candles",
        ("crypto_perpetual", "crypto_futures", "crypto_options"),
        ("perpetual", "future", "options"), ("1m", "5m", "15m", "1h", "4h", "1d"),
        ("public_derivatives",), "https://docs.deribit.com/", public_endpoint=True,
        default_enabled=False, sample_symbol="BTC-PERPETUAL", sample_timeframe="5m",
        notes="Public derivatives connector; enable only after regional/live certification.",
    ),
    ProviderSpec(
        "eodhd", "EODHD", "data.connectors.eodhd_adapter", "get_candles", ("equity", "index", "forex", "commodity_future", "crypto_spot"),
        ("cash", "index", "fx", "future"), ("1m", "5m", "1h", "1d"),
        ("historical", "delayed_intraday"), "https://eodhd.com/financial-apis/", required_env=("EODHD_API_KEY", "EODHD_API_TOKEN"),
        realtime_capable=False, default_enabled=False, sample_symbol="AAPL", sample_timeframe="1d",
    ),
    ProviderSpec(
        "marketstack", "Marketstack", "data.connectors.marketstack_adapter", "get_candles", ("equity", "index"), ("cash", "index"),
        ("1m", "5m", "15m", "1h", "1d"), ("historical", "delayed_intraday"),
        "https://marketstack.com/documentation", required_env=("MARKETSTACK_API_KEY",),
        realtime_capable=False, default_enabled=False, sample_symbol="AAPL", sample_timeframe="1d",
    ),
    ProviderSpec(
        "finnhub", "Finnhub", "data.connectors.finnhub_adapter", "get_candles", ("equity", "forex", "crypto_spot"),
        ("cash", "fx", "spot"), ("1m", "5m", "15m", "1h", "1d"), ("keyed_fallback",),
        "https://finnhub.io/docs/api", required_env=("FINNHUB_API_KEY",), default_enabled=False,
        sample_symbol="AAPL", sample_timeframe="1h",
    ),
    ProviderSpec(
        "alpaca", "Alpaca", "data.connectors.alpaca_adapter", "get_candles", ("equity", "crypto_spot", "equity_option"), ("cash", "spot", "options"),
        ("1m", "5m", "15m", "1h", "1d"), ("keyed_primary", "sandbox"),
        "https://docs.alpaca.markets/docs/market-data",
        required_env_all=(("ALPACA_API_KEY", "APCA_API_KEY_ID"), ("ALPACA_API_SECRET", "APCA_API_SECRET_KEY")),
        sandbox=True, default_enabled=False, sample_symbol="AAPL", sample_timeframe="1h",
    ),
    ProviderSpec(
        "tradier", "Tradier", "data.connectors.tradier_adapter", "get_candles", ("equity", "equity_option"), ("cash", "options"),
        ("1m", "5m", "15m"), ("keyed_fallback", "sandbox"),
        "https://documentation.tradier.com/", required_env=("TRADIER_TOKEN",), sandbox=True, default_enabled=False,
        sample_symbol="AAPL", sample_timeframe="5m",
    ),
    ProviderSpec(
        "nasdaq_data_link", "Nasdaq Data Link", "data.connectors.nasdaq_data_link_adapter", "get_candles",
        ("equity", "commodity_future", "macro"), ("historical", "analysis"), ("1d",),
        ("configured_historical",), "https://docs.data.nasdaq.com/",
        required_env_all=(("NASDAQ_DATA_LINK_API_KEY",), ("NASDAQ_DATA_LINK_DATASETS_JSON",)),
        realtime_capable=False, default_enabled=False, sample_symbol="GC", sample_timeframe="1d",
        notes="Requires NASDAQ_DATA_LINK_DATASETS_JSON symbol-to-dataset mapping.",
    ),
    ProviderSpec(
        "stooq", "Stooq", "data.connectors.stooq_adapter", "get_candles", ("equity", "index", "forex", "commodity_future"),
        ("historical",), ("1d",), ("public_historical",), "https://stooq.com/q/d/?s=aapl.us&i=d",
        public_endpoint=True, realtime_capable=False, default_enabled=False, sample_symbol="AAPL", sample_timeframe="1d",
    ),
)

_PROVIDER_BY_KEY = {spec.key: spec for spec in PROVIDER_SPECS}


def get_provider_spec(key: str) -> ProviderSpec:
    try:
        return _PROVIDER_BY_KEY[str(key).strip().lower()]
    except KeyError as exc:
        raise KeyError(f"unknown provider {key!r}") from exc


def list_provider_specs(*, implemented_only: bool = False) -> tuple[ProviderSpec, ...]:
    if not implemented_only:
        return PROVIDER_SPECS
    return tuple(spec for spec in PROVIDER_SPECS if spec.connector_module and spec.connector_attr)


def providers_for_asset_class(asset_class: str, *, enabled_only: bool = False) -> tuple[ProviderSpec, ...]:
    canonical = str(asset_class or "").strip().lower()
    specs = tuple(spec for spec in PROVIDER_SPECS if canonical in spec.asset_classes)
    if enabled_only:
        specs = tuple(spec for spec in specs if spec.enabled())
    return specs


def _parse_timestamp(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    if isinstance(value, (int, float)):
        number = float(value)
        if not math.isfinite(number):
            return None
        # Normalise milliseconds/microseconds/nanoseconds to seconds.
        while number > 10_000_000_000:
            number /= 1000.0
        return number
    text = str(value).strip()
    if not text:
        return None
    try:
        number = float(text)
    except ValueError:
        try:
            dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    return _parse_timestamp(number)


def validate_candles(
    candles: Sequence[Mapping[str, Any]] | Iterable[Mapping[str, Any]],
    *,
    minimum: int = 2,
) -> dict[str, Any]:
    """Validate normalized OHLCV candles without provider-specific assumptions."""
    rows = list(candles or [])
    errors: list[str] = []
    timestamps: list[float] = []

    if len(rows) < max(1, int(minimum)):
        errors.append(f"expected at least {minimum} candles, got {len(rows)}")

    for index, candle in enumerate(rows):
        if not isinstance(candle, Mapping):
            errors.append(f"row {index} is not a mapping")
            continue
        values: dict[str, float] = {}
        for field in ("open", "high", "low", "close"):
            try:
                value = float(candle[field])
            except (KeyError, TypeError, ValueError):
                errors.append(f"row {index} has invalid {field}")
                value = math.nan
            if not math.isfinite(value) or value <= 0:
                errors.append(f"row {index} has non-positive/non-finite {field}")
            values[field] = value

        if all(math.isfinite(values[field]) for field in values):
            if values["high"] < max(values["open"], values["close"], values["low"]):
                errors.append(f"row {index} violates high geometry")
            if values["low"] > min(values["open"], values["close"], values["high"]):
                errors.append(f"row {index} violates low geometry")

        volume = candle.get("volume", 0)
        try:
            volume_f = float(volume or 0)
            if not math.isfinite(volume_f) or volume_f < 0:
                errors.append(f"row {index} has invalid volume")
        except (TypeError, ValueError):
            errors.append(f"row {index} has invalid volume")

        timestamp = _parse_timestamp(candle.get("timestamp"))
        if timestamp is None or timestamp <= 0:
            errors.append(f"row {index} has invalid timestamp")
        else:
            timestamps.append(timestamp)

    if len(timestamps) > 1 and timestamps != sorted(timestamps):
        errors.append("timestamps are not ascending")
    if len(timestamps) != len(set(timestamps)):
        errors.append("duplicate timestamps")

    return {
        "valid": not errors,
        "count": len(rows),
        "first_timestamp": min(timestamps) if timestamps else None,
        "last_timestamp": max(timestamps) if timestamps else None,
        "errors": errors,
    }
