import os
import requests
import time
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Tuple, Optional

logger = logging.getLogger(__name__)

_NEWS_CACHE = {}
_NEWS_CACHE_TTL = 300  # 5 minutes


def _safe_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (list, tuple)):
        return " ".join(_safe_text(item) for item in value[:5])
    if isinstance(value, dict):
        for key in ("title", "body", "description", "value", "text", "name"):
            if key in value:
                return _safe_text(value.get(key))
        return str(value)
    return str(value)

def fetch_news_headlines(asset: str, lookback_minutes: int = 120) -> List[Tuple[str, str, int]]:
    """
    Fetch news headlines from multiple sources.
    Returns list of (title, published_at, sentiment_score).
    
    Sources tried in order:
    1. NewsAPI.org (NEWSAPI_KEY env var)
    2. CryptoCompare News API (free, no key for basic)
    3. Fallback empty
    """
    cache_key = f"{asset}:{lookback_minutes}"
    cached = _NEWS_CACHE.get(cache_key)
    if cached and (time.time() - cached["ts"]) < _NEWS_CACHE_TTL:
        return cached["data"]
    
    headlines = []
    
    # 1. Try NewsAPI
    newsapi_key = os.getenv("NEWSAPI_KEY", "").strip()
    if newsapi_key:
        try:
            # Map asset to search query
            query = _asset_to_news_query(asset)
            cutoff = (datetime.now(timezone.utc) - timedelta(minutes=lookback_minutes)).isoformat()
            resp = requests.get(
                "https://newsapi.org/v2/everything",
                params={
                    "q": query,
                    "from": cutoff,
                    "sortBy": "publishedAt",
                    "pageSize": 10,
                    "apiKey": newsapi_key,
                },
                timeout=8,
            )
            if resp.ok:
                articles = resp.json().get("articles", [])
                for art in articles:
                    title = art.get("title", "")
                    pub = art.get("publishedAt", "")
                    score = simple_sentiment_score(title + " " + (art.get("description") or ""))
                    headlines.append((title, pub, score))
        except Exception as e:
            logger.warning(f"NewsAPI fetch failed: {e}")
    
    # 2. CryptoCompare News (free, good for crypto)
    if not headlines and _is_crypto_asset(asset):
        try:
            base = asset.upper().replace("USDT", "").replace("USD", "").replace("BUSD", "")
            resp = requests.get(
                f"https://min-api.cryptocompare.com/data/v2/news/?categories={base}",
                timeout=8,
            )
            if resp.ok:
                payload = resp.json()
                articles = payload.get("Data", []) if isinstance(payload, dict) else []
                if not isinstance(articles, list):
                    articles = []
                for art in articles[:10]:
                    if not isinstance(art, dict):
                        continue
                    title = _safe_text(art.get("title", ""))
                    pub = datetime.fromtimestamp(int(art.get("published_on", 0) or 0), tz=timezone.utc).isoformat()
                    body = _safe_text(art.get("body", ""))
                    score = simple_sentiment_score(title + " " + body[:200])
                    headlines.append((title, pub, score))
        except Exception as e:
            logger.warning(f"CryptoCompare news failed: {e}")
    
    _NEWS_CACHE[cache_key] = {"ts": time.time(), "data": headlines}
    return headlines

def _asset_to_news_query(asset: str) -> str:
    """Convert asset symbol to news search query."""
    a = asset.upper().strip()
    # Crypto
    mapping = {
        "BTCUSDT": "Bitcoin BTC",
        "ETHUSDT": "Ethereum ETH",
        "SOLUSDT": "Solana SOL",
        "XRPUSDT": "Ripple XRP",
        "BNBUSDT": "BNB Binance",
        "XAUUSD": "Gold XAUUSD",
        "XAGUSD": "Silver XAGUSD",
        "EURUSD": "EUR USD forex",
        "GBPUSD": "GBP USD forex",
        "USDJPY": "USD JPY forex",
    }
    return mapping.get(a, a)

def _is_crypto_asset(asset: str) -> bool:
    a = (asset or "").upper()
    return a.endswith("USDT") or a.endswith("USD") or a.endswith("BUSD") or a.endswith("USDC")

def simple_sentiment_score(text: str) -> int:
    """Enhanced sentiment scoring with more keywords."""
    text = text.lower()
    positive = [
        'surge', 'rally', 'gain', 'rise', 'bull', 'record', 'beat', 'soar',
        'breakout', 'upgrade', 'strong', 'momentum', 'outperform', 'growth',
        'recovery', 'rebound', 'highs', 'buy', 'accumulate', 'bullish',
        'optimism', 'upside', 'profit', 'boost', 'support'
    ]
    negative = [
        'fall', 'drop', 'loss', 'bear', 'miss', 'crash', 'plunge', 'decline',
        'sell', 'warning', 'risk', 'fear', 'dump', 'collapse', 'downgrade',
        'weak', 'correction', 'selloff', 'panic', 'bearish', 'concern',
        'uncertainty', 'recession', 'inflation', 'crisis', 'fraud'
    ]
    score = 0
    for word in positive:
        if word in text:
            score += 1
    for word in negative:
        if word in text:
            score -= 1
    return max(-3, min(3, score))

def get_news_sentiment(asset: str, lookback_minutes: int = 120) -> float:
    """Aggregate sentiment for recent news headlines."""
    headlines = fetch_news_headlines(asset, lookback_minutes)
    if not headlines:
        return 0.0
    total = sum(s for _, _, s in headlines)
    return total / max(1, len(headlines))

