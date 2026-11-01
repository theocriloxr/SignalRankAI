"""Pegged and reserve-backed crypto tokens (1 Nov 2026).

Stablecoins, tokenized gold and tokenized treasuries trade inside a band
around their reserve. They are not trend instruments: their tiny ranges make
a stop or target almost never resolve, so outcome labels on them are
meaningless. Production evidence on 1 Nov 2026:

- the discovered crypto universe was mostly such tokens (USDTB, USDU, PYUSD,
  RLUSD, BUIDL, PAXG...);
- the serving ML model scored them 0.87-0.93 while real coins scored 0.05-0.64.

They are therefore excluded from scanning and from ML training. The existing
``data.pair_discovery.STABLECOIN_PAIRS`` list only caught a dozen symbols; this
module recognises the whole family by name.

Gold itself (``XAUUSD``) is a commodity instrument, not a token, and is not
affected.
"""
from __future__ import annotations

import os

# Bases that are pegged or reserve-backed but do not follow a USD/EUR naming
# pattern. Upper case, without the quote currency.
_KNOWN_PEGGED_BASES = frozenset(
    {
        # USD stablecoins without "USD" at either end of the ticker
        "DAI", "FRAX", "MIM", "GHO", "DOLA", "BOLD", "BUCK", "USTC", "UST", "PAX", "TUSD",
        "BUSD", "FDUSD", "LUSD", "SUSD", "GUSD", "HUSD", "CUSD", "USDP", "USDD", "USDE",
        "USDS", "USDC", "USDT", "USDB", "USDY", "USD0", "USDX", "USDU", "USDTB", "USDG",
        "USDQ", "USDA", "USDF", "USDR", "USDL", "USDM", "USDH", "USDN", "USDK", "USDJ",
        "USDV", "USDZ", "USDO", "USR", "USX", "AVUSD",
        # tokenized gold and silver
        "PAXG", "XAUT", "XAUM", "KAU", "KAG", "DGX",
        # tokenized treasuries and money-market funds
        "BUIDL", "USTB", "OUSG", "USYC", "BENJI", "TBILL", "EUTBL", "STBT",
        # non-USD fiat stablecoins
        "EURC", "EURS", "EURT", "EURI", "EUROC", "EURQ", "EURR", "AEUR", "EURSAFO", "AGEUR",
        "XSGD", "BIDR", "IDRT", "BRZ", "BRLA", "TRYB", "MXNT", "CADC", "GYEN", "JPYC",
        "ZCHF", "VCHF", "XCHF", "GBPT", "NZDS", "A7A5", "RUBX",
    }
)

# Bases that look pegged by pattern but are real, volatile assets.
_PATTERN_EXCEPTIONS: frozenset[str] = frozenset()

_QUOTES = ("USDT", "USDC", "FDUSD", "BUSD", "TUSD", "USD", "EUR", "PERP")
_CRYPTO_QUOTES = ("USDT", "USDC", "FDUSD", "BUSD", "TUSD", "PERP")


def _env_extra() -> frozenset[str]:
    raw = os.getenv("PEGGED_ASSET_EXTRA_BASES") or ""
    return frozenset(x.strip().upper() for x in raw.split(",") if x.strip())


def crypto_base(symbol: object) -> str:
    """Return the base ticker of a crypto pair (``PYUSDUSDT`` -> ``PYUSD``)."""
    text = str(symbol or "").upper().strip().replace("-", "").replace("/", "").replace("_", "")
    for quote in _QUOTES:
        if text.endswith(quote) and len(text) > len(quote):
            return text[: -len(quote)]
    return text


def is_pegged_crypto(symbol: object) -> bool:
    """True for stablecoins, tokenized precious metals and tokenized treasuries.

    Recognised by an explicit list and by naming pattern: a base that starts or
    ends with ``USD`` (``USDTB``, ``PYUSD``, ``RLUSD``, ``CRVUSD``), or starts
    with ``EUR`` (``EURC``, ``EURSAFO``). ``PEGGED_ASSET_EXTRA_BASES`` adds bases
    without a release.
    """
    text = str(symbol or "").upper().strip().replace("-", "").replace("/", "").replace("_", "")
    base = crypto_base(text)
    if not base or base in _PATTERN_EXCEPTIONS:
        return False
    if base in _KNOWN_PEGGED_BASES or base in _env_extra():
        return True
    # Naming patterns apply only to crypto-quoted pairs, so forex such as
    # USDJPY or USDCHF is never mistaken for a stablecoin.
    if not text.endswith(_CRYPTO_QUOTES):
        return False
    if len(base) >= 4 and (base.startswith("USD") or base.endswith("USD")):
        return True
    if 4 <= len(base) <= 8 and base.startswith("EUR"):
        return True
    return False


def filter_pegged(symbols, *, enabled: bool | None = None) -> list[str]:
    """Drop pegged crypto symbols while keeping order; other classes pass through.

    Only symbols with a crypto quote (USDT/USDC/...) are examined, so forex
    pairs such as ``EURUSD`` and commodities such as ``XAUUSD`` are untouched.
    """
    if enabled is None:
        enabled = (os.getenv("PEGGED_ASSET_FILTER_ENABLED") or "1").strip().lower() not in {"0", "false", "no", "off"}
    out: list[str] = []
    for raw in symbols or []:
        symbol = str(raw or "").upper().strip()
        if not symbol:
            continue
        crypto_quoted = symbol.endswith(_CRYPTO_QUOTES)
        if enabled and crypto_quoted and is_pegged_crypto(symbol):
            continue
        out.append(symbol)
    return out


__all__ = ["crypto_base", "filter_pegged", "is_pegged_crypto"]
