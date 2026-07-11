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
    def _call(symbol: str, tf: str, timeout: int = 10):
        try:
            return fn(symbol, tf)
        except TypeError:
            try:
                return fn(symbol, tf, timeout=timeout)
            except TypeError:
                try:
                    return fn(symbol, tf, limit=200)
                except Exception:
                    return []
        except Exception:
            return []

    return _call


def _wrap_to_async(fn: Callable) -> Callable:
    """Return an async callable for `fn`.

    - If `fn` is already async, return it.
    - Otherwise run it in a thread via `asyncio.to_thread`.
    """
    if inspect.iscoroutinefunction(fn):
        return fn

    async def _call_async(symbol: str, tf: str, timeout: int = 10):
        return await asyncio.to_thread(_wrap_callable(fn), symbol, tf, timeout)

    return _call_async


def _env_enabled(name: str, default: bool = True) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return bool(default)
    return str(raw).strip().lower() in {"1", "true", "yes", "y", "on"}


def _provider_order(kind: str, c, *, async_mode: bool = False) -> List[Tuple[str, Callable]]:
    """Return production provider hierarchy by asset class.

    Binance is intentionally opt-in/demoted because Railway regions are often
    geo-blocked. Keep CoinGecko as last-resort crypto metadata/candle fallback.
    """
    kind = str(kind or "").lower().strip()
    binance_enabled = _env_enabled("BINANCE_MARKET_DATA_ENABLED", False)
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
    ]
    if binance_enabled:
        crypto.append(("binance_connector", getattr(c, "binance_get_candles", None)))

    if kind == "crypto":
        configured = [
            item.strip().lower().replace("_connector", "")
            for item in (os.getenv("CRYPTO_MARKET_DATA_PROVIDERS") or "").split(",")
            if item.strip()
        ]
        if configured:
            by_alias = {
                name.replace("_connector", ""): (name, fn)
                for name, fn in crypto
            }
            selected = [by_alias[name] for name in configured if name in by_alias]
            if selected:
                crypto = selected
        return crypto
    if kind in ("fx", "forex"):
        return [
            ("yfinance_connector", getattr(c, "yfinance_get_candles", None)),
            ("twelvedata_connector", getattr(c, "twelvedata_get_candles", None)),
            ("tiingo_connector", getattr(c, "tiingo_get_candles", None)),
            ("alphavantage_connector", getattr(c, "alphavantage_get_candles", None)),
            ("polygon_connector", getattr(c, "polygon_get_candles", None)),
            ("tradingview_connector", getattr(c, "tradingview_get_candles", None)),
        ]
    if kind == "commodity":
        return [
            ("yfinance_connector", getattr(c, "yfinance_get_candles", None)),
            ("twelvedata_connector", getattr(c, "twelvedata_get_candles", None)),
            ("fmp_connector", getattr(c, "fmp_get_candles", None)),
            ("alphavantage_connector", getattr(c, "alphavantage_get_candles", None)),
            ("oanda_connector", getattr(c, "oanda_get_candles", None)),
            ("tradingview_connector", getattr(c, "tradingview_get_candles", None)),
        ]
    if kind == "index":
        return [
            ("yfinance_connector", getattr(c, "yfinance_get_candles", None)),
            ("twelvedata_connector", getattr(c, "twelvedata_get_candles", None)),
            ("fmp_connector", getattr(c, "fmp_get_candles", None)),
            ("alphavantage_connector", getattr(c, "alphavantage_get_candles", None)),
            ("polygon_connector", getattr(c, "polygon_get_candles", None)),
            ("tradingview_connector", getattr(c, "tradingview_get_candles", None)),
        ]
    return [
        ("twelvedata_connector", getattr(c, "twelvedata_get_candles", None)),
        ("fmp_connector", getattr(c, "fmp_get_candles", None)),
        ("yfinance_connector", getattr(c, "yfinance_get_candles", None)),
        ("alphavantage_connector", getattr(c, "alphavantage_get_candles", None)),
        ("tiingo_connector", getattr(c, "tiingo_get_candles", None)),
        ("polygon_connector", getattr(c, "polygon_get_candles", None)),
        ("tradingview_connector", getattr(c, "tradingview_get_candles", None)),
    ]


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
        if fn is not None:
            providers.append((name, _wrap_callable(fn)))

    # Final legacy safety net in same priority shape.
    try:
        from data import providers as legacy
        if kind == "crypto":
            providers.extend(
                [
                    ("coingecko_legacy", _wrap_callable(legacy.fetch_coingecko_candles)),
                ]
            )
        else:
            providers.extend(
                [
                    ("polygon_legacy", _wrap_callable(legacy.fetch_polygon_candles)),
                    ("twelvedata_legacy", _wrap_callable(legacy.fetch_twelvedata_candles)),
                    ("alphavantage_legacy", _wrap_callable(legacy.fetch_alphavantage_candles)),
                    ("yahoo_legacy", _wrap_callable(legacy.fetch_yahoo_candles)),
                    ("tradingview_legacy", _wrap_callable(legacy.fetch_tradingview_candles)),
                ]
            )
    except Exception:
        pass

    return providers


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
        if fn is not None:
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
            providers.extend(
                [
                    ("polygon_legacy", _wrap_to_async(legacy.fetch_polygon_candles)),
                    ("twelvedata_legacy", _wrap_to_async(legacy.fetch_twelvedata_candles)),
                    ("alphavantage_legacy", _wrap_to_async(legacy.fetch_alphavantage_candles)),
                    ("yahoo_legacy", _wrap_to_async(legacy.fetch_yahoo_candles)),
                    ("tradingview_legacy", _wrap_to_async(legacy.fetch_tradingview_candles)),
                ]
            )
    except Exception:
        pass

    return providers
