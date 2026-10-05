"""Connector registry providing prioritized provider callables.

Two helper apis are provided:
- `get_providers_for_asset(asset_type)` returns a list of sync callables
  (name, fn) for code that expects blocking functions.
- `get_async_providers_for_asset(asset_type)` returns a list of async
  callables (name, async_fn) suitable for `await`-able pipelines.

This module prefers connector adapters under `data.connectors` when
available and falls back to legacy functions in `data.providers`.
"""

from typing import Callable, List, Tuple
import asyncio
import inspect
import os


def _wrap_callable(fn: Callable, /) -> Callable:
    """Wrap various provider call signatures to a unified (symbol, tf, timeout) API."""

    try:
        signature = inspect.signature(fn)
    except (ValueError, TypeError):
        signature = None

    def _call(symbol: str, tf: str, timeout: int = 10):
        try:
            kwargs = {}
            if signature is not None:
                accepts_kwargs = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in signature.parameters.values())
                for name, value in (("timeout", timeout), ("limit", 200)):
                    parameter = signature.parameters.get(name)
                    if accepts_kwargs or (parameter is not None and parameter.kind != inspect.Parameter.POSITIONAL_ONLY):
                        kwargs[name] = value
                signature.bind(symbol, tf, **kwargs)
            # Call once: a TypeError inside a provider must not trigger another
            # external request or silently discard the caller's timeout.
            return fn(symbol, tf, **kwargs)
        except Exception:
            return []

    return _call


def _wrap_to_async(fn: Callable) -> Callable:
    """Return an async callable for `fn`.

    - If `fn` is already async, return it.
    - Otherwise run it in a thread via `asyncio.to_thread`.
    """
    if inspect.iscoroutinefunction(fn):
        wrapped = _wrap_callable(fn)

        async def _call_native_async(symbol: str, tf: str, timeout: int = 10):
            result = wrapped(symbol, tf, timeout)
            return await result if inspect.isawaitable(result) else result

        return _call_native_async

    async def _call_async(symbol: str, tf: str, timeout: int = 10):
        return await asyncio.to_thread(_wrap_callable(fn), symbol, tf, timeout)

    return _call_async


def provider_order_env_name(asset_type: str) -> str | None:
    return {
        "crypto": "CRYPTO_MARKET_DATA_PROVIDERS", "fx": "FX_MARKET_DATA_PROVIDERS",
        "forex": "FX_MARKET_DATA_PROVIDERS", "stock": "STOCK_MARKET_DATA_PROVIDERS",
        "equity": "STOCK_MARKET_DATA_PROVIDERS", "index": "INDEX_MARKET_DATA_PROVIDERS",
        "commodity": "COMMODITY_MARKET_DATA_PROVIDERS",
    }.get(str(asset_type or "").strip().lower())


def _apply_configured_order(kind: str, providers: List[Tuple[str, Callable]]) -> List[Tuple[str, Callable]]:
    env_name = provider_order_env_name(kind)
    raw = os.getenv(env_name, "") if env_name else ""
    if not raw.strip():
        return providers
    selected = []
    seen = set()
    for value in raw.split(","):
        alias = value.strip().lower().removesuffix("_connector").removesuffix("_legacy")
        if alias == "yahoo":
            alias = "yfinance"
        if not alias or alias in seen:
            continue
        seen.add(alias)
        for name, fn in providers:
            candidate = name.removesuffix("_connector").removesuffix("_legacy")
            if ("yfinance" if candidate == "yahoo" else candidate) == alias:
                selected.append((name, fn))
                break
    # An explicit allowlist must not fall through to unrelated legacy feeds.
    # Missing credentials or unknown providers remain an empty, blocked chain.
    return selected


def _env_enabled(name: str, default: bool = True) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return bool(default)
    return str(raw).strip().lower() in {"1", "true", "yes", "y", "on"}


_PROVIDER_ENABLE_FLAGS: dict[str, tuple[str, bool]] = {
    "fcs_connector": ("FCS_ENABLED", True),
    "yfinance_connector": ("YFINANCE_ENABLED", True),
    "fmp_connector": ("FMP_ENABLED", False),
    "alphavantage_connector": ("ALPHAVANTAGE_ENABLED", False),
    "oanda_connector": ("OANDA_ENABLED", False),
}

_PROVIDER_KEYS: dict[str, tuple[str, ...]] = {
    "fcs_connector": ("FCS_API_KEY", "FCS_API_SECRET"),
    "twelvedata_connector": ("TWELVEDATA_API_KEY", "TWELVE_DATA_API_KEY"),
    "polygon_connector": ("MASSIVE_API_KEY", "POLYGON_API_KEY"),  # Massive (formerly Polygon.io) consolidated secret
    "tiingo_connector": ("TIINGO_API_KEY",),
    "fmp_connector": ("FMP_API_KEY",),
    "alphavantage_connector": ("ALPHAVANTAGE_API_KEY", "ALPHA_VANTAGE_API_KEY"),
    "oanda_connector": ("OANDA_API_KEY", "OANDA_TOKEN"),
    "eodhd_connector": ("EODHD_API_KEY", "EODHD_API_TOKEN"),
    "marketstack_connector": ("MARKETSTACK_API_KEY",),
    "finnhub_connector": ("FINNHUB_API_KEY",),
    "alpaca_connector": ("ALPACA_API_KEY", "APCA_API_KEY_ID"),
    "tradier_connector": ("TRADIER_TOKEN",),
    "nasdaq_data_link_connector": ("NASDAQ_DATA_LINK_API_KEY",),
}


def _provider_configured(name: str) -> bool:
    canonical = str(name or "").lower()
    enable_contract = _PROVIDER_ENABLE_FLAGS.get(canonical)
    if enable_contract is not None:
        flag_name, default_enabled = enable_contract
        if not _env_enabled(flag_name, default_enabled):
            return False
    required = _PROVIDER_KEYS.get(canonical)
    if not required:
        return True
    if canonical == "alpaca_connector":
        has_key = any(str(os.getenv(key) or "").strip() for key in ("ALPACA_API_KEY", "APCA_API_KEY_ID"))
        has_secret = any(str(os.getenv(key) or "").strip() for key in ("ALPACA_API_SECRET", "APCA_API_SECRET_KEY"))
        return has_key and has_secret
    if canonical == "nasdaq_data_link_connector":
        return bool(
            str(os.getenv("NASDAQ_DATA_LINK_API_KEY") or "").strip()
            and str(os.getenv("NASDAQ_DATA_LINK_DATASETS_JSON") or "").strip()
        )
    return any(str(os.getenv(key) or "").strip() for key in required)


def _default_provider_order(kind: str, c, *, async_mode: bool = False) -> List[Tuple[str, Callable]]:
    """Return production provider hierarchy by asset class.

    Binance is intentionally opt-in/demoted because Railway regions are often
    geo-blocked. Keep CoinGecko as last-resort crypto metadata/candle fallback.
    """
    kind = str(kind or "").lower().strip()
    binance_enabled = _env_enabled("BINANCE_MARKET_DATA_ENABLED", False)
    hyperliquid_enabled = _env_enabled("HYPERLIQUID_MARKET_DATA_ENABLED", False)
    crypto: List[Tuple[str, Callable]] = [
        ("okx_connector", getattr(c, "okx_get_candles", None)),
        ("bybit_connector", getattr(c, "bybit_get_candles", None)),
        ("coinbase_connector", getattr(c, "coinbase_get_candles", None)),
        ("kraken_connector", getattr(c, "kraken_get_candles", None)),
        (
            "cryptocompare_connector",
            (
                getattr(c, "cryptocompare_get_candles_async", None)
                if async_mode
                else getattr(c, "cryptocompare_get_candles", None)
            )
            or getattr(c, "cryptocompare_get_candles", None),
        ),
        ("kucoin_connector", getattr(c, "kucoin_get_candles", None)),
        # Public keyless discovery/fallback sources (never execution quotes).
        ("coingecko_connector", getattr(c, "coingecko_get_candles", None)),
        ("coinmetrics_connector", getattr(c, "coinmetrics_get_candles", None)),
    ]
    if binance_enabled:
        crypto.append(("binance_connector", getattr(c, "binance_get_candles", None)))
    if hyperliquid_enabled:
        # Venue, not an asset class: public market data only, fail-closed.
        crypto.append(("hyperliquid_connector", getattr(c, "hyperliquid_get_candles", None)))

    if kind in {"crypto_perpetual", "crypto_futures", "crypto_options", "derivative", "future", "option"}:
        derivative_providers: List[Tuple[str, Callable]] = [
            ("deribit_connector", getattr(c, "deribit_get_candles", None)),
            ("bybit_connector", getattr(c, "bybit_get_candles", None)),
            ("okx_connector", getattr(c, "okx_get_candles", None)),
        ]
        if hyperliquid_enabled:
            derivative_providers.append(("hyperliquid_connector", getattr(c, "hyperliquid_get_candles", None)))
        if binance_enabled and kind != "crypto_options":
            derivative_providers.append(("binance_connector", getattr(c, "binance_get_candles", None)))
        return derivative_providers

    if kind == "crypto":
        return crypto
    if kind in ("fx", "forex"):
        return [
            ("twelvedata_connector", getattr(c, "twelvedata_get_candles", None)),
            ("finnhub_connector", getattr(c, "finnhub_get_candles", None)),
            ("fcs_connector", getattr(c, "fcs_get_candles", None)),
            ("oanda_connector", getattr(c, "oanda_get_candles", None)),
            ("fmp_connector", getattr(c, "fmp_get_candles", None)),
            ("alphavantage_connector", getattr(c, "alphavantage_get_candles", None)),
            ("tiingo_connector", getattr(c, "tiingo_get_candles", None)),
            ("polygon_connector", getattr(c, "polygon_get_candles", None)),
            ("yfinance_connector", getattr(c, "yfinance_get_candles", None)),
            ("ecb_connector", getattr(c, "ecb_get_candles", None)),
        ]
    if kind == "commodity":
        return [
            ("fcs_connector", getattr(c, "fcs_get_candles", None)),
            ("fmp_connector", getattr(c, "fmp_get_candles", None)),
            ("twelvedata_connector", getattr(c, "twelvedata_get_candles", None)),
            ("alphavantage_connector", getattr(c, "alphavantage_get_candles", None)),
            ("oanda_connector", getattr(c, "oanda_get_candles", None)),
            ("yfinance_connector", getattr(c, "yfinance_get_candles", None)),
        ]
    if kind == "index":
        return [
            ("fcs_connector", getattr(c, "fcs_get_candles", None)),
            ("fmp_connector", getattr(c, "fmp_get_candles", None)),
            ("twelvedata_connector", getattr(c, "twelvedata_get_candles", None)),
            ("polygon_connector", getattr(c, "polygon_get_candles", None)),
            ("alphavantage_connector", getattr(c, "alphavantage_get_candles", None)),
            ("yfinance_connector", getattr(c, "yfinance_get_candles", None)),
        ]
    return [
        ("twelvedata_connector", getattr(c, "twelvedata_get_candles", None)),
        ("fcs_connector", getattr(c, "fcs_get_candles", None)),
        ("polygon_connector", getattr(c, "polygon_get_candles", None)),
        ("alpaca_connector", getattr(c, "alpaca_get_candles", None)),
        ("finnhub_connector", getattr(c, "finnhub_get_candles", None)),
        ("tradier_connector", getattr(c, "tradier_get_candles", None)),
        ("fmp_connector", getattr(c, "fmp_get_candles", None)),
        ("tiingo_connector", getattr(c, "tiingo_get_candles", None)),
        ("alphavantage_connector", getattr(c, "alphavantage_get_candles", None)),
        ("yfinance_connector", getattr(c, "yfinance_get_candles", None)),
    ]


def _provider_order(kind: str, c, *, async_mode: bool = False) -> List[Tuple[str, Callable]]:
    return _apply_configured_order(kind, _default_provider_order(kind, c, async_mode=async_mode))


def get_providers_for_asset(asset_type: str) -> List[Tuple[str, Callable]]:
    """Return sync (name, callable) providers for `asset_type`.

    asset_type: 'crypto' | 'fx' | 'stock' | 'commodity'

    IMPORTANT: Different asset types need different providers!
    - Crypto: binance, bybit, cryptocompare (ONLY crypto exchanges)
    - Stocks: twelvedata, polygon, yahoo (NOT crypto exchanges!)
    - Commodities: twelvedata, oanda, yahoo (NOT crypto exchanges!)
    - FX: twelvedata, polygon, oanda (NOT crypto exchanges!)
    """
    providers: List[Tuple[str, Callable]] = []
    kind = str(asset_type or "").lower().strip()

    # CRITICAL: Keep commodity separate from stock!
    # This is the fix for "Ghost Price" errors
    # Previously commodities were being sent to crypto providers which returned wrong data

    try:
        from data import connectors as c
    except Exception:
        c = None

    ordered = _provider_order(kind, c, async_mode=False)

    for name, fn in ordered:
        if fn is not None and _provider_configured(name):
            providers.append((name, _wrap_callable(fn)))

    # Final legacy safety net in same priority shape. The legacy CoinGecko
    # fallback is skipped when the adapter is already in the chain to avoid
    # double-fetching the same public endpoint.
    try:
        from data import providers as legacy

        if kind == "crypto":
            existing = {name for name, _ in providers}
            if "coingecko_connector" not in existing:
                providers.append(("coingecko_legacy", _wrap_callable(legacy.fetch_coingecko_candles)))
        else:
            existing = {name.replace("_connector", "").replace("_legacy", "") for name, _ in providers}
            legacy_candidates = [
                ("polygon_legacy", "polygon_connector", legacy.fetch_polygon_candles),
                ("twelvedata_legacy", "twelvedata_connector", legacy.fetch_twelvedata_candles),
                ("alphavantage_legacy", "alphavantage_connector", legacy.fetch_alphavantage_candles),
                ("oanda_legacy", "oanda_connector", legacy.fetch_oanda_candles),
                ("yahoo_legacy", "yfinance_connector", legacy.fetch_yahoo_candles),
                ("tradingview_legacy", "", legacy.fetch_tradingview_candles),
            ]
            for legacy_name, config_name, fn in legacy_candidates:
                alias = legacy_name.replace("_legacy", "")
                if alias in existing:
                    continue
                if config_name and not _provider_configured(config_name):
                    continue
                providers.append((legacy_name, _wrap_callable(fn)))
    except Exception:
        pass

    return _apply_configured_order(kind, providers)


def get_async_providers_for_asset(asset_type: str) -> List[Tuple[str, Callable]]:
    """Return async (name, async_callable) providers for `asset_type`.

    The returned callables are `async fn(symbol, timeframe)` and should
    return the same candle list as sync providers.
    """
    providers: List[Tuple[str, Callable]] = []
    kind = str(asset_type or "").lower().strip()

    try:
        from data import connectors as c
    except Exception:
        c = None

    ordered = _provider_order(kind, c, async_mode=True)

    for name, fn in ordered:
        if fn is not None and _provider_configured(name):
            providers.append((name, _wrap_to_async(fn)))

    # Add legacy fallbacks for async callers.
    try:
        from data import providers as legacy

        if kind == "crypto":
            providers.extend(
                [
                    ("coingecko_legacy", _wrap_to_async(legacy.fetch_coingecko_candles)),
                ]
            )
        else:
            existing = {name.replace("_connector", "").replace("_legacy", "") for name, _ in providers}
            legacy_candidates = [
                ("polygon_legacy", "polygon_connector", legacy.fetch_polygon_candles),
                ("twelvedata_legacy", "twelvedata_connector", legacy.fetch_twelvedata_candles),
                ("alphavantage_legacy", "alphavantage_connector", legacy.fetch_alphavantage_candles),
                ("oanda_legacy", "oanda_connector", legacy.fetch_oanda_candles),
                ("yahoo_legacy", "yfinance_connector", legacy.fetch_yahoo_candles),
                ("tradingview_legacy", "", legacy.fetch_tradingview_candles),
            ]
            for legacy_name, config_name, fn in legacy_candidates:
                alias = legacy_name.replace("_legacy", "")
                if alias in existing:
                    continue
                if config_name and not _provider_configured(config_name):
                    continue
                providers.append((legacy_name, _wrap_to_async(fn)))
    except Exception:
        pass

    return _apply_configured_order(kind, providers)
