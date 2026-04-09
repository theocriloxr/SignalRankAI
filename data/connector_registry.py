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
    kind = str(asset_type or "").lower().strip()
    if kind == "commodity":
        kind = "stock"

    try:
        from data import connectors as c
    except Exception:
        c = None

    if kind == "crypto":
        ordered = [
            ("binance_connector", getattr(c, "binance_get_candles", None)),
            ("bybit_connector", getattr(c, "bybit_get_candles", None)),
            ("cryptocompare_connector", getattr(c, "cryptocompare_get_candles", None)),
        ]
    else:
        # Traditional assets: prefer premium feeds first, then yfinance safety net.
        ordered = [
            ("polygon_connector", getattr(c, "polygon_get_candles", None)),
            ("twelvedata_connector", getattr(c, "twelvedata_get_candles", None)),
            ("yfinance_connector", getattr(c, "yfinance_get_candles", None)),
        ]

    for name, fn in ordered:
        if fn is not None:
            providers.append((name, _wrap_callable(fn)))

    # Final legacy safety net in same priority shape.
    try:
        from data import providers as legacy
        if kind != "crypto":
            providers.extend(
                [
                    ("polygon_legacy", _wrap_callable(legacy.fetch_polygon_candles)),
                    ("twelvedata_legacy", _wrap_callable(legacy.fetch_twelvedata_candles)),
                    ("yahoo_legacy", _wrap_callable(legacy.fetch_yahoo_candles)),
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
    if kind == "commodity":
        kind = "stock"

    try:
        from data import connectors as c
    except Exception:
        c = None

    if kind == "crypto":
        ordered = [
            ("binance_connector", getattr(c, "binance_get_candles", None)),
            ("bybit_connector", getattr(c, "bybit_get_candles", None)),
            (
                "cryptocompare_connector",
                getattr(c, "cryptocompare_get_candles_async", None)
                or getattr(c, "cryptocompare_get_candles", None),
            ),
        ]
    else:
        # Traditional assets: premium feeds first, then yfinance fallback.
        ordered = [
            ("polygon_connector", getattr(c, "polygon_get_candles", None)),
            ("twelvedata_connector", getattr(c, "twelvedata_get_candles", None)),
            ("yfinance_connector", getattr(c, "yfinance_get_candles", None)),
        ]

    for name, fn in ordered:
        if fn is not None:
            providers.append((name, _wrap_to_async(fn)))

    return providers
