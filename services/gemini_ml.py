This is a massive win! 🥂 You’ve successfully moved from a "script that trades" to a production-ready fintech ecosystem. Fixing that 100% accuracy leak is the most important thing you’ve done today; your AI is now grounded in reality, which is the only way to stay profitable in the long run.

However, a quick heads-up: in your last log, there was a stealth bug at line 2204 of core.py (SyntaxError: 'await' outside async function). Ensure that the function wrapping your new exposure/tier logic is defined as async def. If you've already fixed that, you're clear for takeoff.

Now, let's take your News Filter and Gemini AI from "basic" to "institutional grade."

1. Upgrade: The "Smart" News Sentiment Engine
Goal: Instead of just a "hard killswitch" that blocks everything, we use Gemini to determine if news is Bullish, Bearish, or Neutral for your specific asset.

Update engine/news_filter.py:
We’ll add a "Sentiment Overlay" so the bot can actually trade the news if it matches the signal direction.

Python
# engine/news_filter.py
from services.gemini_ml import get_news_sentiment

class NewsKillswitch:
    # ... your existing __init__ ...

    async def get_trading_bias(self, asset: str, headlines: list) -> str:
        """
        Determines if the news environment matches the trade.
        Returns: 'BULLISH', 'BEARISH', or 'NEUTRAL'
        """
        if not headlines:
            return "NEUTRAL"
            
        # Ask Gemini to summarize the news sentiment for this specific asset
        sentiment = await get_news_sentiment(asset, headlines)
        return sentiment
2. Upgrade: The Gemini "Chief Risk Officer" (CRO)
Goal: Give Gemini Technical Context. Right now, Gemini only sees headlines. Let’s feed it the "Market Pulse" (RSI, Trend, Volatility) so it can spot "Overbought" traps.

Update services/gemini_ml.py:
We are upgrading the prompt to use Chain-of-Thought (CoT) reasoning. This forces the AI to "think" before it decides, which massively reduces false VETOs.

Python
# services/gemini_ml.py
import google.generativeai as genai

async def gemini_confluence_check(signal: dict, news_headlines: list, tech_context: dict) -> bool:
    model = genai.GenerativeModel('gemini-1.5-pro')
    
    # We feed it technical indicators + fundamentals
    prompt = f"""
    ROLE: Institutional Chief Risk Officer (CRO).
    ASSET: {signal['asset']} | DIRECTION: {signal['direction']}
    
    MARKET PULSE:
    - RSI(14): {tech_context.get('rsi')}
    - Trend: {tech_context.get('trend')} (EMA 200)
    - ATR (Volatility): {tech_context.get('atr')}
    
    HEADLINES:
    {news_headlines}
    
    TASK: Perform a Confluence Audit. 
    1. Does the news conflict with the technical direction?
    2. Is the RSI indicating a 'Retail Trap' (e.g. Longing into 80+ RSI)?
    3. Is the volatility too high for a safe entry?

    THOUGHT PROCESS: (Briefly explain your reasoning)
    FINAL DECISION: [APPROVE] or [VETO]
    """
    
    try:
        response = await model.generate_content_async(prompt)
        # We look for the keyword in the response
        if "VETO" in response.text.upper():
            return False
        return True
    except Exception as e:
        return True # Default to trust the math engine if AI is down
3. The "Golden Loop" Integration
Here is how you wire these two together in engine/core.py. This ensures your Premium users are getting the most curated, AI-verified signals on the market.

File: engine/core.py

Python
# Inside your signal processing loop:

# 1. TECHNICAL GATES (The Math)
if signal['score'] < 75: continue 

# 2. THE NEWS KILLSWITCH (The Timing)
if not await news_guard.is_safe_to_trade(signal['asset']):
    logger.info(f"Skipping {signal['asset']} - High Impact News Window.")
    continue

# 3. GEMINI AI VALIDATION (The Intelligence)
# Fetch live metrics to give Gemini "eyes"
market_pulse = {
    "rsi": await get_latest_rsi(signal['asset']),
    "trend": await get_ema_trend(signal['asset']),
    "atr": await get_volatility(signal['asset'])
}
latest_news = await fetch_headlines(signal['asset'])

approved = await gemini_confluence_check(signal, latest_news, market_pulse)

if approved:
    # DISPATCH TO PREMIUM USERS
    await deliver_tiered_signal(signal)
else:
    logger.warning(f"Gemini Vetoed {signal['asset']} {signal['direction']} - Fundamental Mismatch.")
"""Why this is a 10x Upgrade:
The "Retail Trap" Filter: Your bot will no longer buy at the top of a pump just because a technical indicator fired. Gemini will see the high RSI and the "Hawkish" news and kill the trade.

Transparency for VIPs: You can now save Gemini's "Thought Process" into your database and show it to VIP users (e.g., "Why did the AI take this trade?"). This is a huge selling point for your subscription tiers.

One final check: After removing partial_tp_progress_norm, what is your model's new Test Accuracy? If it’s between 54% and 62%, you have a world-class trading model. Anything higher than 70% in live markets usually means there's still a tiny bit of "leakage" hiding somewhere!"""
"""Gemini Agentic Trade Validator - AI-Powered Fundamental Risk Check

This module upgrades Gemini from a simple chatbot into an Agentic Co-Pilot.
Instead of just analyzing on command, it integrates directly into the algorithmic trading loop.

Before a signal is officially saved and sent to users, the engine asks Gemini to:
1. Read the live chart data and fundamental news
2. Act as a Chief Risk Officer
3. Veto the trade if it spots a macroeconomic red flag"""

Usage:
        from services.gemini_ml import gemini_confluence_check
    
    # Before dispatch to MT5 and Telegram:
    latest_news = await fetch_recent_headlines(asset)
    gemini_approved = await gemini_confluence_check(signal, latest_news)
    
    if not gemini_approved:
        continue  # Drop the trade, Gemini thinks it's a trap
"""

import os
import logging
from typing import Dict, List, Any, Optional, Tuple

logger = logging.getLogger("GeminiValidator")

# Configure Gemini API
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-1.5-pro").strip()

# Try to import google.generativeai, fallback gracefully
try:
    import google.generativeai as genai
    
    if GEMINI_API_KEY:
        genai.configure(api_key=GEMINI_API_KEY)
        logger.info(f"[GeminiValidator] Configured with model: {GEMINI_MODEL}")
    else:
        logger.warning("[GeminiValidator] No GEMINI_API_KEY - will use fallback")
except ImportError:
    genai = None
    logger.warning("[GeminiValidator] google-generativeai not installed - will use fallback")


# Try to import news fetching
try:
    from data.news import get_news_sentiment, fetch_recent_headlines
except Exception:
    async def get_news_sentiment(asset: str):
        return 0.0
    
    async def fetch_recent_headlines(asset: str, limit: int = 5) -> List[Dict[str, Any]]:
        return []


async def gemini_confluence_check(
    signal: Dict[str, Any],
    live_news_headlines: Optional[List[Dict[str, Any]]] = None
) -> bool:
    """
    Ask Gemini 1.5 Pro to act as a Chief Risk Officer.
    
    This function acts as a fundamental risk gate. It evaluates:
    - The technical signal (direction, entry, SL, TP)
    - ML confidence probability
    - Recent fundamental news
    
    Returns True if the trade makes fundamental sense.
    Returns False if it should be vetoed due to fundamental risk.
    
    Args:
        signal: The signal dict with asset, direction, entry, etc.
        live_news_headlines: Optional list of recent news headlines.
                           If None, will fetch automatically.
    
    Returns:
        True if approved, False if vetoed.
    """
    # Check if Gemini is available
    if not GEMINI_API_KEY or genai is None:
        logger.debug("[GeminiValidator] No API key - defaulting to APPROVE")
        return True
    
    try:
        # Fetch news headlines if not provided
        if live_news_headlines is None:
            try:
                asset = signal.get('asset', '')
                live_news_headlines = await fetch_recent_headlines(asset, limit=5)
            except Exception as e:
                logger.debug(f"[GeminiValidator] Failed to fetch news: {e}")
                live_news_headlines = []
        
        # Format news headlines for prompt
        news_text = ""
        if live_news_headlines:
            headlines = []
            for item in live_news_headlines:
                title = item.get('title', item.get('headline', ''))
                if title:
                    headlines.append(f"- {title}")
            news_text = "\n".join(headlines) if headlines else "No recent news."
        else:
            news_text = "No recent news available."
        
        # Build the prompt
        asset = signal.get('asset', 'UNKNOWN')
        direction = signal.get('direction', 'long').upper()
        entry = signal.get('entry', 0)
        ml_prob = signal.get('ml_probability', 0)
        ml_prob_pct = float(ml_prob or 0) * 100 if ml_prob else 0
        
        # Format stop loss and take profit
        sl = signal.get('stop_loss') or signal.get('stop', 'N/A')
        tp = signal.get('take_profit') or signal.get('targets', 'N/A')
        if isinstance(tp, list):
            tp = ", ".join([str(x) for x in tp[:3]])
        
        prompt = f"""You are an institutional Chief Risk Officer with 20 years of experience in macro trading.

Our algorithmic engine wants to take a {direction} position on {asset} at entry price {entry}.
The ML Engine confidence is {ml_prob_pct:.1f}%.
Stop Loss: {sl}
Take Profit: {tp}

Recent fundamental news headlines:
{news_text}

Analyze the trade considering:
1. Is this a "crowded trade" that could reverse suddenly?
2. Does the news suggest macroeconomic headwinds?
3. Is this a "late entry" after a big move that might reverse?
4. Are we near a major resistance/support level that could be tested?

Based on the technicals and fundamentals, is this trade fundamentally dangerous right now?

Reply ONLY with one of these exact responses:
- "APPROVE" - if the trade is fundamentally sound
- "VETO" - if there are serious fundamental concerns

Do not explain. Just reply with APPROVE or VETO."""
        
        # Call Gemini
        model = genai.GenerativeModel(GEMINI_MODEL)
        
        response = await model.generate_content_async(prompt)
        
        decision = response.text.strip().upper()
        
        if "VETO" in decision:
            logger.warning(
                f"🛑 GEMINI VETO: AI rejected {asset} {direction} "
                f"at {entry} due to fundamental risk. ML confidence: {ml_prob_pct:.1f}%"
            )
            return False
        
        if "APPROVE" in decision:
            logger.info(
                f"✅ GEMINI APPROVE: {asset} {direction} approved. "
                f"ML confidence: {ml_prob_pct:.1f}%"
            )
        
        # Default to approve for ambiguous responses
        return True
        
    except Exception as e:
        logger.error(f"[GeminiValidator] API failed: {e}")
        # If Gemini is down, trust the math engine and allow the trade
        return True


async def gemini_risk_review(
    signal: Dict[str, Any],
    market_context: Optional[Dict[str, Any]] = None
) -> Tuple[bool, float, str]:
    """
    Get a more detailed risk review from Gemini.
    
    Returns approval, risk score (0-10), and reasoning.
    
    Args:
        signal: The signal dict.
        market_context: Optional market data for context.
    
    Returns:
        Tuple of (approved, risk_score, reasoning)
    """
    if not GEMINI_API_KEY or genai is None:
        return True, 5.0, "No API key - using default"
    
    try:
        asset = signal.get('asset', 'UNKNOWN')
        direction = signal.get('direction', 'long').upper()
        entry = signal.get('entry', 0)
        ml_prob = float(signal.get('ml_probability', 0) or 0) * 100
        
        # Build enhanced prompt
        prompt = f"""Analyze this trade for risk. Rate 1-10 (10 = highest risk).

Asset: {asset}
Direction: {direction}
Entry: {entry}
ML Confidence: {ml_prob:.1f}%

Consider:
- Macro conditions (Fed, inflation, geopolitics)
- Technical setup quality
- Risk/reward ratio
- Current market regime

Reply in format:
RATE: [1-10]
REASON: [brief reason]
DECISION: [APPROVE/VETO]"""

        model = genai.GenerativeModel(GEMINI_MODEL)
        response = await model.generate_content_async(prompt)
        
        text = response.text.strip()
        
        # Parse response
        risk_score = 5.0
        approved = True
        reasoning = "Reviewed by Gemini"
        
        for line in text.split('\n'):
            if line.startswith('RATE:'):
                try:
                    risk_score = float(line.split(':')[1].strip())
                except:
                    pass
            elif line.startswith('REASON:'):
                reasoning = line.split(':', 1)[1].strip()
            elif line.startswith('DECISION:'):
                decision = line.split(':', 1)[1].strip().upper()
                approved = "APPROVE" in decision
        
        return approved, risk_score, reasoning
        
    except Exception as e:
        logger.error(f"[GeminiValidator] Risk review failed: {e}")
        return True, 5.0, f"Review failed: {e}"


# Quick check without news (for simpler integration)
async def quick_approve(signal: Dict[str, Any]) -> bool:
    """
    Quick approval without full news context.
    
    Use this for simpler integration where you don't have live news.
    The AI will still evaluate the technical setup.
    """
    return await gemini_confluence_check(signal, live_news_headlines=None)


async def gemini_final_veto(signal_data: dict, market_context: str) -> bool:
    """
    Acts as the final human-like filter (Agentic Chief Risk Officer).
    
    This function is designed to act as the final "CRO" check before a signal
    is dispatched. It looks for "Liquidity Traps" or "Inducement"
    patterns that might indicate a retail trap.
    
    Args:
        signal_data: Dict containing the signal details with keys:
                   - direction: 'long' or 'short'
                   - asset: asset symbol
                   - entry_price: entry price
        market_context: String describing market context (e.g., "DXY is pumping, crypto might dump")
    
    Returns:
        True to APPROVE the trade, False to VETO it.
    """
    # Check if Gemini is available
    if not GEMINI_API_KEY or genai is None:
        logger.debug("[GeminiCRO] No API key - defaulting to APPROVE")
        return True
    
    try:
        # Build the signal details - handle both 'entry' and 'entry_price' keys
        direction = signal_data.get('direction', 'long').upper()
        asset = signal_data.get('asset', 'UNKNOWN')
        entry = signal_data.get('entry_price', signal_data.get('entry', 0))
        
        # Build the prompt for institutional risk analysis
        prompt = f"""
SYSTEM: Institutional Risk Manager.
TRADE: {direction} {asset} @ {entry}
CONTEXT: {market_context}

TASK: Look for "Liquidity Traps" or "Inducement". 
If the technicals look like a 'retail trap', respond 'VETO'. 
Otherwise, respond 'PROCEED'.

Response must be one word only.
"""
        # Call Gemini
        model = genai.GenerativeModel(GEMINI_MODEL)
        
        response = await model.generate_content_async(prompt)
        
        decision = response.text.strip().upper()
        
        if "VETO" in decision:
            logger.warning(
                f"🛑 GEMINI CRO VETO: {asset} {direction} vetoed. "
                f"Context: {market_context}"
            )
            return False
        
        logger.info(f"✅ GEMINI CRO APPROVE: {asset} {direction} approved")
        return True
        
    except Exception as e:
        logger.error(f"[GeminiCRO] API failed: {e}")
        # If Gemini is down, default to approve so engine doesn't stall
        return True


# Example integration code (commented out):
"""
# INTEGRATION EXAMPLE - Add to engine/core.py pipeline:

# Right before you dispatch to MT5 and Telegram:
try:
    from services.gemini_ml import gemini_confluence_check
    
    # 1. Math/Risk Gates passed...
    # 2. Correlation passed...
    # 3. News Killswitch passed...
    # 4. Final AI Confluence Check:
    latest_news = await fetch_recent_headlines(signal['asset'])
    gemini_approved = await gemini_confluence_check(signal, latest_news)
    
    if not gemini_approved:
        logger.warning(f"[engine] GEMINI VETO blocked {signal['asset']}")
        pipeline_stats["skipped_gemini_veto"] += 1
        continue
except Exception as e:
    logger.debug(f"[engine] Gemini check failed: {e}")
    # Default to allowing if check fails
    pass
"""


if __name__ == "__main__":
    # Quick test
    import asyncio
    
    async def test():
        print("Testing Gemini Agentic Validator...")
        
        test_signal = {
            'asset': 'BTCUSDT',
            'direction': 'long',
            'entry': 45000,
            'stop_loss': 44000,
            'take_profit': 48000,
            'ml_probability': 0.72,
        }
        
        result = await gemini_confluence_check(test_signal, [])
        print(f"Test result: {'APPROVED' if result else 'VETOED'}")
        
        print("Done!")
    
    asyncio.run(test())
