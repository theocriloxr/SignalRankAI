"""Off-market throttling helpers.

Crypto runs continuously; FX, commodities, indices, and stocks do not. During
closed sessions the engine should avoid hammering providers and logging stale
candle warnings for closed markets.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class OffMarketDecision:
    throttle: bool
    sleep_seconds: int
    reason: str


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return bool(default)
    return str(raw).strip().lower() in {"1", "true", "yes", "on", "y"}


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)) or default)
    except Exception:
        return int(default)


def off_market_decision(open_assets: Iterable[str], closed_notes: Iterable[tuple[str, str]]) -> OffMarketDecision:
    """Return whether to downshift loop frequency for non-crypto closures.

    If crypto assets are still open, the engine should continue normal crypto
    scanning. If only closed non-crypto assets remain, it can safely sleep much
    longer and preserve Railway/provider/DB budget.
    """
    if not _env_bool("ENGINE_OFF_MARKET_THROTTLE_ENABLED", True):
        return OffMarketDecision(False, 0, "disabled")
    open_list = [str(a or "").upper() for a in open_assets]
    closed_list = list(closed_notes or [])
    has_open_crypto = any(a.endswith(("USDT", "USDC", "BUSD", "BTC", "ETH")) for a in open_list)
    has_open_noncrypto = bool(open_list) and not all(a.endswith(("USDT", "USDC", "BUSD", "BTC", "ETH")) for a in open_list)
    if has_open_crypto or has_open_noncrypto:
        return OffMarketDecision(False, 0, "open_assets_available")
    if closed_list:
        return OffMarketDecision(
            True,
            max(60, _env_int("ENGINE_OFF_MARKET_SLEEP_SECONDS", 900)),
            f"all_non_crypto_markets_closed closed={len(closed_list)}",
        )
    return OffMarketDecision(False, 0, "no_closed_assets")


__all__ = ["OffMarketDecision", "off_market_decision"]
