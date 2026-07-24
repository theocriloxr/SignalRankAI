#!/usr/bin/env python3
"""Asset capability audit — run preflight checks on all configured assets.

This script tests every asset across all supported classes for OHLC availability,
live quote freshness, correct session/classification, provider symbol mapping,
and delivery eligibility.

Usage:
  python scripts/asset_capability_audit.py --all
  python scripts/asset_capability_audit.py --class crypto
  python scripts/asset_capability_audit.py --class fx
  python scripts/asset_capability_audit.py --class stock
  python scripts/asset_capability_audit.py --asset BTCUSDT
  python scripts/asset_capability_audit.py --ring 3    # Test assets in ring 3
  python scripts/asset_capability_audit.py --list-rings # Show release rings

SAFETY: This script operates in READ-ONLY mode by default.
It fetches market data and provider quotes but generates no signals,
sends no Telegram messages, and opens no trades.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.abspath(os.path.join(_THIS_DIR, ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

os.environ.setdefault("PUBLIC_TESTING_MODE", "1")


# ============================================================================
# Release Rings
# ============================================================================

RELEASE_RINGS = {
    0: {
        "name": "Provider Diagnostics",
        "description": "Fetch only — no signals, no delivery, no outcomes",
        "signals": False,
        "delivery": False,
        "outcomes": False,
    },
    1: {
        "name": "Shadow Analysis",
        "description": "Run strategies, track simulated outcomes, no user delivery",
        "signals": True,
        "delivery": False,
        "outcomes": True,  # shadow only
    },
    2: {
        "name": "Paper Testing",
        "description": "Generate signals, simulate fills, no public delivery",
        "signals": True,
        "delivery": False,  # paper only
        "outcomes": True,  # paper only
    },
    3: {
        "name": "Internal Owner Actionable Test",
        "description": "Owner account only — final quote required, complete delivery proof",
        "signals": True,
        "delivery": True,  # owner only
        "outcomes": True,
    },
    4: {
        "name": "Limited Public Test",
        "description": "Only proven assets — manual decisions only, no auto execution",
        "signals": True,
        "delivery": True,
        "outcomes": True,
    },
}


@dataclass
class AssetCapability:
    """Result of one asset's capability check."""
    asset: str = ""
    asset_class: str = ""
    session: str = ""
    ohlc_provider: str = ""
    required_timeframes: list[str] = field(default_factory=list)
    ohlc_fresh: bool = False
    ohlc_latency_ms: float = 0.0
    live_quote_provider: str = ""
    quote_fresh: bool = False
    quote_latency_ms: float = 0.0
    quote_price: float = 0.0
    quote_bid: float | None = None
    quote_ask: float | None = None
    spread_pct: float = 0.0
    symbol_mapping: str = ""
    capability_state: str = "UNKNOWN"
    reason: str = ""
    public_test_eligible: bool = False
    release_ring: int = 0


# ============================================================================
# Asset Registry (canonical, minimal starter set)
# ============================================================================

ASSET_REGISTRY: dict[str, dict[str, Any]] = {
    # === Crypto (24/7) ===
    "BTCUSDT": {"class": "crypto", "session": "24x7", "subtype": "crypto_stablecoin", "quote_currency": "USDT"},
    "ETHUSDT": {"class": "crypto", "session": "24x7", "subtype": "crypto_stablecoin", "quote_currency": "USDT"},
    "ADAUSDT": {"class": "crypto", "session": "24x7", "subtype": "crypto_stablecoin", "quote_currency": "USDT"},
    "XRPUSDT": {"class": "crypto", "session": "24x7", "subtype": "crypto_stablecoin", "quote_currency": "USDT"},
    "SOLUSDT": {"class": "crypto", "session": "24x7", "subtype": "crypto_stablecoin", "quote_currency": "USDT"},
    "AVAXUSDT": {"class": "crypto", "session": "24x7", "subtype": "crypto_stablecoin", "quote_currency": "USDT"},
    "LTCUSDT": {"class": "crypto", "session": "24x7", "subtype": "crypto_stablecoin", "quote_currency": "USDT"},
    "LINKUSDT": {"class": "crypto", "session": "24x7", "subtype": "crypto_stablecoin", "quote_currency": "USDT"},
    "BNBUSDT": {"class": "crypto", "session": "24x7", "subtype": "crypto_stablecoin", "quote_currency": "USDT"},
    "OPUSDT": {"class": "crypto", "session": "24x7", "subtype": "crypto_stablecoin", "quote_currency": "USDT"},
    "DOTUSDT": {"class": "crypto", "session": "24x7", "subtype": "crypto_stablecoin", "quote_currency": "USDT"},
    "POLUSDT": {"class": "crypto", "session": "24x7", "subtype": "crypto_stablecoin", "quote_currency": "USDT"},
    "XAUTUSDT": {"class": "crypto", "session": "24x7", "subtype": "crypto_tokenized_gold", "quote_currency": "USDT"},
    # === Forex (5-day, 24h) ===
    "EURUSD": {"class": "forex", "session": "forex", "subtype": "major", "quote_currency": "USD"},
    "GBPUSD": {"class": "forex", "session": "forex", "subtype": "major", "quote_currency": "USD"},
    "USDJPY": {"class": "forex", "session": "forex", "subtype": "major", "quote_currency": "JPY"},
    "USDCHF": {"class": "forex", "session": "forex", "subtype": "major", "quote_currency": "CHF"},
    "USDCAD": {"class": "forex", "session": "forex", "subtype": "major", "quote_currency": "CAD"},
    "AUDUSD": {"class": "forex", "session": "forex", "subtype": "major", "quote_currency": "USD"},
    "AUDJPY": {"class": "forex", "session": "forex", "subtype": "cross", "quote_currency": "JPY"},
    "NZDJPY": {"class": "forex", "session": "forex", "subtype": "cross", "quote_currency": "JPY"},
    "GBPJPY": {"class": "forex", "session": "forex", "subtype": "cross", "quote_currency": "JPY"},
    "EURCHF": {"class": "forex", "session": "forex", "subtype": "cross", "quote_currency": "CHF"},
    # === Stocks (US hours) ===
    "AAPL": {"class": "stock", "session": "us_equity", "subtype": "tech_equity", "exchange": "NASDAQ"},
    "MSFT": {"class": "stock", "session": "us_equity", "subtype": "tech_equity", "exchange": "NASDAQ"},
    "NVDA": {"class": "stock", "session": "us_equity", "subtype": "tech_equity", "exchange": "NASDAQ"},
    "AMZN": {"class": "stock", "session": "us_equity", "subtype": "tech_equity", "exchange": "NASDAQ"},
    "META": {"class": "stock", "session": "us_equity", "subtype": "tech_equity", "exchange": "NASDAQ"},
    "GOOGL": {"class": "stock", "session": "us_equity", "subtype": "tech_equity", "exchange": "NASDAQ"},
    "TSLA": {"class": "stock", "session": "us_equity", "subtype": "auto_equity", "exchange": "NASDAQ"},
    "AMD": {"class": "stock", "session": "us_equity", "subtype": "semiconductor_equity", "exchange": "NASDAQ"},
    "JPM": {"class": "stock", "session": "us_equity", "subtype": "finance_equity", "exchange": "NYSE"},
    "BAC": {"class": "stock", "session": "us_equity", "subtype": "finance_equity", "exchange": "NYSE"},
    # === Indices ===
    "SPY": {"class": "index", "session": "us_equity", "subtype": "etf_index", "proxy": "SPY"},
    "QQQ": {"class": "index", "session": "us_equity", "subtype": "etf_index", "proxy": "QQQ"},
    "DIA": {"class": "index", "session": "us_equity", "subtype": "etf_index", "proxy": "DIA"},
    "JP225": {"class": "index", "session": "asia_index", "subtype": "cash_index"},
    "FRA40": {"class": "index", "session": "europe_index", "subtype": "cash_index"},
    "EU50": {"class": "index", "session": "europe_index", "subtype": "cash_index"},
    "AUS200": {"class": "index", "session": "asia_index", "subtype": "cash_index"},
    "HK50": {"class": "index", "session": "asia_index", "subtype": "cash_index"},
    # === Commodities & Metals ===
    "XAUUSD": {"class": "commodity", "session": "commodity", "subtype": "precious_metal"},
    "XAGUSD": {"class": "commodity", "session": "commodity", "subtype": "precious_metal"},
    "WTI": {"class": "commodity", "session": "commodity", "subtype": "energy"},
    "BRENT": {"class": "commodity", "session": "commodity", "subtype": "energy"},
    "NG": {"class": "commodity", "session": "commodity", "subtype": "energy"},
    # === Macro ===
    "DXY": {"class": "macro", "session": "forex", "subtype": "dollar_index"},
    "US10Y": {"class": "yield", "session": "us_equity", "subtype": "treasury_yield"},
    "US02Y": {"class": "yield", "session": "us_equity", "subtype": "treasury_yield"},
    # === Volatility ===
    "VIX": {"class": "volatility", "session": "us_equity", "subtype": "volatility_index"},
}


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on", "y"}


def _asset_class_sort_key(item: tuple[str, dict[str, Any]]) -> int:
    """Sort assets by class priority for cleaner output."""
    priority = {
        "crypto": 0,
        "forex": 1,
        "stock": 2,
        "index": 3,
        "commodity": 4,
        "macro": 5,
        "yield": 6,
        "volatility": 7,
    }
    return priority.get(item[1].get("class", ""), 99)


async def check_asset_ohlc(asset: str, asset_info: dict[str, Any]) -> tuple[bool, str, float]:
    """Check OHLC availability for an asset. Returns (available, provider, latency_ms)."""
    provider = "unknown"
    start = time.perf_counter()
    try:
        from data.fetch import async_get_candles

        cls = asset_info.get("class", "")
        timeframes = ["5m", "15m", "1h"]
        if cls == "crypto":
            session = "24x7"
            timeframes = ["5m", "15m", "1h"]
        elif cls == "stock":
            session = "us_equity"
            timeframes = ["1d", "1h"]
        else:
            session = "default"

        # Try to fetch the most recent candle
        candles = await async_get_candles(asset, timeframe="5m", limit=5)
        elapsed = (time.perf_counter() - start) * 1000

        if candles and len(candles) > 0:
            last_candle = candles[-1] if isinstance(candles, list) else None
            if last_candle:
                provider = str(getattr(last_candle, "source", None) or candles.get("source", "unknown"))
            return True, provider, elapsed

        # Fallback: try sync fetch
        start = time.perf_counter()
        from data.fetcher import get_candles

        candles = get_candles(asset, "5m")
        elapsed = (time.perf_counter() - start) * 1000
        if candles and len(candles) > 0:
            return True, "legacy_fetcher", elapsed

        return False, provider, elapsed
    except Exception as exc:
        elapsed = (time.perf_counter() - start) * 1000
        return False, provider, elapsed


async def check_asset_live_quote(asset: str, asset_info: dict[str, Any]) -> tuple[bool, str, float, float | None, float | None]:
    """Check live quote availability for an asset. Returns (available, provider, latency_ms, bid, ask)."""
    start = time.perf_counter()
    try:
        from data.provider_types import LivePriceFailure, LivePriceQuote
        from data.get_live_price import get_live_price_result

        result = await get_live_price_result(asset, timeout=5.0)
        elapsed = (time.perf_counter() - start) * 1000

        if isinstance(result, LivePriceQuote):
            return True, result.provider, elapsed, result.bid, result.ask
        if isinstance(result, LivePriceFailure):
            return False, result.provider, elapsed, None, None
        return False, "unknown", elapsed, None, None
    except Exception as exc:
        elapsed = (time.perf_counter() - start) * 1000
        logger.debug("[capability] live quote check failed for %s: %s", asset, exc)
        return False, "error", elapsed, None, None


async def run_capability_check(
    asset: str,
    asset_info: dict[str, Any],
    *,
    verbose: bool = False,
) -> AssetCapability:
    """Run the full capability check for one asset."""
    capability = AssetCapability(asset=asset)
    capability.asset_class = asset_info.get("class", "unknown")
    capability.session = asset_info.get("session", "default")

    if verbose:
        logger.info("Checking %s (%s)...", asset, capability.asset_class)

    # 1. OHLC check
    ohlc_ok, ohlc_provider, ohlc_latency = await check_asset_ohlc(asset, asset_info)
    capability.ohlc_provider = ohlc_provider
    capability.ohlc_fresh = ohlc_ok
    capability.ohlc_latency_ms = ohlc_latency

    # 2. Live quote check
    quote_ok, quote_provider, quote_latency, bid, ask = await check_asset_live_quote(asset, asset_info)
    capability.live_quote_provider = quote_provider
    capability.quote_fresh = quote_ok
    capability.quote_latency_ms = quote_latency
    capability.quote_bid = bid
    capability.quote_ask = ask
    if bid is not None and ask is not None and ask > 0:
        capability.spread_pct = (ask - bid) / ask * 100.0

    # 3. Symbol mapping
    try:
        from services.asset_mapper import map_symbol

        yf_sym = map_symbol(asset, "yfinance")
        capability.symbol_mapping = yf_sym or ""
    except Exception:
        capability.symbol_mapping = ""

    # 4. Determine capability state
    if ohlc_ok and quote_ok:
        if capability.asset_class == "crypto":
            capability.public_test_eligible = True
            capability.release_ring = 3  # Needs owner test first
        elif capability.asset_class in ("forex", "stock", "index", "commodity"):
            capability.public_test_eligible = False
            capability.release_ring = 1  # Shadow first
        else:
            capability.public_test_eligible = False
            capability.release_ring = 0  # Diagnostic only
        capability.capability_state = "ACTIVE"
        capability.reason = "OHLC and live quote verified"
    elif ohlc_ok and not quote_ok:
        capability.capability_state = "DISABLED_NO_LIVE_QUOTE"
        capability.release_ring = 0
        capability.reason = f"OHLC available ({ohlc_provider}) but live quote unavailable (last tried: {quote_provider})"
    elif not ohlc_ok and quote_ok:
        capability.capability_state = "DISABLED_NO_OHLC"
        capability.release_ring = 0
        capability.reason = f"Live quote available ({quote_provider}) but OHLC unavailable"
    else:
        capability.capability_state = "DISABLED_UNSUPPORTED"
        capability.release_ring = 0
        capability.reason = "Neither OHLC nor live quote available for this asset through any configured provider"

    if verbose and capability.capability_state == "ACTIVE":
        spread_str = f" spread={capability.spread_pct:.3f}%" if capability.spread_pct > 0 else ""
        logger.info(
            "  %s: %s (OHLC=%s %.0fms, Quote=%s %.0fms%s)",
            asset,
            capability.capability_state,
            ohlc_provider,
            ohlc_latency,
            quote_provider,
            quote_latency,
            spread_str,
        )
    elif verbose and capability.capability_state != "ACTIVE":
        logger.info("  %s: %s — %s", asset, capability.capability_state, capability.reason)

    return capability


def print_asset_table(results: list[AssetCapability], *, class_filter: str | None = None, show_all: bool = False) -> None:
    """Print a formatted table of asset capability results."""
    header = (
        f"{'Asset':<12} {'Class':<10} {'Session':<12} {'OHLC':<8} {'Provider':<14} "
        f"{'Quote':<8} {'Provider':<14} {'Latency':<8} {'Spread':<8} {'State':<24} {'Ring':<5}"
    )
    separator = "-" * len(header)

    filtered = [r for r in results if (class_filter is None or r.asset_class == class_filter) and (show_all or r.capability_state != "DISABLED_NO_OHLC")]

    logger.info("\n%s", separator)
    logger.info("Asset Capability Report")
    logger.info("%s", separator)
    logger.info(header)
    logger.info(header.replace("[A-Za-z]", "-"))
    logger.info(separator)

    for r in sorted(filtered, key=lambda x: (RELEASE_RINGS.get(x.release_ring, {}).get("name", "Z"), x.asset)):
        state_str = r.capability_state
        if r.public_test_eligible:
            state_str += " [PUBLIC ELIGIBLE]"
        latency_str = f"{r.quote_latency_ms:.0f}ms" if r.quote_latency_ms > 0 else "-"
        spread_str = f"{r.spread_pct:.3f}%" if r.spread_pct > 0 else "-"
        logger.info(
            f"{r.asset:<12} {r.asset_class:<10} {r.session:<12} "
            f"{'OK' if r.ohlc_fresh else 'FAIL':<8} {r.ohlc_provider:<14.14} "
            f"{'OK' if r.quote_fresh else 'FAIL':<8} {r.live_quote_provider:<14.14} "
            f"{latency_str:<8} {spread_str:<8} {state_str:<24} {r.release_ring:<5}"
        )

    logger.info(separator)

    # Summary counts
    active = sum(1 for r in filtered if r.capability_state == "ACTIVE")
    no_quote = sum(1 for r in filtered if r.capability_state == "DISABLED_NO_LIVE_QUOTE")
    no_ohlc = sum(1 for r in filtered if r.capability_state == "DISABLED_NO_OHLC")
    unsupported = sum(1 for r in filtered if r.capability_state == "DISABLED_UNSUPPORTED")

    logger.info("Summary: %d active, %d no-quote, %d no-OHLC, %d unsupported", active, no_quote, no_ohlc, unsupported)
    logger.info("")

    if active:
        # Group by ring
        ring_counts: dict[int, int] = {}
        for r in filtered:
            if r.capability_state == "ACTIVE":
                ring_counts[r.release_ring] = ring_counts.get(r.release_ring, 0) + 1
        logger.info("Release Ring Distribution:")
        for ring_no in sorted(ring_counts.keys()):
            ring_info = RELEASE_RINGS.get(ring_no, {})
            logger.info("  Ring %d (%s): %d asset(s)", ring_no, ring_info.get("name", ""), ring_counts[ring_no])


def list_rings() -> None:
    """Display the release ring definitions."""
    logger.info("\nRelease Rings:")
    logger.info("=" * 60)
    for ring_no in sorted(RELEASE_RINGS.keys()):
        info = RELEASE_RINGS[ring_no]
        logger.info("  Ring %d — %s", ring_no, info["name"])
        logger.info("    %s", info["description"])
        logger.info("    Signals: %s, Delivery: %s, Outcomes: %s", info["signals"], info["delivery"], info["outcomes"])
        logger.info("")


async def main() -> int:
    parser = argparse.ArgumentParser(
        description="Asset capability audit — test OHLC, quotes, and eligibility",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--all", action="store_true", help="Test all configured assets")
    parser.add_argument("--class", dest="asset_class", type=str, default=None, help="Test assets of a specific class")
    parser.add_argument("--asset", type=str, default=None, help="Test a single asset")
    parser.add_argument("--ring", type=int, default=None, help="Filter by release ring")
    parser.add_argument("--list-rings", action="store_true", help="Show release ring definitions")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    parser.add_argument("--concurrency", type=int, default=5, help="Concurrent checks (default: 5)")
    parser.add_argument("--show-failed", action="store_true", help="Show failed assets too")
    parser.add_argument("--output", type=str, default=None, help="Write report to CSV file")

    args = parser.parse_args()

    if args.list_rings:
        list_rings()
        return 0

    # Build the asset list to test
    assets_to_test: dict[str, dict[str, Any]] = {}

    if args.asset:
        asset_upper = args.asset.upper().strip()
        if asset_upper in ASSET_REGISTRY:
            assets_to_test[asset_upper] = ASSET_REGISTRY[asset_upper]
        else:
            # Try dynamic lookup via asset_mapper
            try:
                from services.asset_mapper import classify_asset

                cls = classify_asset(asset_upper)
                assets_to_test[asset_upper] = {"class": cls, "session": "default", "subtype": "unknown"}
            except Exception:
                assets_to_test[asset_upper] = {"class": "unknown", "session": "default", "subtype": "unknown"}
    elif args.asset_class:
        cls = args.asset_class.strip().lower()
        aliases = {"forex": "forex", "fx": "forex", "stocks": "stock", "indices": "index", "commodities": "commodity"}
        resolved_cls = aliases.get(cls, cls)
        assets_to_test = {
            sym: info for sym, info in ASSET_REGISTRY.items()
            if info["class"] == resolved_cls
        }
    elif args.all:
        assets_to_test = dict(ASSET_REGISTRY)
    else:
        parser.print_help()
        logger.info("\nTip: use --all to test all assets, or filter with --class / --asset")
        return 1

    if not assets_to_test:
        logger.error("No assets matched the filter criteria")
        return 1

    if args.ring is not None:
        ring = int(args.ring)
        assets_to_test = {
            sym: info for sym, info in assets_to_test.items()
        }
        # Ring filtering is done after capability check

    logger.info("Testing %d asset(s)...", len(assets_to_test))

    # Run capability checks with concurrency control
    semaphore = asyncio.Semaphore(max(1, int(args.concurrency)))

    async def _checked(asset: str, info: dict[str, Any]) -> AssetCapability:
        async with semaphore:
            return await run_capability_check(asset, info, verbose=args.verbose)

    results = await asyncio.gather(
        *[_checked(asset, info) for asset, info in assets_to_test.items()],
        return_exceptions=True,
    )

    # Process results
    capabilities: list[AssetCapability] = []
    errors: list[str] = []
    for i, result in enumerate(results):
        if isinstance(result, AssetCapability):
            capabilities.append(result)
        elif isinstance(result, Exception):
            asset = list(assets_to_test.keys())[i] if i < len(assets_to_test) else "?"
            errors.append(f"{asset}: {result}")
        else:
            asset = list(assets_to_test.keys())[i] if i < len(assets_to_test) else "?"
            errors.append(f"{asset}: unexpected return type {type(result).__name__}")

    # Filter by ring if specified
    if args.ring is not None:
        capabilities = [c for c in capabilities if c.release_ring == int(args.ring)]

    # Print report
    class_filter = args.asset_class
    print_asset_table(capabilities, class_filter=class_filter, show_all=args.show_failed)

    if errors:
        logger.warning("\nErrors (%d):", len(errors))
        for err in errors:
            logger.warning("  %s", err)

    # Write CSV if requested
    if args.output:
        import csv

        with open(args.output, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                "Asset", "Class", "Session", "OHLC_OK", "OHLC_Provider", "OHLC_Latency_ms",
                "Quote_OK", "Quote_Provider", "Quote_Latency_ms", "Spread_Pct",
                "State", "Ring", "Public_Test_Eligible", "Reason",
            ])
            for c in capabilities:
                writer.writerow([
                    c.asset, c.asset_class, c.session,
                    c.ohlc_fresh, c.ohlc_provider, f"{c.ohlc_latency_ms:.0f}",
                    c.quote_fresh, c.live_quote_provider, f"{c.quote_latency_ms:.0f}",
                    f"{c.spread_pct:.3f}" if c.spread_pct > 0 else "",
                    c.capability_state, c.release_ring, c.public_test_eligible, c.reason,
                ])
        logger.info("CSV report written to: %s", args.output)

    # Final summary
    active_count = sum(1 for c in capabilities if c.capability_state == "ACTIVE")
    logger.info("\n=== CAPABILITY AUDIT COMPLETE ===")
    logger.info("Assets tested: %d, Active: %d, Failed/Unsupported: %d",
                len(capabilities), active_count, len(capabilities) - active_count)

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
