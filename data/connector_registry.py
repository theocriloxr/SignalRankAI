"""Connector registry providing ordered provider callables per asset type.

This module tries to surface pluggable connector adapters (under
`data.connectors`) when available and falls back to legacy provider
functions implemented in `data.providers`.
"""
from typing import Callable, List, Tuple


def _wrap_callable(fn: Callable, /) -> Callable:
    """Wrap various provider call signatures to a unified (symbol, tf, timeout) API."""
    def _call(symbol: str, tf: str, timeout: int = 10):
        try:
            # Try common signatures
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


def get_providers_for_asset(asset_type: str) -> List[Tuple[str, Callable]]:
    """Return a prioritized list of (name, callable) providers for asset_type.

    asset_type: 'crypto' | 'fx' | 'stock'
    """
    providers = []

    # Try to import connector adapters first
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
            # alphavantage is used via fetch_fx_candles in fetcher
    except Exception:
        pass

    return providers
