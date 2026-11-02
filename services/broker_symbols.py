"""Map SignalRank symbols to each MT4/MT5 broker's own symbol names (2 Nov 2026).

Brokers name the same instrument differently: Exness Standard accounts trade
``EURUSDm`` and ``XAUUSDm``, cent accounts ``EURUSDc``, many brokers use
``US500.cash``, ``SPX500``, ``USTEC``, ``GER40.r``, ``XTIUSD`` or ``GOLD``.
Sending the canonical name to such a broker fails, or worse, hits a different
contract. This module reads the account's own symbol list once (MetaApi
``/symbols``), caches it, and resolves each canonical symbol to exactly one
broker symbol, or to nothing when the match is ambiguous or absent (the
caller then refuses the trade rather than guessing).
"""
from __future__ import annotations

import logging
import re
import time
from typing import Any, Iterable

logger = logging.getLogger(__name__)

# Canonical -> alternative base names used by brokers (before any suffix).
ALIASES: dict[str, tuple[str, ...]] = {
    "US500": ("SPX500", "SP500", "US500CASH", "USA500", "SPX", "US500ROLL"),
    "NAS100": ("USTEC", "US100", "NDX100", "NAS100CASH", "USTECH", "NQ100", "US100CASH"),
    "US30": ("DJ30", "WS30", "DOW30", "US30CASH", "USA30", "DJI30"),
    "GER40": ("DE40", "GER30", "DAX40", "DE30", "GER40CASH", "DAX"),
    "UK100": ("FTSE100", "UK100CASH", "FTSE"),
    "JP225": ("JPN225", "NIKKEI225", "JP225CASH", "NI225"),
    "FRA40": ("FRA40CASH", "CAC40", "F40"),
    "EU50": ("STOXX50", "EUSTX50", "EU50CASH", "ESTX50"),
    "AUS200": ("AUS200CASH", "ASX200", "AU200"),
    "HK50": ("HK50CASH", "HSI50", "HK33", "HSI"),
    "XAUUSD": ("GOLD",),
    "XAGUSD": ("SILVER",),
    "WTI": ("USOIL", "XTIUSD", "WTICRUDE", "CRUDEOIL", "OILCASH", "CL"),
    "BRENT": ("UKOIL", "XBRUSD", "BRENTCRUDE", "BRENTCASH"),
    "NATGAS": ("XNGUSD", "NGAS", "NATURALGAS"),
}

_MAX_SUFFIX = 5
_CACHE_SECONDS = 6 * 3600
_cache: dict[str, tuple[float, tuple[str, ...]]] = {}


def _key(name: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(name or "").upper())


def resolve_from_list(canonical: str, broker_symbols: Iterable[str]) -> str | None:
    """Pick the broker symbol for ``canonical`` or ``None`` when it is absent or ambiguous.

    Order of preference: the exact name; the name with only a short suffix or
    prefix (``EURUSDm``, ``EURUSD.r``, ``#AAPL``); then an alias with the same
    treatment. Among candidates of equal rank the shortest wins; a tie between
    different symbols is ambiguous.
    """
    symbols = [str(s) for s in broker_symbols or [] if str(s).strip()]
    target = _key(canonical)
    if not target:
        return None
    for name in (target, *ALIASES.get(target, ())):
        exact = [s for s in symbols if s.upper() == name]
        if len(exact) == 1:
            return exact[0]
        if exact:
            return None
        same = [s for s in symbols if _key(s) == name]  # "#AAPL", "EUR/USD"
        if len(same) == 1:
            return same[0]
        if len(same) > 1:
            return None
        candidates = [s for s in symbols if _suffix_ok(s, name)]
        if not candidates:
            continue
        candidates.sort(key=lambda s: (len(s), s))
        best = candidates[0]
        ties = [c for c in candidates if len(c) == len(best) and c != best]
        return None if ties else best
    return None


_KNOWN_SUFFIXES = frozenset({"PRO", "ECN", "RAW", "CASH", "STD", "MINI", "MICRO", "ZERO", "CFD", "SPOT", "ROLL"})


def _suffix_ok(raw: str, name: str) -> bool:
    """``raw`` is ``name`` plus a broker suffix: a separator (``.r``, ``-ecn``, ``_i``, ``+``),
    a single lower-case account letter (Exness ``m``/``c``), or a known word (``CASH``, ``PRO``)."""
    if not raw.upper().startswith(name) or len(raw) == len(name):
        return False
    rest = raw[len(name):]
    if len(rest) > _MAX_SUFFIX + 1:
        return False
    if rest[0] in ".-_#+!":
        return True
    if len(rest) == 1 and rest.islower():
        return True
    return rest.upper() in _KNOWN_SUFFIXES


async def broker_symbol_list(account_id: str) -> tuple[str, ...]:
    now = time.monotonic()
    cached = _cache.get(account_id)
    if cached and now - cached[0] < _CACHE_SECONDS:
        return cached[1]
    from services.mt5_client import _client_base, _deploy_account, _http_get

    await _deploy_account(account_id)
    data = await _http_get(f"{_client_base(account_id)}/symbols")
    symbols: tuple[str, ...] = ()
    if isinstance(data, list):
        symbols = tuple(str(item.get("symbol") if isinstance(item, dict) else item) for item in data if item)
    if symbols:
        _cache[account_id] = (now, symbols)
    return symbols


async def resolve_broker_symbol(account_id: str, canonical: str) -> str:
    """Broker symbol for an MT account; falls back to the canonical name if the list is unavailable."""
    canonical = str(canonical or "").upper().strip()
    try:
        symbols = await broker_symbol_list(str(account_id))
    except Exception:
        logger.debug("[broker_symbols] symbol list unavailable", exc_info=True)
        symbols = ()
    if not symbols:
        return canonical
    resolved = resolve_from_list(canonical, symbols)
    if resolved is None:
        logger.info("[broker_symbols] no unique broker symbol for %s", canonical)
        return canonical
    return resolved


__all__ = ["ALIASES", "broker_symbol_list", "resolve_broker_symbol", "resolve_from_list"]
