"""One canonical asset class per symbol, shared by every stage (10 Nov 2026).

Same rules as ``engine.core._asset_class_key``: the asset registry first, then
the market-data predicates. ``db.repository.persist_signal`` did not store the
class at all, so 42,702 of 43,340 recent ``signals`` rows had an empty
``asset_class`` (data audit, 10 Nov 2026); this module lets the writer and the
backfill use exactly the engine's classification.
"""
from __future__ import annotations

_ALIASES = {"forex": "fx", "equity": "stock", "equities": "stock", "indices": "index",
            "commodities": "commodity", "rates": "macro", "yield": "macro"}
_VALID = {"crypto", "fx", "index", "commodity", "stock", "macro", "volatility"}


def canonical_asset_class(asset: str) -> str:
    sym = str(asset or "").upper().strip()
    try:
        from services.asset_mapper import classify_asset

        mapped = str(classify_asset(sym) or "").strip().lower()
        mapped = _ALIASES.get(mapped, mapped)
        if mapped in _VALID:
            return mapped
    except Exception:
        pass
    from data.fetcher import is_commodity, is_crypto, is_fx, is_index

    if is_crypto(sym):
        return "crypto"
    if is_fx(sym):
        return "fx"
    if is_index(sym):
        return "index"
    if is_commodity(sym):
        return "commodity"
    try:
        from data.fetcher import is_macro_yield, is_stock

        if is_macro_yield(sym):
            return "macro"
        if is_stock(sym):
            return "stock"
    except Exception:
        pass
    return "other"
