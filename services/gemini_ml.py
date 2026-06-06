"""
Gemini Agentic Trade Validator

Uses Gemini 1.5 Pro as a Chief Risk Officer to validate trades before execution.
Acts as a final AI confluence check to veto trades that are fundamentally dangerous.
"""

import os
import logging
from typing import Dict, List, Optional, Any

logger = logging.getLogger("GeminiValidator")

# Configure Gemini API
try:
    import google.generativeai as genai
    
    # Configure with API key from environment
    api_key = os.getenv("GEMINI_API_KEY")
    if api_key:
        genai.configure(api_key=api_key)
    else:
        logger.warning("GEMINI_API_KEY not set - Gemini validator will be disabled")
except ImportError:
    genai = None
    logger.warning("google-generativeai not installed - Gemini validator will be disabled")


async def fetch_recent_headlines(asset: str, limit: int = 5) -> List[str]:
    """
    Fetch recent news headlines for an asset.
    
    Args:
        asset: Asset symbol (e.g., 'BTCUSDT', 'EURUSD')
        limit: Maximum number of headlines to return
        
    Returns:
        List of headline strings
    """
    headlines: List[str] = []
    
    try:
        # Try to get news from data providers
        from data.news import get_latest_news
        news_items = await get_latest_news(asset=asset, limit=limit)
        
        for item in news_items:
            title = item.get('title', '')
            if title:
                headlines.append(title)
                
    except Exception as e:
        logger.debug(f"Failed to fetch headlines for {asset}: {e}")
    
    # Fallback to empty list if nothing found
    return headlines


async def gemini_confluence_check(
    signal: Dict[str, Any],
    live_news_headlines: List[str]
) -> bool:
    """
    Asks Gemini 1.5 Pro to act as a Chief Risk Officer.
    
    This function validates that a trade makes fundamental sense by checking
    against recent news and macroeconomic context. If Gemini identifies a 
    fundamental red flag, it vetoes the trade.
    
    Args:
        signal: Signal dictionary with 'asset', 'direction', 'entry_price', 'ml_probability'
        live_news_headlines: List of recent news headlines for the asset
        
    Returns:
        True if trade is approved, False if vetoed
    """
    # Check if Gemini is configured
    if genai is None:
        logger.debug("Gemini not available, defaulting to APPROVE")
        return True
    
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        logger.debug("GEMINI_API_KEY not set, defaulting to APPROVE")
        return True
    
    try:
        model = genai.GenerativeModel('gemini-1.5-pro')
        
        # Build the prompt
        asset = signal.get('asset', 'UNKNOWN')
        direction = signal.get('direction', 'UNKNOWN')
        entry = signal.get('entry_price', signal.get('entry', 0))
        ml_prob = signal.get('ml_probability', signal.get('ml_prob', 0.5))
        
        # Format news for the prompt
        news_text = "No recent news available"
        if live_news_headlines:
            news_text = "\n".join(f"- {h}" for h in live_news_headlines[:5])
        
        prompt = f"""You are an institutional Chief Risk Officer.
Our algorithmic engine wants to take a {direction} position on {asset} at {entry}.
The ML Engine confidence is {ml_prob * 100:.1f}%.

Recent fundamental news headlines:
{news_text}

Based on the news and asset class, is this trade fundamentally dangerous right now?
Reply ONLY with 'APPROVE' or 'VETO'."""
        
        # Generate response
        response = await model.generate_content_async(prompt)
        decision = response.text.strip().upper()
        
        if "VETO" in decision:
            logger.warning(
                f"🛑 GEMINI VETO: AI rejected {asset} {direction} "
                f"due to fundamental risk. Reason: {response.text}"
            )
            return False
        
        logger.info(f"✅ GEMINI APPROVE: {asset} {direction} passed fundamental check")
        return True
        
    except Exception as e:
        logger.error(f"Gemini API failed: {e}. Defaulting to APPROVE (fail-safe).")
        return True


async def validate_signal(signal: Dict[str, Any]) -> bool:
    """
    Convenience function to validate a signal with Gemini.
    
    Fetches headlines and runs confluence check.
    
    Args:
        signal: Signal dictionary
        
    Returns:
        True if approved, False if vetoed
    """
    asset = signal.get('asset', '')
    
    # Try to fetch headlines
    try:
        headlines = await fetch_recent_headlines(asset)
    except Exception:
        headlines = []
    
    # Run Gemini check
    return await gemini_confluence_check(signal, headlines)


# Global instance for easy import
gemini_validator = gemini_confluence_check
