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


def get_providers_for_asset(asset_type: str) -> List[Tuple[str, Callable]]:
    """Return sync (name, callable) providers for `asset_type`.

    asset_type: 'crypto' | 'fx' | 'stock'
    """
    providers: List[Tuple[str, Callable]] = []

    # Try to import connector adapters first (sync wrappers)
    try:
        from data.connectors import binance_get_candles
        providers.append(("binance_connector", _wrap_callable(binance_get_candles)))
    except Exception:
        pass

    try:
        from data.connectors import yfinance_get_candles
        providers.append(("yfinance_connector", _wrap_callable(yfinance_get_candles)))
    except Exception:
        pass

    try:
        from data.connectors import polygon_get_candles, twelvedata_get_candles
        providers.append(("polygon_connector", _wrap_callable(polygon_get_candles)))
        providers.append(("twelvedata_connector", _wrap_callable(twelvedata_get_candles)))
    except Exception:
        pass

    # Fall back to legacy providers if connectors absent
    try:
        from data import providers as legacy
        if asset_type == "crypto":
            providers.append(("yahoo_legacy", _wrap_callable(legacy.fetch_yahoo_candles)))
        if asset_type == "stock":
            providers.append(("yahoo_legacy", _wrap_callable(legacy.fetch_yahoo_candles)))
            providers.append(("polygon_legacy", _wrap_callable(legacy.fetch_polygon_candles)))
            providers.append(("twelvedata_legacy", _wrap_callable(legacy.fetch_twelvedata_candles)))
        if asset_type == "fx":
            providers.append(("oanda_legacy", _wrap_callable(legacy.fetch_oanda_candles)))
    except Exception:
        pass

    return providers


def get_async_providers_for_asset(asset_type: str) -> List[Tuple[str, Callable]]:
    """Return async (name, async_callable) providers for `asset_type`.

    The returned callables are `async fn(symbol, timeframe)` and should
    return the same candle list as sync providers.
    """
    providers: List[Tuple[str, Callable]] = []

    try:
        from data.connectors import binance_get_candles, yfinance_get_candles
    except Exception:
        binance_get_candles = None
        yfinance_get_candles = None

    try:
        from data.connectors import polygon_get_candles, twelvedata_get_candles
    except Exception:
        polygon_get_candles = None
        twelvedata_get_candles = None

    # Prefer adapter async variants when present; wrap sync ones to async
    if binance_get_candles is not None:
        providers.append(("binance_connector", _wrap_to_async(binance_get_candles)))
    if yfinance_get_candles is not None:
        providers.append(("yfinance_connector", _wrap_to_async(yfinance_get_candles)))
    if polygon_get_candles is not None:
        providers.append(("polygon_connector", _wrap_to_async(polygon_get_candles)))
    if twelvedata_get_candles is not None:
        providers.append(("twelvedata_connector", _wrap_to_async(twelvedata_get_candles)))

    # Legacy fallbacks
    try:
        from data import providers as legacy
        if asset_type == "crypto":
            providers.append(("yahoo_legacy", _wrap_to_async(legacy.fetch_yahoo_candles)))
        if asset_type == "stock":
            providers.append(("yahoo_legacy", _wrap_to_async(legacy.fetch_yahoo_candles)))
            providers.append(("polygon_legacy", _wrap_to_async(legacy.fetch_polygon_candles)))
            providers.append(("twelvedata_legacy", _wrap_to_async(legacy.fetch_twelvedata_candles)))
        if asset_type == "fx":
            providers.append(("oanda_legacy", _wrap_to_async(legacy.fetch_oanda_candles)))
    except Exception:
        pass

    return providers
