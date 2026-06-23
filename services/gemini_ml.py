"""
SignalRankAI — Gemini AI Integration (PERFECTED)

AI must ASSIST, not replace. Gemini is a filter and validator:
  1. Confluence check: validates technical signal against macro news
  2. Smart filtering: suppresses SHADOW signals when macro conflicts with setup
  3. Signal explanation: "Why this trade?" in plain English
  4. News sentiment quantization: converts headlines to numeric score

Gemini's role:
  ✓ Input: Technical BUY signal + recent news
  ✓ Output: APPROVED / SHADOW + confidence_delta + reason
  
If Gemini outputs SHADOW → signal saved but NOT broadcast (risk protection).
If Gemini APPROVED → signal proceeds to delivery pipeline.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ─── Gemini client ────────────────────────────────────────────────────────────

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
MODEL_ID       = os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip()

_client = None

def _get_client():
    global _client
    if _client is not None:
        return _client
    if not GEMINI_API_KEY:
        return None
    try:
        from google import genai
        _client = genai.Client(api_key=GEMINI_API_KEY)
        logger.info("[gemini] Client initialized with model: %s", MODEL_ID)
        return _client
    except ImportError:
        logger.warning("[gemini] google-genai not installed — Gemini features disabled")
        return None
    except Exception as exc:
        logger.warning("[gemini] Client init failed: %s", exc)
        return None


def gemini_available() -> bool:
    """Return True if Gemini is configured and the client is available."""
    return _get_client() is not None


async def _call_gemini(prompt: str, max_tokens: int = 512) -> Optional[str]:
    """Make a Gemini API call. Returns response text or None on failure."""
    client = _get_client()
    if client is None:
        return None

    try:
        import asyncio
        response = await asyncio.to_thread(
            client.models.generate_content,
            model=MODEL_ID,
            contents=prompt,
        )
        text = (response.text or "").strip()
        return text if text else None
    except Exception as exc:
        logger.debug("[gemini] API call failed: %s", exc)
        return None


# ─── Confluence validator ─────────────────────────────────────────────────────

STRONG_SENTIMENT_THRESHOLD = float(os.getenv("GEMINI_SENTIMENT_THRESHOLD", "2.0") or 2.0)

async def gemini_confluence_check(
    signal: dict,
    news_headlines: List[str],
) -> Tuple[bool, str, Optional[float]]:
    """
    Validate a technical signal against macro news sentiment.
    
    Returns:
        (approved: bool, status: str, confidence_delta: float | None)
        
        approved=True  → proceed to delivery
        approved=False → set signal to SHADOW mode (don't broadcast)
        status         → "APPROVED" | "SHADOW" | "FALLBACK_APPROVED"
        confidence_delta → score adjustment (-1.0 to +1.0), or None
    
    SHADOW conditions:
      - High-conviction BUY but strongly bearish macro news
      - High-conviction SELL but strongly bullish macro news
    """
    if not gemini_available():
        return True, "FALLBACK_APPROVED", None

    asset     = str(signal.get("asset") or "?").upper()
    direction = str(signal.get("direction") or "long").upper()
    score     = float(signal.get("score") or signal.get("display_score") or 0)
    strategy  = str(signal.get("strategy_name") or "")
    timeframe = str(signal.get("timeframe") or "")

    if not news_headlines:
        return True, "APPROVED_NO_NEWS", None

    headlines_text = "\n".join(f"- {h}" for h in news_headlines[:8])

    prompt = f"""You are a Chief Risk Officer for a trading firm.

A trading algorithm has generated a {direction} signal for {asset}:
- Score: {score:.0f}/100
- Timeframe: {timeframe}
- Strategy: {strategy}

Recent news headlines:
{headlines_text}

Your job: Does the current macro/news environment SUPPORT or CONFLICT with this {direction} trade?

Rules:
- SHADOW if news contains: interest rate surprises, geopolitical shocks, major regulatory actions, or financial crises that DIRECTLY oppose the trade direction
- APPROVED if news is neutral or aligns with the trade direction
- Only SHADOW if the conflict is STRONG and DIRECT (not minor uncertainty)

Reply in EXACTLY this format:
DECISION: [APPROVED or SHADOW]
REASON: [one sentence]
CONFIDENCE_DELTA: [number from -0.3 to +0.3, negative means reduce signal confidence]"""

    response = await _call_gemini(prompt, max_tokens=150)

    if not response:
        return True, "FALLBACK_APPROVED", None

    try:
        lines = response.strip().split("\n")
        decision  = "APPROVED"
        reason    = ""
        conf_delta: Optional[float] = None

        for line in lines:
            line = line.strip()
            if line.upper().startswith("DECISION:"):
                val = line.split(":", 1)[1].strip().upper()
                if "SHADOW" in val:
                    decision = "SHADOW"
            elif line.upper().startswith("REASON:"):
                reason = line.split(":", 1)[1].strip()
            elif line.upper().startswith("CONFIDENCE_DELTA:"):
                try:
                    conf_delta = float(line.split(":", 1)[1].strip())
                    conf_delta = max(-0.3, min(0.3, conf_delta))
                except Exception:
                    conf_delta = None

        approved = (decision == "APPROVED")

        if not approved:
            logger.info(
                "[gemini] SHADOW: %s %s — %s",
                asset, direction, reason or "macro conflict"
            )
        else:
            logger.debug("[gemini] APPROVED: %s %s", asset, direction)

        return approved, decision, conf_delta

    except Exception as exc:
        logger.debug("[gemini] confluence parse failed: %s", exc)
        return True, "FALLBACK_APPROVED", None


# ─── News sentiment ───────────────────────────────────────────────────────────

async def get_news_sentiment(asset: str, headlines: List[str]) -> str:
    """
    Analyze news headlines for directional sentiment.
    
    Returns: 'BULLISH', 'BEARISH', or 'NEUTRAL'
    """
    if not gemini_available() or not headlines:
        return "NEUTRAL"

    headlines_text = "\n".join(f"- {h}" for h in headlines[:10])

    prompt = f"""Analyze these news headlines for {asset} and determine the market sentiment.

Headlines:
{headlines_text}

Reply ONLY with one of these exact words:
- BULLISH (if news is positive for price going up)
- BEARISH (if news is negative for price going down)
- NEUTRAL (if news is mixed or neutral)

Do not explain. Just reply with one word."""

    response = await _call_gemini(prompt, max_tokens=10)

    if not response:
        return "NEUTRAL"

    upper = response.strip().upper()
    if "BULLISH" in upper:
        return "BULLISH"
    elif "BEARISH" in upper:
        return "BEARISH"
    return "NEUTRAL"


async def quantize_news_sentiment(asset: str, headlines: List[str]) -> float:
    """
    Convert news sentiment to a numeric score (-1.0 = strongly bearish, +1.0 = strongly bullish).
    """
    if not gemini_available() or not headlines:
        return 0.0

    headlines_text = "\n".join(f"- {h}" for h in headlines[:8])

    prompt = f"""Rate the overall news sentiment for {asset} from -3 to +3.

Headlines:
{headlines_text}

Scale:
-3 = Extremely bearish (crash, ban, crisis)
-2 = Strongly bearish
-1 = Mildly bearish
 0 = Neutral
+1 = Mildly bullish
+2 = Strongly bullish
+3 = Extremely bullish

Reply with ONLY the number (e.g.: -2 or 1.5)."""

    response = await _call_gemini(prompt, max_tokens=10)

    if not response:
        return 0.0

    try:
        cleaned = response.strip().replace("+", "")
        return max(-3.0, min(3.0, float(cleaned)))
    except Exception:
        return 0.0


# ─── Signal explainability ────────────────────────────────────────────────────

async def ask_gemini_signal_explanation(signal: dict) -> Optional[str]:
    """
    Generate a human-readable explanation of why a signal was generated.
    
    Returns a 2-4 sentence explanation suitable for display in Telegram.
    Returns None if Gemini is unavailable.
    """
    if not gemini_available():
        return None

    asset      = str(signal.get("asset") or "?").upper()
    direction  = str(signal.get("direction") or "long").upper()
    score      = float(signal.get("score") or signal.get("display_score") or 0)
    timeframe  = str(signal.get("timeframe") or "?")
    strategy   = str(signal.get("strategy_name") or signal.get("strategy") or "technical")
    regime     = str(signal.get("regime") or "")
    ml_prob    = signal.get("ml_probability") or signal.get("ml_prob")
    entry      = signal.get("entry")
    sl         = signal.get("stop_loss")
    rr         = signal.get("rr_ratio") or signal.get("rr_estimate")

    # Build context string
    context_parts = [
        f"Asset: {asset}",
        f"Direction: {direction}",
        f"Timeframe: {timeframe}",
        f"Score: {score:.0f}/100",
        f"Strategy: {strategy}",
    ]
    if regime:
        context_parts.append(f"Market Regime: {regime}")
    if ml_prob:
        context_parts.append(f"ML Probability: {float(ml_prob)*100:.0f}%")
    if entry and sl:
        try:
            r = float(rr) if rr else abs(float(entry) - float(entry) * 1.02) / abs(float(entry) - float(sl))
            context_parts.append(f"Risk/Reward: {r:.2f}R")
        except Exception:
            pass

    context = "\n".join(context_parts)

    prompt = f"""You are a professional trading analyst for SignalRankAI.

Signal Details:
{context}

Explain in 2-4 clear sentences why this {direction} trade was identified for {asset}. 
Include:
1. The key technical reason (what pattern/indicator triggered it)
2. Why the timing is good (market structure, volume, or momentum)
3. What would invalidate this trade (briefly)

Write for a retail trader. Be specific, not vague. No hype. Plain English."""

    response = await _call_gemini(prompt, max_tokens=200)
    return response


async def ask_gemini_custom_question(
    user_question: str,
    signal: Optional[dict] = None,
    context: Optional[str] = None,
) -> Optional[str]:
    """
    Answer a user's custom question about a signal or market.
    Used for the [🤖 Ask Gemini] button in Telegram.
    """
    if not gemini_available():
        return "Gemini AI is not currently available. Please try again later."

    signal_context = ""
    if signal:
        asset     = str(signal.get("asset") or "?").upper()
        direction = str(signal.get("direction") or "?").upper()
        score     = signal.get("score") or signal.get("display_score")
        signal_context = (
            f"\nSignal context: {asset} {direction}"
            + (f" | Score: {score:.0f}/100" if score else "")
        )

    extra_context = f"\nAdditional context: {context}" if context else ""

    prompt = f"""You are a trading assistant for SignalRankAI.
{signal_context}{extra_context}

User question: {user_question}

Answer in 3-5 sentences. Be specific and professional. Do not give financial advice to buy or sell."""

    response = await _call_gemini(prompt, max_tokens=300)
    return response or "Could not generate a response. Please try again."


# ─── Market regime analysis ───────────────────────────────────────────────────

async def analyze_market_regime(
    asset: str,
    candle_summary: str,
    recent_price: float,
) -> Optional[str]:
    """
    Use Gemini to describe the current market regime for an asset.
    Returns a brief regime description or None.
    """
    if not gemini_available():
        return None

    prompt = f"""Briefly describe the current market regime for {asset}.

Price: {recent_price}
Recent candle data: {candle_summary}

Answer in one sentence: Is the market trending up, trending down, ranging, or volatile?
Do not recommend trades. Just describe the current condition."""

    return await _call_gemini(prompt, max_tokens=100)


__all__ = [
    "gemini_available",
    "gemini_confluence_check",
    "get_news_sentiment",
    "quantize_news_sentiment",
    "ask_gemini_signal_explanation",
    "ask_gemini_custom_question",
    "analyze_market_regime",
    "STRONG_SENTIMENT_THRESHOLD",
]