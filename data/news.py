import os
import requests
import time
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, List, Tuple

logger = logging.getLogger(__name__)

_NEWS_CACHE = {}
_NEWS_CACHE_TTL = 300  # 5 minutes


def _asset_base_symbol(asset: str) -> str:
    a = (asset or "").upper().strip()
    for suffix in ("USDT", "USDC", "BUSD", "USD"):
        if a.endswith(suffix) and len(a) > len(suffix):
            return a[: -len(suffix)]
    return a


def _append_headlines(headlines: list[tuple[str, str, int]], rows: list[tuple[str, str, int]], *, seen: set[str]) -> None:
    for title, published_at, score in rows:
        clean_title = _safe_text(title).strip()
        if not clean_title:
            continue
        dedupe_key = clean_title.lower()
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        headlines.append((clean_title[:240], _safe_text(published_at), int(score)))


def _parse_news_time(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        if isinstance(value, (int, float)):
            ts = float(value)
            if ts > 10_000_000_000:
                ts /= 1000.0
            return datetime.fromtimestamp(ts, tz=timezone.utc)
    except Exception:
        return None
    text = _safe_text(value).strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except Exception:
        pass
    try:
        if len(text) >= 15 and text[:8].isdigit():
            return datetime.strptime(text[:15], "%Y%m%dT%H%M%S").replace(tzinfo=timezone.utc)
    except Exception:
        return None
    return None


def _is_within_lookback(value: Any, lookback_minutes: int) -> bool:
    parsed = _parse_news_time(value)
    if parsed is None:
        return True
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=max(0, int(lookback_minutes or 0)))
    return parsed >= cutoff


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
    2. X recent search (X_BEARER_TOKEN env var)
    3. CryptoPanic news (CRYPTOPANIC_TOKEN / CRYPTOPANIC_API_KEY)
    4. Alpha Vantage NEWS_SENTIMENT (ALPHAVANTAGE_API_KEY)
    5. CryptoCompare News API (free, no key for basic)
    6. CoinGecko status updates (public)
    7. Fallback empty
    """
    cache_key = f"{asset}:{lookback_minutes}"
    cached = _NEWS_CACHE.get(cache_key)
    if cached and (time.time() - cached["ts"]) < _NEWS_CACHE_TTL:
        return cached["data"]
    
    headlines = []
    seen: set[str] = set()
    
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
                    _append_headlines(headlines, [(title, pub, score)], seen=seen)
        except Exception as e:
            logger.warning(f"NewsAPI fetch failed: {e}")

    # 2. Try X/Twitter recent search if token is present
    x_bearer_token = (os.getenv("X_BEARER_TOKEN") or os.getenv("TWITTER_BEARER_TOKEN") or "").strip()
    if x_bearer_token:
        try:
            _append_headlines(headlines, _fetch_x_headlines(asset, lookback_minutes, x_bearer_token), seen=seen)
        except Exception as e:
            logger.warning(f"X news fetch failed: {e}")

    # 3. CryptoPanic (crypto-only, free tier available with token)
    cryptopanic_token = (os.getenv("CRYPTOPANIC_TOKEN") or os.getenv("CRYPTOPANIC_API_KEY") or "").strip()
    if cryptopanic_token and _is_crypto_asset(asset):
        try:
            _append_headlines(headlines, _fetch_cryptopanic_headlines(asset, lookback_minutes, cryptopanic_token), seen=seen)
        except Exception as e:
            logger.warning(f"CryptoPanic fetch failed: {e}")

    # 4. Alpha Vantage news sentiment (crypto / FX / stocks)
    alphavantage_key = os.getenv("ALPHAVANTAGE_API_KEY", "").strip()
    if alphavantage_key:
        try:
            _append_headlines(headlines, _fetch_alphavantage_headlines(asset, lookback_minutes, alphavantage_key), seen=seen)
        except Exception as e:
            logger.warning(f"Alpha Vantage news fetch failed: {e}")
    
    # 5. CryptoCompare News (free, good for crypto)
    if _is_crypto_asset(asset):
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
                    if _is_within_lookback(pub, lookback_minutes):
                        _append_headlines(headlines, [(title, pub, score)], seen=seen)
        except Exception as e:
            logger.warning(f"CryptoCompare news failed: {e}")

    # 6. CoinGecko public status updates (crypto-only)
    if _is_crypto_asset(asset):
        try:
            _append_headlines(headlines, _fetch_coingecko_updates(asset, lookback_minutes), seen=seen)
        except Exception as e:
            logger.warning(f"CoinGecko updates fetch failed: {e}")
    
    _NEWS_CACHE[cache_key] = {"ts": time.time(), "data": headlines}
    return headlines


def _asset_to_x_query(asset: str) -> str:
    a = (asset or "").upper().strip()
    mapping = {
        "BTCUSDT": "(bitcoin OR btc OR btcusdt) lang:en -is:retweet",
        "ETHUSDT": "(ethereum OR eth OR ethusdt) lang:en -is:retweet",
        "SOLUSDT": "(solana OR sol OR solusdt) lang:en -is:retweet",
        "XRPUSDT": "(ripple OR xrp OR xrpusdt) lang:en -is:retweet",
        "BNBUSDT": "(bnb OR binance coin OR bnbusdt) lang:en -is:retweet",
        "EURUSD": "(EURUSD OR euro dollar OR eur usd forex) lang:en -is:retweet",
        "GBPUSD": "(GBPUSD OR pound dollar OR gbp usd forex) lang:en -is:retweet",
        "USDJPY": "(USDJPY OR dollar yen OR usd jpy forex) lang:en -is:retweet",
        "XAUUSD": "(gold OR xauusd OR xau usd) lang:en -is:retweet",
        "XAGUSD": "(silver OR xagusd OR xag usd) lang:en -is:retweet",
    }
    if a in mapping:
        return mapping[a]
    return f"({a} OR {a.replace('USDT', '')}) lang:en -is:retweet"


def _fetch_x_headlines(asset: str, lookback_minutes: int, bearer_token: str) -> List[Tuple[str, str, int]]:
    since_time = datetime.now(timezone.utc) - timedelta(minutes=max(5, int(lookback_minutes or 120)))
    params = {
        "query": _asset_to_x_query(asset),
        "max_results": 20,
        "tweet.fields": "created_at,text,lang",
        "start_time": since_time.isoformat().replace("+00:00", "Z"),
    }
    headers = {"Authorization": f"Bearer {bearer_token}"}

    resp = requests.get(
        "https://api.twitter.com/2/tweets/search/recent",
        params=params,
        headers=headers,
        timeout=8,
    )
    if not resp.ok:
        return []

    payload = resp.json() if callable(getattr(resp, "json", None)) else {}
    data = payload.get("data", []) if isinstance(payload, dict) else []
    if not isinstance(data, list):
        data = []

    out: list[tuple[str, str, int]] = []
    for item in data[:20]:
        if not isinstance(item, dict):
            continue
        text = _safe_text(item.get("text", ""))
        if not text:
            continue
        created_at = _safe_text(item.get("created_at", ""))
        score = simple_sentiment_score(text)
        out.append((text[:240], created_at, score))
    return out


def _fetch_cryptopanic_headlines(asset: str, lookback_minutes: int, token: str) -> List[Tuple[str, str, int]]:
    if not _is_crypto_asset(asset):
        return []
    base = _asset_base_symbol(asset)
    params = {
        "auth_token": token,
        "currencies": base,
        "public": "true",
        "kind": "news",
        "filter": "hot",
        "regions": "en",
    }
    resp = requests.get("https://cryptopanic.com/api/v1/posts/", params=params, timeout=8)
    if not resp.ok:
        return []
    payload = resp.json() if callable(getattr(resp, "json", None)) else {}
    results = payload.get("results", []) if isinstance(payload, dict) else []
    if not isinstance(results, list):
        results = []

    out: list[tuple[str, str, int]] = []
    for item in results[:20]:
        if not isinstance(item, dict):
            continue
        title = _safe_text(item.get("title") or item.get("domain") or "")
        published_at = _safe_text(item.get("published_at") or item.get("created_at") or "")
        if not _is_within_lookback(published_at, lookback_minutes):
            continue
        body = _safe_text(item.get("currencies") or item.get("slug") or "")
        score = simple_sentiment_score(f"{title} {body}")
        out.append((title, published_at, score))
    return out


def _fetch_alphavantage_headlines(asset: str, lookback_minutes: int, api_key: str) -> List[Tuple[str, str, int]]:
    query_asset = _asset_base_symbol(asset) if _is_crypto_asset(asset) else asset.upper().strip()
    topics = "cryptocurrency" if _is_crypto_asset(asset) else ("forex" if any(asset.upper().endswith(x) for x in ("USD", "EUR", "JPY", "GBP")) else "technology")
    params = {
        "function": "NEWS_SENTIMENT",
        "apikey": api_key,
        "limit": 20,
        "topics": topics,
    }
    if query_asset:
        params["tickers"] = query_asset
    resp = requests.get("https://www.alphavantage.co/query", params=params, timeout=12)
    if not resp.ok:
        return []
    payload = resp.json() if callable(getattr(resp, "json", None)) else {}
    feed = payload.get("feed", []) if isinstance(payload, dict) else []
    if not isinstance(feed, list):
        feed = []

    out: list[tuple[str, str, int]] = []
    for item in feed[:20]:
        if not isinstance(item, dict):
            continue
        title = _safe_text(item.get("title") or item.get("summary") or "")
        published_at = _safe_text(item.get("time_published") or item.get("published_at") or "")
        if not _is_within_lookback(published_at, lookback_minutes):
            continue
        summary = _safe_text(item.get("summary") or item.get("content") or "")
        ticker_sentiment = item.get("ticker_sentiment") or []
        score = simple_sentiment_score(f"{title} {summary}")
        if isinstance(ticker_sentiment, list):
            for row in ticker_sentiment:
                if not isinstance(row, dict):
                    continue
                try:
                    score += int(round(float(row.get("ticker_sentiment_score") or 0)))
                except Exception:
                    pass
        out.append((title, published_at, score))
    return out


def _fetch_coingecko_updates(asset: str, lookback_minutes: int) -> List[Tuple[str, str, int]]:
    try:
        from services.asset_mapper import map_symbol

        cg_id = map_symbol(asset.upper(), "coingecko")
        if not cg_id:
            cg_id = _asset_base_symbol(asset).lower()
    except Exception:
        cg_id = _asset_base_symbol(asset).lower()

    resp = requests.get(
        f"https://api.coingecko.com/api/v3/coins/{cg_id}/status_updates",
        params={"per_page": 10, "page": 1},
        timeout=10,
    )
    if not resp.ok:
        return []
    payload = resp.json() if callable(getattr(resp, "json", None)) else {}
    updates = payload.get("status_updates", []) if isinstance(payload, dict) else []
    if not isinstance(updates, list):
        updates = []

    out: list[tuple[str, str, int]] = []
    for item in updates[:10]:
        if not isinstance(item, dict):
            continue
        title = _safe_text(item.get("description") or item.get("project") or item.get("user") or "")
        published_at = _safe_text(item.get("created_at") or item.get("published_at") or "")
        if not _is_within_lookback(published_at, lookback_minutes):
            continue
        score = simple_sentiment_score(f"{title} {_safe_text(item.get('category') or '')}")
        out.append((title, published_at, score))
    return out

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

