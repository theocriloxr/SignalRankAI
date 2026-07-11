"""Deterministic news intelligence helpers for signal gating and sizing.

The module intentionally does not fetch live news. Callers pass known headlines or
provider payloads, and this layer normalizes, deduplicates, classifies, and scores
the evidence so downstream gates can act without hallucinated context.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Sequence


SOURCE_RELIABILITY = {
    "reuters": 0.95,
    "bloomberg": 0.95,
    "ap": 0.93,
    "associated press": 0.93,
    "cnbc": 0.78,
    "financial times": 0.88,
    "coindesk": 0.74,
    "cointelegraph": 0.62,
    "twitter": 0.28,
    "x": 0.28,
    "telegram": 0.22,
    "unknown": 0.35,
}

EVENT_KEYWORDS = {
    "central_bank": ("fomc", "fed", "ecb", "boe", "rate decision", "interest rate"),
    "inflation": ("cpi", "ppi", "inflation", "core prices"),
    "employment": ("nfp", "payroll", "unemployment", "jobless"),
    "regulation": ("sec", "lawsuit", "ban", "approval", "etf", "regulator"),
    "exchange_flow": ("exchange inflow", "exchange outflow", "whale", "liquidation"),
    "earnings": ("earnings", "guidance", "revenue", "profit"),
    "security": ("hack", "exploit", "breach", "halted withdrawals"),
}

ASSET_ALIASES = {
    "BTC": ("btc", "bitcoin", "btcusd", "btcusdt"),
    "ETH": ("eth", "ethereum", "ethusd", "ethusdt"),
    "SOL": ("sol", "solana", "solusd", "solusdt"),
    "XAUUSD": ("xau", "gold", "xauusd"),
    "EURUSD": ("eurusd", "euro", "ecb"),
    "GBPUSD": ("gbpusd", "sterling", "boe"),
    "USD": ("usd", "dollar", "fed", "fomc"),
}

POSITIVE_TERMS = ("approval", "beats", "surge", "rally", "inflow", "eases", "bullish")
NEGATIVE_TERMS = ("ban", "lawsuit", "hack", "misses", "crash", "outflow", "bearish", "halted")
SENSATIONAL_TERMS = ("guaranteed", "100x", "secret", "insider", "leaked", "unconfirmed")


def _clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def _source_score(source: Any) -> float:
    source_norm = _clean_text(source).lower() or "unknown"
    return SOURCE_RELIABILITY.get(source_norm, SOURCE_RELIABILITY["unknown"])


def normalize_story(story: Dict[str, Any]) -> Dict[str, Any]:
    title = _clean_text(story.get("title") or story.get("headline"))
    body = _clean_text(story.get("body") or story.get("summary") or story.get("description"))
    source = _clean_text(story.get("source") or story.get("provider") or "unknown")
    url = _clean_text(story.get("url"))
    published_at = story.get("published_at") or story.get("created_at") or story.get("time")
    return {
        "title": title,
        "body": body,
        "source": source or "unknown",
        "url": url,
        "published_at": published_at,
        "text": _clean_text(f"{title} {body}"),
        "source_reliability": _source_score(source),
    }


def deduplicate_stories(stories: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for raw in stories:
        story = normalize_story(raw)
        key = story["url"].lower() or re.sub(r"[^a-z0-9]+", "", story["title"].lower())[:120]
        if not key or key in seen:
            continue
        seen.add(key)
        unique.append(story)
    return unique


def classify_event(story: Dict[str, Any]) -> str:
    text = story.get("text", "").lower()
    for event_type, keywords in EVENT_KEYWORDS.items():
        if any(keyword in text for keyword in keywords):
            return event_type
    return "market_commentary"


def affected_assets(stories: Sequence[Dict[str, Any]]) -> List[str]:
    found: set[str] = set()
    corpus = " ".join(story.get("text", "") for story in stories).lower()
    for asset, aliases in ASSET_ALIASES.items():
        if any(re.search(rf"\b{re.escape(alias)}\b", corpus) for alias in aliases):
            found.add(asset)
    return sorted(found)


def sentiment_score(stories: Sequence[Dict[str, Any]]) -> float:
    if not stories:
        return 0.0
    total = 0.0
    weight = 0.0
    for story in stories:
        text = story.get("text", "").lower()
        pos = sum(1 for term in POSITIVE_TERMS if term in text)
        neg = sum(1 for term in NEGATIVE_TERMS if term in text)
        reliability = float(story.get("source_reliability", 0.35) or 0.35)
        total += max(-1.0, min(1.0, (pos - neg) / 3.0)) * reliability
        weight += reliability
    return round(total / weight, 4) if weight else 0.0


def fake_news_risk(stories: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    if not stories:
        return {"score": 0.0, "flags": []}
    flags: list[str] = []
    avg_reliability = sum(float(s.get("source_reliability", 0.35) or 0.35) for s in stories) / len(stories)
    if avg_reliability < 0.4:
        flags.append("low_source_reliability")
    text = " ".join(s.get("text", "") for s in stories).lower()
    if any(term in text for term in SENSATIONAL_TERMS):
        flags.append("sensational_language")
    if len(stories) == 1 and avg_reliability < 0.6:
        flags.append("single_unconfirmed_source")
    score = min(1.0, (1.0 - avg_reliability) + (0.18 * len(flags)))
    return {"score": round(score, 4), "flags": flags}


def assess_news(stories: Iterable[Dict[str, Any]], signal: Dict[str, Any] | None = None) -> Dict[str, Any]:
    normalized = deduplicate_stories(stories)
    event_counts: dict[str, int] = {}
    for story in normalized:
        event = classify_event(story)
        story["event_type"] = event
        event_counts[event] = event_counts.get(event, 0) + 1

    reliability = (
        sum(float(s.get("source_reliability", 0.35) or 0.35) for s in normalized) / len(normalized)
        if normalized
        else 0.0
    )
    fake_risk = fake_news_risk(normalized)
    sentiment = sentiment_score(normalized)
    assets = affected_assets(normalized)
    high_impact_count = sum(event_counts.get(k, 0) for k in ("central_bank", "inflation", "employment", "security"))
    volatility_score = min(1.0, 0.18 * len(normalized) + 0.22 * high_impact_count + fake_risk["score"] * 0.2)
    uncertainty = min(1.0, (1.0 - reliability) * 0.7 + fake_risk["score"] * 0.3)

    action = "allow"
    confidence_adjustment = 0.0
    if fake_risk["score"] >= 0.7 or uncertainty >= 0.75:
        action = "suppress"
        confidence_adjustment = -0.2
    elif volatility_score >= 0.55 or abs(sentiment) >= 0.55:
        action = "delay"
        confidence_adjustment = -0.1

    if signal:
        signal_asset = _clean_text(signal.get("asset")).upper()
        if signal_asset and assets and all(not signal_asset.startswith(asset) for asset in assets):
            confidence_adjustment = min(confidence_adjustment + 0.03, 0.0)

    return {
        "ok": True,
        "story_count": len(normalized),
        "deduplicated_stories": normalized,
        "source_reliability": round(reliability, 4),
        "fake_news_risk": fake_risk,
        "event_counts": event_counts,
        "affected_assets": assets,
        "sentiment_score": sentiment,
        "expected_volatility_score": round(volatility_score, 4),
        "half_life_minutes": 240 if high_impact_count else 90 if normalized else 0,
        "uncertainty": round(uncertainty, 4),
        "signal_action": action,
        "confidence_adjustment": round(confidence_adjustment, 4),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


__all__ = [
    "assess_news",
    "affected_assets",
    "classify_event",
    "deduplicate_stories",
    "fake_news_risk",
    "normalize_story",
    "sentiment_score",
]
