"""
Live Price Fetcher with Circuit Breaker - Task 5 Fix

This module:
- Implements strict asset routing: Crypto (USDT/*) → Binance/Bybit, Stocks → Yahoo
- Uses Circuit Breaker pattern for each provider
- Provides automatic failover on rate limits/geo-blocks
- Prevents "Ghost Price" from wrong provider
"""

import os
import logging
import asyncio
import time
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from collections import deque
from datetime import datetime, timezone

from data.provider_types import (
    BreakerState,
    LivePriceFailure,
    LivePriceQuote,
    ProviderHealthState,
    QuoteKind,
)

logger = logging.getLogger(__name__)


# ============================================================================
# Circuit Breaker Configuration
# ============================================================================

@dataclass
class PriceCircuitConfig:
    """Configuration for price circuit breaker."""
    failure_threshold: int = 3  # Open after 3 failures
    window_seconds: float = 60.0  # Track failures in 60s window
    open_seconds: float = 30.0  # Stay open for 30s


class PriceCircuitBreaker:
    """Circuit breaker for price providers."""
    
    def __init__(self, config: Optional[PriceCircuitConfig] = None):
        self.config = config or PriceCircuitConfig()
        self._failures: deque[float] = deque()
        self._open_until: float = 0.0
    
    def _now(self) -> float:
        return time.time()
    
    def _prune(self, now_ts: float) -> None:
        window_start = now_ts - self.config.window_seconds
        while self._failures and self._failures[0] < window_start:
            self._failures.popleft()
    
    def allow(self) -> bool:
        now_ts = self._now()
        if now_ts < self._open_until:
            return False
        self._prune(now_ts)
        return True
    
    def record_success(self) -> None:
        self._failures.clear()
        self._open_until = 0.0
    
    def record_failure(self) -> bool:
        now_ts = self._now()
        self._failures.append(now_ts)
        self._prune(now_ts)
        
        if len(self._failures) >= self.config.failure_threshold:
            self._open_until = now_ts + self.config.open_seconds
            return True
        return False


# Provider circuit breakers
_price_breakers: Dict[str, PriceCircuitBreaker] = {}


def _get_breaker(provider: str) -> PriceCircuitBreaker:
    """Get or create circuit breaker for provider."""
    if provider not in _price_breakers:
        _price_breakers[provider] = PriceCircuitBreaker()
    return _price_breakers[provider]


# ============================================================================
# Asset Routing Logic
# ============================================================================

def _is_crypto(asset: str) -> bool:
    """Check if asset is crypto (USDT, USDC, BUSD, etc.)."""
    a = (asset or "").upper().strip()
    return (
        a.endswith("USDT") or 
        a.endswith("USDC") or 
        a.endswith("BUSD") or
        a.endswith("BTC") or
        a.endswith("ETH")
    )


def _get_providers_for_asset(asset: str) -> List[str]:
    """Get provider priority list for live-price checks.

    The final-send gate must not reuse candle-cache prices. It needs a fresh
    quote from a provider whose symbol mapping matches the asset class.

    Railway-compatible priority for crypto:
    1. Coinbase - REST API works from Railway (EU/US regions)
    2. OKX - REST API works from Railway (all regions)
    3. Binance - may fail with HTTP 451 in restricted regions
    4. Bybit - may fail with HTTP 403 in some regions
    
    Stocks, FX, and commodities prefer Yahoo with keyed Twelve Data fallback.
    """
    try:
        from services.asset_mapper import classify_asset
        cls = str(classify_asset(asset)).lower()
    except Exception:
        cls = "crypto" if _is_crypto(asset) else "stock"
    if cls == "crypto":
        # Coinbase and OKX are the most Railway-compatible crypto providers.
        # Binance/Bybit/CryptoCompare are fallbacks that may be region-blocked.
        return ["coinbase", "okx", "binance", "bybit", "cryptocompare", "yahoo"]
    return ["yahoo", "twelvedata", "polygon"]


# ============================================================================
# Price Fetching Functions
# ============================================================================

async def _fetch_binance_price(symbol: str) -> Optional[float]:
    """Fetch price from Binance public API."""
    import requests
    
    breaker = _get_breaker("binance")
    if not breaker.allow():
        return None
    
    try:
        sym = symbol.upper().replace("/", "").replace("-", "")
        if not sym.endswith("USDT") and not sym.endswith("USDC"):
            sym += "USDT"
        
        url = f"https://api.binance.com/api/v3/ticker/price?symbol={sym}"
        resp = await asyncio.to_thread(requests.get, url, timeout=5)
        
        if resp.ok:
            data = resp.json()
            price = data.get("price")
            if price:
                breaker.record_success()
                return float(price)
        
        breaker.record_failure()
        return None
        
    except Exception as e:
        breaker.record_failure()
        logger.debug(f"[price] Binance error for {symbol}: {e}")
        return None


async def _fetch_bybit_price(symbol: str) -> Optional[float]:
    """Fetch price from Bybit public API."""
    import requests
    
    breaker = _get_breaker("bybit")
    if not breaker.allow():
        return None
    
    try:
        sym = symbol.upper().replace("/", "").replace("-", "")
        
        url = "https://api.bybit.com/v5/market/ticker"
        params = {
            "category": "spot",
            "symbol": sym,
        }
        
        resp = await asyncio.to_thread(requests.get, url, params=params, timeout=5)
        
        if resp.ok:
            data = resp.json()
            if str(data.get("retCode", "1")) == "0":
                result = data.get("result", {})
                price = result.get("lastPrice")
                if price:
                    breaker.record_success()
                    return float(price)
        
        breaker.record_failure()
        return None
        
    except Exception as e:
        breaker.record_failure()
        logger.debug(f"[price] Bybit error for {symbol}: {e}")
        return None


async def _fetch_cryptocompare_price(symbol: str) -> Optional[float]:
    """Fetch price from CryptoCompare."""
    import requests
    
    breaker = _get_breaker("cryptocompare")
    if not breaker.allow():
        return None
    
    try:
        # Parse symbol (BTCUSDT -> BTC,USDT)
        sym = symbol.upper().replace("/", "").replace("-", "")
        base = sym
        quote = "USDT"
        
        for q in ("USDT", "USDC", "BUSD", "USD"):
            if sym.endswith(q):
                base = sym[:-len(q)]
                quote = q
                break
        
        api_key = os.getenv("CRYPTOCOMPARE_API_KEY", "").strip()
        
        url = "https://min-api.cryptocompare.com/data/price"
        params = {
            "fsym": base,
            "tsyms": quote,
        }
        if api_key:
            params["api_key"] = api_key
        
        resp = await asyncio.to_thread(requests.get, url, params=params, timeout=5)
        
        if resp.ok:
            data = resp.json()
            price = data.get(quote)
            if price:
                breaker.record_success()
                return float(price)
        
        breaker.record_failure()
        return None
        
    except Exception as e:
        breaker.record_failure()
        logger.debug(f"[price] CryptoCompare error for {symbol}: {e}")
        return None


async def _fetch_yahoo_price(symbol: str) -> Optional[float]:
    """Fetch price from Yahoo Finance using provider-correct symbol mapping.

    Previous code treated every non-USD ticker as FX and converted symbols like
    META into META=X. That can return no data/ghost data and is one root cause
    of stale stock signals. Use services.asset_mapper for stocks, FX,
    commodities, and crypto fallbacks, and query the correct /chart endpoint.
    """
    import requests

    breaker = _get_breaker("yahoo")
    if not breaker.allow():
        return None

    try:
        try:
            from services.asset_mapper import map_symbol
            sym = map_symbol(symbol, "yfinance") or symbol.upper().strip()
        except Exception:
            sym = symbol.upper().strip()
        if not sym:
            breaker.record_failure()
            return None

        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}"
        resp = await asyncio.to_thread(requests.get, url, timeout=5)

        if resp.ok:
            data = resp.json()
            chart = data.get("chart", {})
            result = chart.get("result", [])
            if result:
                meta = result[0].get("meta", {}) or {}
                price = (
                    meta.get("regularMarketPrice")
                    or meta.get("previousClose")
                    or meta.get("chartPreviousClose")
                )
                if price:
                    breaker.record_success()
                    return float(price)

        breaker.record_failure()
        return None

    except Exception as e:
        breaker.record_failure()
        logger.debug(f"[price] Yahoo error for {symbol}: {e}")
        return None


async def _fetch_polygon_price(symbol: str) -> Optional[float]:
    """Fetch price from Polygon.io."""
    import requests
    
    breaker = _get_breaker("polygon")
    if not breaker.allow():
        return None
    
    try:
        api_key = os.getenv("POLYGON_API_KEY", "").strip()
        if not api_key:
            return None
        
        # Clean symbol
        sym = symbol.upper().replace("/", "").replace("-", "")
        
        url = f"https://api.polygon.io/v2/aggs/ticker/{sym}/prev"
        params = {"apiKey": api_key}
        
        resp = await asyncio.to_thread(requests.get, url, params=params, timeout=5)
        
        if resp.ok:
            data = resp.json()
            results = data.get("results", [])
            if results:
                price = results[0].get("c")  # Close price
                if price:
                    breaker.record_success()
                    return float(price)
        
        breaker.record_failure()
        return None
        
    except Exception as e:
        breaker.record_failure()
        logger.debug(f"[price] Polygon error for {symbol}: {e}")
        return None


# ============================================================================
# Typed Provider Adapters
# ============================================================================

def _epoch_seconds(value: Any) -> float | None:
    try:
        timestamp = float(value)
        if timestamp <= 0:
            return None
        if timestamp > 10_000_000_000_000_000:
            timestamp /= 1_000_000_000.0
        elif timestamp > 10_000_000_000:
            timestamp /= 1000.0
        return timestamp
    except (TypeError, ValueError):
        return None


def _provider_identity(symbol: str, provider: str) -> tuple[str, str, str]:
    from services.asset_mapper import canonicalize_symbol, classify_asset, map_symbol

    canonical = canonicalize_symbol(symbol)
    provider_symbol = map_symbol(canonical, "yfinance" if provider == "yahoo" else provider)
    return canonical, str(provider_symbol or ""), classify_asset(canonical)


def _typed_failure(
    symbol: str,
    provider: str,
    reason: str,
    *,
    retryable: bool = True,
    breaker_state: str = BreakerState.CLOSED.value,
) -> LivePriceFailure:
    canonical, provider_symbol, asset_class = _provider_identity(symbol, provider)
    return LivePriceFailure(
        symbol=canonical,
        provider=provider,
        provider_symbol=provider_symbol,
        asset_class=asset_class,
        reason=reason,
        retryable=retryable,
        breaker_state=breaker_state,
    )


def _typed_quote(
    *,
    symbol: str,
    provider: str,
    price: Any,
    source_timestamp: Any,
    started: float,
    received_at: float,
    bid: Any = None,
    ask: Any = None,
    quote_kind: str = QuoteKind.TICKER.value,
    market_status: str = "unknown",
    confidence_reasons: tuple[str, ...] = (),
) -> LivePriceQuote | LivePriceFailure:
    canonical, provider_symbol, asset_class = _provider_identity(symbol, provider)
    try:
        numeric_price = float(price)
        numeric_bid = float(bid) if bid not in (None, "") else None
        numeric_ask = float(ask) if ask not in (None, "") else None
    except (TypeError, ValueError):
        return _typed_failure(symbol, provider, "invalid_price_payload")
    if numeric_price <= 0:
        return _typed_failure(symbol, provider, "non_positive_price")
    completed_at = time.time()
    source_time = _epoch_seconds(source_timestamp)
    reasons = list(confidence_reasons)
    if source_time is not None:
        reasons.append("provider_source_timestamp")
    if numeric_bid is not None and numeric_ask is not None:
        reasons.append("bid_ask_available")
    return LivePriceQuote(
        symbol=canonical,
        provider_symbol=provider_symbol,
        asset_class=asset_class,
        price=numeric_price,
        bid=numeric_bid,
        ask=numeric_ask,
        provider=provider,
        fetched_at=completed_at,
        received_at=received_at,
        completed_at=completed_at,
        source_timestamp=source_time,
        latency_ms=int((time.perf_counter() - started) * 1000),
        quote_kind=quote_kind,
        market_status=market_status,
        provider_health=ProviderHealthState.HEALTHY.value,
        breaker_state=BreakerState.CLOSED.value,
        confidence=1.0 if source_time is not None else 0.5,
        confidence_reasons=tuple(reasons),
        untrusted_reason=None if source_time is not None else "missing_source_timestamp",
    )


async def _fetch_binance_quote(symbol: str) -> LivePriceQuote | LivePriceFailure:
    import requests

    provider = "binance"
    breaker = _get_breaker(provider)
    if not breaker.allow():
        return _typed_failure(symbol, provider, "circuit_open", breaker_state=BreakerState.OPEN.value)
    started = time.perf_counter()
    try:
        canonical, provider_symbol, _ = _provider_identity(symbol, provider)
        sym = provider_symbol or canonical.replace("/", "").replace("-", "")
        if not sym.endswith(("USDT", "USDC")):
            sym += "USDT"
        response = await asyncio.to_thread(
            requests.get,
            "https://api.binance.com/api/v3/ticker/24hr",
            params={"symbol": sym},
            timeout=5,
        )
        received_at = time.time()
        if not response.ok:
            breaker.record_failure()
            return _typed_failure(symbol, provider, f"http_status:{response.status_code}")
        payload = response.json() or {}
        quote = _typed_quote(
            symbol=symbol,
            provider=provider,
            price=payload.get("lastPrice"),
            bid=payload.get("bidPrice"),
            ask=payload.get("askPrice"),
            source_timestamp=payload.get("closeTime"),
            started=started,
            received_at=received_at,
            quote_kind=QuoteKind.BID_ASK.value,
            market_status="open",
        )
        if isinstance(quote, LivePriceQuote):
            breaker.record_success()
        else:
            breaker.record_failure()
        return quote
    except Exception as exc:
        breaker.record_failure()
        logger.debug("[price] Binance typed quote error for %s: %s", symbol, exc)
        return _typed_failure(symbol, provider, f"provider_error:{type(exc).__name__}")


async def _fetch_bybit_quote(symbol: str) -> LivePriceQuote | LivePriceFailure:
    import requests

    provider = "bybit"
    breaker = _get_breaker(provider)
    if not breaker.allow():
        return _typed_failure(symbol, provider, "circuit_open", breaker_state=BreakerState.OPEN.value)
    started = time.perf_counter()
    try:
        canonical, provider_symbol, _ = _provider_identity(symbol, provider)
        sym = provider_symbol or canonical.replace("/", "").replace("-", "")
        response = await asyncio.to_thread(
            requests.get,
            "https://api.bybit.com/v5/market/tickers",
            params={"category": "spot", "symbol": sym},
            timeout=5,
        )
        received_at = time.time()
        payload = response.json() if response.ok else {}
        rows = (payload.get("result") or {}).get("list") or []
        if not response.ok or str(payload.get("retCode", "1")) != "0" or not rows:
            breaker.record_failure()
            return _typed_failure(symbol, provider, f"invalid_response:{getattr(response, 'status_code', 'unknown')}")
        row = rows[0] or {}
        quote = _typed_quote(
            symbol=symbol,
            provider=provider,
            price=row.get("lastPrice"),
            bid=row.get("bid1Price"),
            ask=row.get("ask1Price"),
            source_timestamp=payload.get("time"),
            started=started,
            received_at=received_at,
            quote_kind=QuoteKind.BID_ASK.value,
            market_status="open",
        )
        if isinstance(quote, LivePriceQuote):
            breaker.record_success()
        else:
            breaker.record_failure()
        return quote
    except Exception as exc:
        breaker.record_failure()
        logger.debug("[price] Bybit typed quote error for %s: %s", symbol, exc)
        return _typed_failure(symbol, provider, f"provider_error:{type(exc).__name__}")


async def _fetch_cryptocompare_quote(symbol: str) -> LivePriceQuote | LivePriceFailure:
    import requests

    provider = "cryptocompare"
    breaker = _get_breaker(provider)
    if not breaker.allow():
        return _typed_failure(symbol, provider, "circuit_open", breaker_state=BreakerState.OPEN.value)
    started = time.perf_counter()
    try:
        canonical, _, _ = _provider_identity(symbol, provider)
        compact = canonical.replace("/", "").replace("-", "")
        base, quote_currency = compact, "USD"
        for suffix in ("USDT", "USDC", "BUSD", "USD"):
            if compact.endswith(suffix):
                base, quote_currency = compact[:-len(suffix)], "USD"
                break
        params = {"fsyms": base, "tsyms": quote_currency}
        api_key = os.getenv("CRYPTOCOMPARE_API_KEY", "").strip()
        if api_key:
            params["api_key"] = api_key
        response = await asyncio.to_thread(
            requests.get,
            "https://min-api.cryptocompare.com/data/pricemultifull",
            params=params,
            timeout=5,
        )
        received_at = time.time()
        payload = response.json() if response.ok else {}
        row = (((payload.get("RAW") or {}).get(base) or {}).get(quote_currency) or {})
        if not response.ok or not row:
            breaker.record_failure()
            return _typed_failure(symbol, provider, f"invalid_response:{getattr(response, 'status_code', 'unknown')}")
        quote = _typed_quote(
            symbol=symbol,
            provider=provider,
            price=row.get("PRICE"),
            bid=row.get("BID"),
            ask=row.get("ASK"),
            source_timestamp=row.get("LASTUPDATE"),
            started=started,
            received_at=received_at,
            quote_kind=QuoteKind.TICKER.value,
            market_status="open",
        )
        if isinstance(quote, LivePriceQuote):
            breaker.record_success()
        else:
            breaker.record_failure()
        return quote
    except Exception as exc:
        breaker.record_failure()
        logger.debug("[price] CryptoCompare typed quote error for %s: %s", symbol, exc)
        return _typed_failure(symbol, provider, f"provider_error:{type(exc).__name__}")


async def _fetch_yahoo_quote(symbol: str) -> LivePriceQuote | LivePriceFailure:
    import requests

    provider = "yahoo"
    breaker = _get_breaker(provider)
    if not breaker.allow():
        return _typed_failure(symbol, provider, "circuit_open", breaker_state=BreakerState.OPEN.value)
    started = time.perf_counter()
    try:
        _, provider_symbol, _ = _provider_identity(symbol, provider)
        if not provider_symbol:
            return _typed_failure(symbol, provider, "unsupported_symbol", retryable=False)
        response = await asyncio.to_thread(
            requests.get,
            f"https://query1.finance.yahoo.com/v8/finance/chart/{provider_symbol}",
            params={"interval": "1m", "range": "1d"},
            timeout=5,
        )
        received_at = time.time()
        payload = response.json() if response.ok else {}
        rows = (payload.get("chart") or {}).get("result") or []
        if not response.ok or not rows:
            breaker.record_failure()
            return _typed_failure(symbol, provider, f"invalid_response:{getattr(response, 'status_code', 'unknown')}")
        meta = rows[0].get("meta") or {}
        regular_price = meta.get("regularMarketPrice")
        regular_time = meta.get("regularMarketTime")
        if regular_price and regular_time:
            quote = _typed_quote(
                symbol=symbol,
                provider=provider,
                price=regular_price,
                bid=meta.get("bid"),
                ask=meta.get("ask"),
                source_timestamp=regular_time,
                started=started,
                received_at=received_at,
                quote_kind=QuoteKind.TICKER.value,
                market_status=str(meta.get("marketState") or "unknown").lower(),
            )
        else:
            previous_close = meta.get("previousClose") or meta.get("chartPreviousClose")
            if not previous_close:
                breaker.record_failure()
                return _typed_failure(symbol, provider, "live_price_missing")
            quote = _typed_quote(
                symbol=symbol,
                provider=provider,
                price=previous_close,
                source_timestamp=None,
                started=started,
                received_at=received_at,
                quote_kind=QuoteKind.PREVIOUS_CLOSE.value,
                market_status="closed",
                confidence_reasons=("analysis_only_previous_close",),
            )
        if isinstance(quote, LivePriceQuote):
            breaker.record_success()
        else:
            breaker.record_failure()
        return quote
    except Exception as exc:
        breaker.record_failure()
        logger.debug("[price] Yahoo typed quote error for %s: %s", symbol, exc)
        return _typed_failure(symbol, provider, f"provider_error:{type(exc).__name__}")


async def _fetch_twelvedata_quote(symbol: str) -> LivePriceQuote | LivePriceFailure:
    """Fetch a source-timestamped quote for FX, metals, indices, and stocks."""
    import requests

    provider = "twelvedata"
    breaker = _get_breaker(provider)
    if not breaker.allow():
        return _typed_failure(symbol, provider, "circuit_open", breaker_state=BreakerState.OPEN.value)
    api_key = (
        os.getenv("TWELVEDATA_API_KEY")
        or os.getenv("TWELVE_DATA_API_KEY")
        or ""
    ).strip()
    if not api_key:
        return _typed_failure(symbol, provider, "provider_not_configured", retryable=False)
    canonical, provider_symbol, _ = _provider_identity(symbol, provider)
    if not provider_symbol:
        return _typed_failure(canonical, provider, "unsupported_symbol", retryable=False)

    started = time.perf_counter()
    try:
        response = await asyncio.to_thread(
            requests.get,
            "https://api.twelvedata.com/quote",
            params={"symbol": provider_symbol, "apikey": api_key},
            timeout=5,
        )
        received_at = time.time()
        payload = response.json() if response.ok else {}
        if (
            not response.ok
            or str(payload.get("status") or "").lower() == "error"
            or payload.get("code")
        ):
            reason = f"invalid_response:{getattr(response, 'status_code', 'unknown')}"
            if getattr(response, "status_code", None) == 429:
                reason = "rate_limit:twelvedata"
            elif payload.get("code"):
                reason = f"provider_error_code:{payload.get('code')}"
            breaker.record_failure()
            return _typed_failure(canonical, provider, reason)

        market_open = payload.get("is_market_open")
        quote = _typed_quote(
            symbol=canonical,
            provider=provider,
            price=payload.get("price") or payload.get("close"),
            source_timestamp=payload.get("timestamp"),
            started=started,
            received_at=received_at,
            quote_kind=QuoteKind.TICKER.value,
            market_status=(
                "open"
                if market_open is True
                else "closed"
                if market_open is False
                else "unknown"
            ),
        )
        if isinstance(quote, LivePriceQuote):
            breaker.record_success()
        else:
            breaker.record_failure()
        return quote
    except Exception as exc:
        breaker.record_failure()
        logger.debug("[price] Twelve Data typed quote error for %s: %s", symbol, exc)
        return _typed_failure(symbol, provider, f"provider_error:{type(exc).__name__}")


async def _fetch_coinbase_quote(symbol: str) -> LivePriceQuote | LivePriceFailure:
    """Fetch live quote from Coinbase public ticker endpoint.

    Coinbase is the most Railway-compatible crypto provider because its REST API
    is accessible from most cloud regions without geo-restrictions.
    Uses the /products/<product_id>/ticker endpoint which provides bid/ask/last.
    """
    import requests

    provider = "coinbase"
    breaker = _get_breaker(provider)
    if not breaker.allow():
        return _typed_failure(symbol, provider, "circuit_open", breaker_state=BreakerState.OPEN.value)
    started = time.perf_counter()
    try:
        # Normalize symbol: BTCUSDT -> BTC-USD, ETHUSDT -> ETH-USD
        canonical, provider_symbol, _ = _provider_identity(symbol, provider)
        compact = canonical.replace("/", "").replace("-", "")
        base, quote = compact, "USD"
        for suffix in ("USDT", "USDC", "BUSD", "USD"):
            if compact.endswith(suffix):
                base, quote = compact[:-len(suffix)], "USD"
                break
        product_id = f"{base}-{quote}"
        response = await asyncio.to_thread(
            requests.get,
            f"https://api.exchange.coinbase.com/products/{product_id}/ticker",
            timeout=5,
        )
        received_at = time.time()
        if not response.ok:
            reason = f"http_status:{response.status_code}"
            if response.status_code == 429:
                reason = "rate_limit:coinbase"
            elif response.status_code in (401, 403):
                reason = "auth_or_permission_denied"
            breaker.record_failure()
            return _typed_failure(symbol, provider, reason)
        payload = response.json() or {}
        price = payload.get("price") or payload.get("last")
        bid = payload.get("bid")
        ask = payload.get("ask")
        source_time = payload.get("time")
        quote = _typed_quote(
            symbol=symbol,
            provider=provider,
            price=price,
            bid=bid,
            ask=ask,
            source_timestamp=source_time,
            started=started,
            received_at=received_at,
            quote_kind=QuoteKind.BID_ASK.value if bid and ask else QuoteKind.TICKER.value,
            market_status="open",
        )
        if isinstance(quote, LivePriceQuote):
            breaker.record_success()
            logger.info(
                "[price] coinbase_live_quote symbol=%s price=%s bid=%s ask=%s product=%s latency_ms=%s",
                symbol, price, bid, ask, product_id, quote.latency_ms,
            )
        else:
            breaker.record_failure()
        return quote
    except Exception as exc:
        breaker.record_failure()
        logger.debug("[price] Coinbase quote error for %s: %s", symbol, exc)
        return _typed_failure(symbol, provider, f"provider_error:{type(exc).__name__}")


async def _fetch_okx_quote(symbol: str) -> LivePriceQuote | LivePriceFailure:
    """Fetch live quote from OKX public ticker endpoint.

    OKX is a reliable Railway-compatible fallback for crypto quotes.
    Uses the /api/v5/market/ticker endpoint.
    """
    import requests

    provider = "okx"
    breaker = _get_breaker(provider)
    if not breaker.allow():
        return _typed_failure(symbol, provider, "circuit_open", breaker_state=BreakerState.OPEN.value)
    started = time.perf_counter()
    try:
        canonical, provider_symbol, _ = _provider_identity(symbol, provider)
        compact = canonical.replace("/", "").replace("-", "")
        # OKX uses - separator: BTC-USDT
        base, quote = compact, "USDT"
        for suffix in ("USDT", "USDC", "USD"):
            if compact.endswith(suffix):
                base, quote = compact[:-len(suffix)], suffix
                break
        inst_id = f"{base}-{quote}"
        response = await asyncio.to_thread(
            requests.get,
            "https://www.okx.com/api/v5/market/ticker",
            params={"instId": inst_id},
            timeout=5,
        )
        received_at = time.time()
        payload = response.json() if response.ok else {}
        if not response.ok or str(payload.get("code") or "1") != "0":
            reason = f"invalid_response:{getattr(response, 'status_code', 'unknown')}"
            if not response.ok and response.status_code == 429:
                reason = "rate_limit:okx"
            breaker.record_failure()
            return _typed_failure(symbol, provider, reason)
        data_list = payload.get("data") or []
        if not data_list:
            breaker.record_failure()
            return _typed_failure(symbol, provider, "no_ticker_data")
        row = data_list[0] or {}
        price = row.get("last")
        bid = row.get("bidPx")
        ask = row.get("askPx")
        source_time = row.get("ts")
        quote = _typed_quote(
            symbol=symbol,
            provider=provider,
            price=price,
            bid=bid,
            ask=ask,
            source_timestamp=source_time,
            started=started,
            received_at=received_at,
            quote_kind=QuoteKind.BID_ASK.value if bid and ask else QuoteKind.TICKER.value,
            market_status="open",
        )
        if isinstance(quote, LivePriceQuote):
            breaker.record_success()
            logger.info(
                "[price] okx_live_quote symbol=%s price=%s bid=%s ask=%s instId=%s latency_ms=%s",
                symbol, price, bid, ask, inst_id, quote.latency_ms,
            )
        else:
            breaker.record_failure()
        return quote
    except Exception as exc:
        breaker.record_failure()
        logger.debug("[price] OKX quote error for %s: %s", symbol, exc)
        return _typed_failure(symbol, provider, f"provider_error:{type(exc).__name__}")


async def _fetch_polygon_quote(symbol: str) -> LivePriceQuote | LivePriceFailure:
    import requests

    provider = "polygon"
    breaker = _get_breaker(provider)
    if not breaker.allow():
        return _typed_failure(symbol, provider, "circuit_open", breaker_state=BreakerState.OPEN.value)
    api_key = os.getenv("POLYGON_API_KEY", "").strip()
    if not api_key:
        return _typed_failure(symbol, provider, "provider_not_configured", retryable=False)
    canonical, provider_symbol, asset_class = _provider_identity(symbol, provider)
    if asset_class not in {"stock", "index"} or not provider_symbol:
        return _typed_failure(symbol, provider, "unsupported_asset_class", retryable=False)
    started = time.perf_counter()
    try:
        response = await asyncio.to_thread(
            requests.get,
            f"https://api.polygon.io/v2/last/trade/{provider_symbol}",
            params={"apiKey": api_key},
            timeout=5,
        )
        received_at = time.time()
        payload = response.json() if response.ok else {}
        row = payload.get("results") or {}
        if not response.ok or not row:
            breaker.record_failure()
            return _typed_failure(canonical, provider, f"invalid_response:{getattr(response, 'status_code', 'unknown')}")
        quote = _typed_quote(
            symbol=canonical,
            provider=provider,
            price=row.get("p"),
            source_timestamp=row.get("t"),
            started=started,
            received_at=received_at,
            quote_kind=QuoteKind.TRADE.value,
        )
        if isinstance(quote, LivePriceQuote):
            breaker.record_success()
        else:
            breaker.record_failure()
        return quote
    except Exception as exc:
        breaker.record_failure()
        logger.debug("[price] Polygon typed quote error for %s: %s", symbol, exc)
        return _typed_failure(symbol, provider, f"provider_error:{type(exc).__name__}")


async def _fetch_structured_quote(
    provider: str,
    symbol: str,
    timeout: float,
) -> LivePriceQuote | LivePriceFailure:
    adapter = {
        "coinbase": _fetch_coinbase_quote,
        "okx": _fetch_okx_quote,
        "binance": _fetch_binance_quote,
        "bybit": _fetch_bybit_quote,
        "cryptocompare": _fetch_cryptocompare_quote,
        "yahoo": _fetch_yahoo_quote,
        "twelvedata": _fetch_twelvedata_quote,
        "polygon": _fetch_polygon_quote,
    }.get(provider)
    if adapter is None:
        return _typed_failure(symbol, provider, "adapter_not_registered", retryable=False)
    try:
        return await asyncio.wait_for(adapter(symbol), timeout=timeout)
    except asyncio.TimeoutError:
        return _typed_failure(symbol, provider, "provider_timeout")


# ============================================================================
# Primary API with Circuit Breaker & Failover
# ============================================================================

async def get_live_price_result(
    symbol: str,
    timeout: float = 5.0,
) -> LivePriceQuote | LivePriceFailure:
    """Get a typed quote or a typed terminal failure after provider failover.

    Analysis-only observations such as Yahoo previous close are remembered but
    do not prevent a later provider from supplying a source-timestamped quote.
    """
    if not symbol:
        return LivePriceFailure("", "none", "missing_symbol", retryable=False)

    from services.asset_mapper import canonicalize_symbol

    symbol = canonicalize_symbol(symbol)
    providers = _get_providers_for_asset(symbol)
    analysis_fallback: LivePriceQuote | None = None
    failures: list[LivePriceFailure] = []
    deadline = time.perf_counter() + max(0.1, float(timeout))

    for provider in providers:
        remaining = deadline - time.perf_counter()
        if remaining <= 0:
            failures.append(_typed_failure(symbol, provider, "overall_timeout_budget_exhausted"))
            break
        try:
            per_attempt_timeout = max(0.1, min(2.0, remaining))
            result = await _fetch_structured_quote(provider, symbol, timeout=per_attempt_timeout)
            if isinstance(result, LivePriceFailure):
                failures.append(result)
                logger.debug(
                    "[price] %s provider=%s failed reason=%s",
                    symbol,
                    provider,
                    result.reason,
                )
                continue

            if result.quote_kind == QuoteKind.PREVIOUS_CLOSE.value or result.source_timestamp is None:
                analysis_fallback = analysis_fallback or result
                logger.info(
                    "[price] %s provider=%s returned analysis-only quote kind=%s",
                    symbol,
                    provider,
                    result.quote_kind,
                )
                continue

            logger.info(
                "[price] %s price=%s provider=%s latency_ms=%s source_age_ms=%s request_id=%s",
                symbol,
                result.price,
                provider,
                result.latency_ms,
                int(max(0.0, result.source_age_seconds() or 0.0) * 1000),
                result.request_id,
            )
            return result
        except Exception as e:
            logger.debug("[price] %s: %s error: %s", symbol, provider, e)
            failures.append(_typed_failure(symbol, provider, f"adapter_error:{type(e).__name__}"))

    if analysis_fallback is not None:
        return analysis_fallback
    reasons = ",".join(f"{item.provider}:{item.reason}" for item in failures[-5:]) or "no_provider_attempted"
    logger.warning("[price] All providers failed for %s reasons=%s", symbol, reasons)
    return LivePriceFailure(symbol, "all", f"all_providers_failed:{reasons}")


async def get_live_price_quote(
    symbol: str,
    timeout: float = 5.0,
) -> Optional[LivePriceQuote]:
    """Compatibility wrapper returning ``None`` instead of a typed failure."""
    result = await get_live_price_result(symbol, timeout=timeout)
    return result if isinstance(result, LivePriceQuote) else None


async def get_live_price(
    symbol: str,
    timeout: float = 5.0,
) -> Optional[float]:
    """Get live price with circuit breaker and automatic failover.

    Compatibility wrapper around get_live_price_quote. New final-send code should
    use get_live_price_quote so it can inspect provider metadata.
    """
    quote = await get_live_price_quote(symbol, timeout=timeout)
    return float(quote.price) if quote is not None else None


async def get_cached_price(
    symbol: str,
    max_age_seconds: float = 30.0,
) -> Optional[float]:
    """
    Get price with optional cache.
    
    Uses Redis cache if available to reduce API calls.
    """
    try:
        from core.redis_state import state
        
        cache_key = f"live_price:{symbol.upper()}"
        
        # Try cache first
        cached = await state.cache_get(cache_key)
        if cached:
            import json
            try:
                data = json.loads(cached)
                price = data.get("price")
                ts = data.get("timestamp", 0)
                
                if price and ts:
                    age = time.time() - ts
                    if age <= max_age_seconds:
                        return float(price)
            except Exception:
                pass
        
        # Fetch fresh price
        price = await get_live_price(symbol)
        
        if price:
            # Cache it
            import json
            await state.cache_set(
                cache_key,
                json.dumps({"price": price, "timestamp": time.time()}),
                ex=int(max_age_seconds),
            )
        
        return price
        
    except Exception as e:
        logger.debug(f"[price] Cache error: {e}")
        return await get_live_price(symbol)


# Convenience function aliases
get_price = get_live_price
fetch_price = get_live_price


# ============================================================================
# Diagnostic Functions
# ============================================================================

def get_circuit_breaker_status() -> Dict[str, Dict[str, Any]]:
    """Get circuit breaker status for all providers."""
    status = {}
    
    for name, breaker in _price_breakers.items():
        now = time.time()
        open_remaining = max(0.0, breaker._open_until - now) if breaker._open_until else 0.0
        
        status[name] = {
            "open": bool(open_remaining > 0),
            "open_remaining_s": open_remaining,
            "failures": len(breaker._failures),
        }
    
    return status


__all__ = [
    "LivePriceFailure",
    "LivePriceQuote",
    "get_live_price_result",
    "get_live_price_quote",
    "get_live_price",
    "get_cached_price",
    "get_price",
    "fetch_price",
    "get_circuit_breaker_status",
    "_is_crypto",
    "_get_providers_for_asset",
]
