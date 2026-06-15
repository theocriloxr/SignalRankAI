"""
Gemini Agentic Trade Validator - AI-Powered Fundamental Risk Check

This module upgrades Gemini from a simple chatbot into an Agentic Co-Pilot.
Instead of just analyzing on command, it integrates directly into the algorithmic trading loop.

Before a signal is officially saved and sent to users, the engine asks Gemini to:
1. Read the live chart data and fundamental news
2. Act as a Chief Risk Officer
3. Veto the trade if it spots a macroeconomic red flag

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

# Setup Client (New SDK: google-genai)
client = None
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
MODEL_ID = os.getenv("GEMINI_MODEL", "gemini-2.0-flash").strip()

# Try to import google.genai (new SDK), fallback gracefully
try:
    from google import genai
    
    if GEMINI_API_KEY:
        client = genai.Client(api_key=GEMINI_API_KEY)
        logger.info(f"[GeminiValidator] Configured with model: {MODEL_ID}")
    else:
        logger.warning("[GeminiValidator] No GEMINI_API_KEY - will use fallback")
except ImportError:
    client = None
    logger.warning("[GeminiValidator] google-genai not installed - will use fallback")


# Try to import news fetching
try:
    from data.news import get_news_sentiment as _fetch_news_sentiment, fetch_news_headlines
except Exception:
    async def _fetch_news_sentiment(asset: str):
        return 0.0
    
    async def fetch_news_headlines(asset: str, limit: int = 5) -> List[Dict[str, Any]]:
        return []


async def get_news_sentiment(asset: str, headlines: list) -> str:
    """
    Analyzes news headlines using Gemini to determine sentiment direction.
    
    Args:
        asset: The asset symbol to check (e.g., "BTCUSDT", "EURUSD")
        headlines: List of news headlines (strings)
    
    Returns:
        'BULLISH', 'BEARISH', or 'NEUTRAL'
    """
    if not GEMINI_API_KEY or client is None:
        # Fallback: return NEUTRAL when Gemini unavailable
        return "NEUTRAL"
    
    if not headlines:
        return "NEUTRAL"
    
    try:
        # Format headlines for prompt
        headlines_text = "\n".join([f"- {h}" for h in headlines[:10]])
        
        prompt = f"""Analyze these news headlines for {asset} and determine the market sentiment.

Headlines:
{headlines_text}

Reply ONLY with one of these exact words:
- BULLISH (if news is positive/optimistic for price going up)
- BEARISH (if news is negative/pessimistic for price going down)
- NEUTRAL (if news is mixed or neutral)

Do not explain. Just reply with one word."""
        
        # New SDK: client.models.generate_content()
        response = client.models.generate_content(
            model=MODEL_ID,
            contents=prompt
        )
        
        decision = response.text.strip().upper()
        
        if "BULLISH" in decision:
            return "BULLISH"
        elif "BEARISH" in decision:
            return "BEARISH"
        else:
            return "NEUTRAL"
            
    except Exception as e:
        logger.error(f"[GeminiValidator] get_news_sentiment failed: {e}")
        return "NEUTRAL"


async def gemini_confluence_check_with_tech_context(
    signal: Dict[str, Any],
    news_headlines: list,
    tech_context: Dict[str, Any]
) -> bool:
    """
    Gemini Chief Risk Officer (CRO) with Chain-of-Thought reasoning.
    
    This upgraded version feeds Gemini technical context (RSI, Trend, ATR) so it can
    spot "Overbought" retail traps before they happen.
    
    Args:
        signal: Signal dict with asset, direction, etc.
        news_headlines: List of news headline strings
        tech_context: Dict with 'rsi', 'trend', 'atr' keys
    
    Returns:
        True if APPROVED, False if VETOED
    """
    if not GEMINI_API_KEY or client is None:
        return True
    
    try:
        asset = signal.get('asset', 'UNKNOWN')
        direction = signal.get('direction', 'long').upper()
        
        # Format news headlines
        headlines_text = ""
        if news_headlines:
            if news_headlines and isinstance(news_headlines[0], str):
                headlines_text = "\n".join([f"- {h}" for h in news_headlines[:10]])
            else:
                headlines_text = "\n".join([f"- {h.get('title', h.get('headline', ''))}" for h in news_headlines[:10]])
        else:
            headlines_text = "No recent news."
        
        # Build technical context
        rsi = tech_context.get('rsi', 'N/A')
        trend = tech_context.get('trend', 'N/A')
        atr = tech_context.get('atr', 'N/A')
        
        # Chain-of-Thought prompt
        prompt = f"""ROLE: Institutional Chief Risk Officer (CRO).
ASSET: {asset} | DIRECTION: {direction}

MARKET PULSE:
- RSI(14): {rsi}
- Trend: {trend} (EMA 200)
- ATR (Volatility): {atr}

HEADLINES:
{headlines_text}

TASK: Perform a Confluence Audit. 
1. Does the news conflict with the technical direction?
2. Is the RSI indicating a 'Retail Trap' (e.g. Longing into 80+ RSI)?
3. Is the volatility too high for a safe entry?

THOUGHT PROCESS: (Briefly explain your reasoning)
FINAL DECISION: [APPROVE] or [VETO]"""

        # New SDK call
        response = client.models.generate_content(
            model=MODEL_ID,
            contents=prompt
        )
        
        decision = response.text.strip().upper()
        
        if "VETO" in decision:
            logger.warning(
                f"🛑 GEMINI CRO VETO: {asset} {direction} rejected. "
                f"RSI={rsi}, Trend={trend}, ATR={atr}"
            )
            return False
        
        logger.info(f"✅ GEMINI CRO APPROVE: {asset} {direction} approved")
        return True
        
    except Exception as e:
        logger.error(f"[GeminiValidator] CRO check failed: {e}")
        return True  # Default to approve if AI fails


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
    if not GEMINI_API_KEY or client is None:
        logger.debug("[GeminiValidator] No API key - defaulting to APPROVE")
        return True
    
    try:
        # Fetch news headlines if not provided
        if live_news_headlines is None:
            try:
                asset = signal.get('asset', '')
                live_news_headlines = await fetch_news_headlines(asset, limit=5)
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
        
        # New SDK call
        response = client.models.generate_content(
            model=MODEL_ID,
            contents=prompt
        )
        
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
    if not GEMINI_API_KEY or client is None:
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

        # New SDK call
        response = client.models.generate_content(
            model=MODEL_ID,
            contents=prompt
        )
        
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


async def run_gemini_review_pipeline(trigger: str, scope: str = "weekly") -> Dict[str, Any]:
    """
    Run a comprehensive Gemini review pipeline for automated analytics.
    
    This collects DB aggregates and uses Gemini to analyze cycle performance,
    identifying patterns in rejected signals and potential improvements.
    
    Args:
        trigger: Identifier for what triggered this review (e.g., "automated_cycle_20")
        scope: Time scope for analysis (e.g., "daily", "weekly", "monthly")
    
    Returns:
        Dict with analysis results including ok status and insights
    """
    if not GEMINI_API_KEY or client is None:
        return {"ok": False, "error": "GEMINI_API_KEY not configured"}
    
    # FIX: Use async session generator instead of sync SessionLocal
    from db.session import get_session
    from db.models import Signal, Outcome, MLRejectedSignal, MLShadowPrediction
    
    try:
        async with get_session() as db_session:
            # Collect aggregates based on scope
            from datetime import timedelta
            from utils.timeutils import now_utc_naive
            
            cutoff = now_utc_naive()
            if scope == "daily":
                cutoff = cutoff - timedelta(days=1)
            elif scope == "weekly":
                cutoff = cutoff - timedelta(days=7)
            elif scope == "monthly":
                cutoff = cutoff - timedelta(days=30)
            else:
                cutoff = cutoff - timedelta(days=7)
            
            # Query signal counts
            signals_generated = 0
            signals_stored = 0
            ml_rejected_count = 0
            outcomes_count = 0
            wins = 0
            losses = 0
            
            try:
                # Count generated signals
                from sqlalchemy import select, func
                signals_generated = await db_session.scalar(
                    select(func.count(Signal.signal_id)).where(Signal.created_at >= cutoff)
                ) or 0
                
                # Count stored signals (status='issued' or similar)
                signals_stored = await db_session.scalar(
                    select(func.count(Signal.signal_id)).where(
                        Signal.created_at >= cutoff,
                        Signal.status == "issued"
                    )
                ) or 0
                
                # Count ML rejected signals
                ml_rejected_count = await db_session.scalar(
                    select(func.count(MLRejectedSignal.id)).where(
                        MLRejectedSignal.created_at >= cutoff
                    )
                ) or 0
                
                # Count outcomes with results
                outcomes_count = await db_session.scalar(
                    select(func.count(Outcome.id)).where(
                        Outcome.closed_at >= cutoff,
                        Outcome.status.isnot(None)
                    )
                ) or 0
                
                # Count wins and losses
                wins = await db_session.scalar(
                    select(func.count(Outcome.id)).where(
                        Outcome.closed_at >= cutoff,
                        Outcome.status == "win"
                    )
                ) or 0
                
                losses = await db_session.scalar(
                    select(func.count(Outcome.id)).where(
                        Outcome.closed_at >= cutoff,
                        Outcome.status.in_(["loss", "timeout"])
                    )
                ) or 0
            except Exception as e:
                logger.warning(f"[GeminiValidator] DB query failed: {e}")
            
            # Get recent ML rejection reasons
            rejection_reasons = []
            try:
                from sqlalchemy import select
                rejected_query = await db_session.execute(
                    select(MLRejectedSignal.rejection_reason, MLRejectedSignal.asset)
                    .order_by(MLRejectedSignal.created_at.desc())
                    .limit(10)
                )
                for row in rejected_query:
                    rejection_reasons.append(f"{row[1]}: {row[0]}")
            except Exception as e:
                logger.debug(f"[GeminiValidator] Could not fetch rejection reasons: {e}")
            
            # Build the review prompt
            win_rate = (wins / outcomes_count * 100) if outcomes_count > 0 else 0
            
            prompt = f"""You are an Institutional Trading Analyst reviewing cycle performance.

TRIGGER: {trigger}
SCOPE: {scope} (cutoff: {cutoff.isoformat()})

PERFORMANCE METRICS:
- Signals Generated: {signals_generated}
- Signals Stored (issued): {signals_stored}
- ML Rejected (before storage): {ml_rejected_count}
- Outcomes Tracked: {outcomes_count}
- Wins: {wins}
- Losses: {losses}
- Win Rate: {win_rate:.1f}%

RECENT ML REJECTION REASONS:
{chr(10).join(rejection_reasons) if rejection_reasons else "No recent rejections recorded."}

TASK: Analyze these metrics and provide:
1. A brief assessment of how the ML model is performing
2. Any patterns you notice in the rejections
3. Suggestions for improving signal quality

Respond in this format:
ASSESSMENT: [1-2 sentence summary]
PATTERNS: [What you observe in the data]
RECOMMENDATIONS: [Specific suggestions]
"""
            
            # Call Gemini
            try:
                response = client.models.generate_content(
                    model=MODEL_ID,
                    contents=prompt
                )
                
                analysis = response.text.strip()
                
                return {
                    "ok": True,
                    "trigger": trigger,
                    "scope": scope,
                    "metrics": {
                        "signals_generated": signals_generated,
                        "signals_stored": signals_stored,
                        "ml_rejected": ml_rejected_count,
                        "outcomes": outcomes_count,
                        "wins": wins,
                        "losses": losses,
                        "win_rate": win_rate,
                    },
                    "analysis": analysis,
                }
            except Exception as e:
                logger.error(f"[GeminiValidator] Pipeline API call failed: {e}")
                return {
                    "ok": False,
                    "error": f"API call failed: {e}",
                    "metrics": {
                        "signals_generated": signals_generated,
                        "signals_stored": signals_stored,
                        "ml_rejected": ml_rejected_count,
                    }
                }
                
    except Exception as e:
        logger.exception("[GeminiValidator] Pipeline failed: %s", e)
        return {"ok": False, "error": str(e)}


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
    if not GEMINI_API_KEY or client is None:
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
        # New SDK call
        response = client.models.generate_content(
            model=MODEL_ID,
            contents=prompt
        )
        
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
    latest_news = await fetch_news_headlines(signal['asset'])
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


async def audit_recent(limit: int = 50) -> Dict[str, Any]:
    """
    Admin-only: quick audit of recent losses and rejections.
    
    Args:
        limit: Number of recent items to fetch (default 50)
    
    Returns:
        Dict with ok status, recent_losses, recent_rejections
    """
    if not GEMINI_API_KEY or client is None:
        return {"ok": False, "error": "GEMINI_API_KEY not configured"}
    
    try:
        from db.session import get_session
        from db.models import Outcome, MLRejectedSignal
        from sqlalchemy import select
        from datetime import timedelta
        from utils.timeutils import now_utc_naive
        
        cutoff = now_utc_naive() - timedelta(days=7)
        
        recent_losses = []
        recent_rejections = []
        
        async with get_session() as session:
            # Get recent losses (status = 'sl')
            loss_query = await session.execute(
                select(Outcome)
                .where(
                    Outcome.status == "sl",
                    Outcome.closed_at >= cutoff
                )
                .order_by(Outcome.closed_at.desc())
                .limit(limit)
            )
            loss_rows = loss_query.scalars().all()
            for row in loss_rows:
                recent_losses.append({
                    "signal_id": row.signal_id,
                    "status": row.status,
                    "r_multiple": row.r_multiple,
                    "closed_at": str(row.closed_at) if row.closed_at else None,
                })
            
            # Get recent ML rejections
            reject_query = await session.execute(
                select(MLRejectedSignal)
                .order_by(MLRejectedSignal.created_at.desc())
                .limit(limit)
            )
            reject_rows = reject_query.scalars().all()
            for row in reject_rows:
                recent_rejections.append({
                    "signal_id": getattr(row, 'signal_id', None),
                    "asset": row.asset,
                    "rejection_reason": row.rejection_reason,
                    "created_at": str(row.created_at) if row.created_at else None,
                })
            
            await session.commit()
        
        return {
            "ok": True,
            "recent_losses": recent_losses,
            "recent_rejections": recent_rejections,
            "losses_count": len(recent_losses),
            "rejections_count": len(recent_rejections),
        }
        
    except Exception as e:
        logger.error(f"[GeminiValidator] audit_recent failed: {e}")
        return {"ok": False, "error": str(e)}


async def analyze_asset(asset: str, limit: int = 20) -> Dict[str, Any]:
    """
    Admin-only: analyze a single asset with recent signals and rejections.
    
    Args:
        asset: Asset symbol to analyze (e.g., "BTCUSDT")
        limit: Number of recent items to fetch
    
    Returns:
        Dict with analysis results
    """
    if not GEMINI_API_KEY or client is None:
        return {"ok": False, "error": "GEMINI_API_KEY not configured"}
    
    try:
        from db.session import get_session
        from db.models import Signal, MLRejectedSignal
        from sqlalchemy import select
        from datetime import timedelta
        from utils.timeutils import now_utc_naive
        
        cutoff = now_utc_naive() - timedelta(days=30)
        
        recent_signals = []
        recent_rejections = []
        
        async with get_session() as session:
            # Get recent signals for this asset
            signal_query = await session.execute(
                select(Signal)
                .where(
                    Signal.asset == asset,
                    Signal.created_at >= cutoff
                )
                .order_by(Signal.created_at.desc())
                .limit(limit)
            )
            signal_rows = signal_query.scalars().all()
            for row in signal_rows:
                recent_signals.append({
                    "signal_id": row.signal_id,
                    "direction": row.direction,
                    "entry": row.entry,
                    "score": row.score,
                    "created_at": str(row.created_at) if row.created_at else None,
                })
            
            # Get recent rejections for this asset
            reject_query = await session.execute(
                select(MLRejectedSignal)
                .where(
                    MLRejectedSignal.asset == asset,
                    MLRejectedSignal.created_at >= cutoff
                )
                .order_by(MLRejectedSignal.created_at.desc())
                .limit(limit)
            )
            reject_rows = reject_query.scalars().all()
            for row in reject_rows:
                recent_rejections.append({
                    "rejection_reason": row.rejection_reason,
                    "created_at": str(row.created_at) if row.created_at else None,
                })
            
            await session.commit()
        
        return {
            "ok": True,
            "asset": asset,
            "recent_signals": recent_signals,
            "recent_rejections": recent_rejections,
            "signals_count": len(recent_signals),
            "rejections_count": len(recent_rejections),
        }
        
    except Exception as e:
        logger.error(f"[GeminiValidator] analyze_asset failed: {e}")
        return {"ok": False, "error": str(e)}


async def predict_candidate(candidate: Dict[str, Any]) -> Dict[str, Any]:
    """
    Admin-only: predict/assess a candidate signal.
    
    Args:
        candidate: Dict with asset, timeframe, direction, entry
    
    Returns:
        Dict with prediction results
    """
    if not GEMINI_API_KEY or client is None:
        return {"ok": False, "error": "GEMINI_API_KEY not configured"}
    
    try:
        asset = candidate.get("asset", "UNKNOWN")
        direction = candidate.get("direction", "long").upper()
        entry = candidate.get("entry", 0)
        timeframe = candidate.get("timeframe", "1h")
        
        # Check for duplicates in recent signals
        from db.session import get_session
        from db.models import Signal
        from sqlalchemy import select
        from datetime import timedelta
        from utils.timeutils import now_utc_naive
        
        cutoff = now_utc_naive() - timedelta(hours=24)
        is_duplicate = False
        recent_neighbors = []
        
        async with get_session() as session:
            dup_query = await session.execute(
                select(Signal)
                .where(
                    Signal.asset == asset,
                    Signal.direction == direction.lower(),
                    Signal.timeframe == timeframe,
                    Signal.created_at >= cutoff
                )
                .order_by(Signal.created_at.desc())
                .limit(5)
            )
            dup_rows = dup_query.scalars().all()
            if dup_rows:
                is_duplicate = True
                for row in dup_rows:
                    recent_neighbors.append({
                        "signal_id": row.signal_id,
                        "entry": row.entry,
                        "created_at": str(row.created_at) if row.created_at else None,
                    })
            
            await session.commit()
        
        return {
            "ok": True,
            "is_duplicate": is_duplicate,
            "recent_neighbors": recent_neighbors,
            "candidate": candidate,
        }
        
    except Exception as e:
        logger.error(f"[GeminiValidator] predict_candidate failed: {e}")
        return {"ok": False, "error": str(e)}


# Cache for last Gemini review (for gemini_review_command)
_last_gemini_review: Dict[str, Any] = {}


async def get_last_gemini_review() -> Dict[str, Any]:
    """Get the cached last Gemini review result."""
    global _last_gemini_review
    return _last_gemini_review


async def set_last_gemini_review(result: Dict[str, Any]) -> None:
    """Store the last Gemini review result."""
    global _last_gemini_review
    _last_gemini_review = result


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
