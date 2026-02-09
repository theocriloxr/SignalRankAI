import requests
import os
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


def fetch_news_headlines(asset, lookback_minutes=120):
    """
    Fetch recent news headlines for the given asset using NewsAPI (or similar).
    Returns a list of (headline, published_at, sentiment_score) tuples.
    """
    # Example: Use NewsAPI (https://newsapi.org/)
    api_key = os.getenv('NEWSAPI_KEY')
    if not api_key:
        return []
    url = f'https://newsapi.org/v2/everything?q={asset}&language=en&sortBy=publishedAt&pageSize=10&apiKey={api_key}'
    try:
        resp = requests.get(url, timeout=10)
        data = resp.json()
        headlines = []
        for article in data.get('articles', []):
            headline = article.get('title', '')
            published_at = article.get('publishedAt', '')
            # Simple sentiment: +1 if positive, -1 if negative, 0 if neutral
            sentiment = simple_sentiment_score(headline)
            headlines.append((headline, published_at, sentiment))
        return headlines
    except Exception:
        return []

def simple_sentiment_score(text):
    """Very basic sentiment scoring for demonstration."""
    text = text.lower()
    positive = ['surge', 'rally', 'gain', 'rise', 'bull', 'record', 'beat']
    negative = ['fall', 'drop', 'loss', 'bear', 'miss', 'crash', 'plunge']
    score = 0
    for word in positive:
        if word in text:
            score += 1
    for word in negative:
        if word in text:
            score -= 1
    return score

def get_news_sentiment(asset, lookback_minutes=120):
    """
    Aggregate sentiment for recent news headlines for the asset.
    Returns a float: positive (>0), negative (<0), or neutral (0).
    """
    headlines = fetch_news_headlines(asset, lookback_minutes)
    if not headlines:
        return 0.0
    total = sum(s for _, _, s in headlines)
    return total / max(1, len(headlines))


async def check_news_impact_on_active_signals():
    """
    Check if recent news affects any active signals and notify users.
    
    This function:
    1. Gets all active signals
    2. Fetches recent news for each asset
    3. Compares news sentiment against signal direction
    4. Sends alerts to users if news conflicts with their signals
    """
    try:
        from db.session import get_session
        from db.models import Signal, SignalDelivery
        from sqlalchemy import select
        from core.redis_state import state
        from core.tier_constants import ACTIVE_SIGNAL_LOOKBACK_HOURS, STRONG_SENTIMENT_THRESHOLD
        
        # Get active signals from last N hours
        async with get_session() as session:
            cutoff = datetime.utcnow() - timedelta(hours=ACTIVE_SIGNAL_LOOKBACK_HOURS)
            stmt = select(Signal).where(
                Signal.archived == False,
                Signal.created_at >= cutoff
            )
            result = await session.execute(stmt)
            signals = result.scalars().all()
            
            if not signals:
                logger.debug("No active signals to check for news impact")
                return
            
            logger.info(f"Checking news impact on {len(signals)} active signals")
            
            # Group signals by asset
            signals_by_asset = {}
            for sig in signals:
                asset = sig.asset
                if asset not in signals_by_asset:
                    signals_by_asset[asset] = []
                signals_by_asset[asset].append(sig)
            
            # Check news for each asset
            for asset, asset_signals in signals_by_asset.items():
                try:
                    # Fetch recent news (last 2 hours)
                    headlines = fetch_news_headlines(asset, lookback_minutes=120)
                    
                    if not headlines:
                        continue
                    
                    # Get most recent headline with strong sentiment
                    strong_news = [h for h in headlines if abs(h[2]) >= STRONG_SENTIMENT_THRESHOLD]
                    
                    if not strong_news:
                        continue
                    
                    latest_headline, published_at, sentiment = strong_news[0]
                    
                    # Check each signal for this asset
                    for sig in asset_signals:
                        direction = sig.direction.lower()
                        
                        # Check if news conflicts with signal direction
                        conflicts = False
                        if direction == 'long' and sentiment < -1:
                            conflicts = True
                            conflict_type = "bearish news on LONG signal"
                        elif direction == 'short' and sentiment > 1:
                            conflicts = True
                            conflict_type = "bullish news on SHORT signal"
                        
                        if conflicts:
                            logger.info(f"News conflict detected for signal {sig.signal_id[:8]}: {conflict_type}")
                            
                            # Check if we've already notified about this news
                            redis_key = f"news_alert:{sig.signal_id}:{latest_headline[:50]}"
                            already_notified = state.get_sync(redis_key)
                            
                            if already_notified:
                                logger.debug(f"Already notified users about news for signal {sig.signal_id[:8]}")
                                continue
                            
                            # Get users who received this signal
                            stmt = select(SignalDelivery.user_id).where(
                                SignalDelivery.signal_id == sig.signal_id
                            ).distinct()
                            result = await session.execute(stmt)
                            user_ids = [row[0] for row in result]
                            
                            # Get current price
                            try:
                                from engine.price_validator import get_current_price
                                current_price = get_current_price(asset)
                                price_str = f"${current_price:.4f}" if current_price else "N/A"
                            except:
                                price_str = "N/A"
                            
                            # Notify users
                            for user_id in user_ids:
                                try:
                                    await notify_news_alert(
                                        user_id=user_id,
                                        signal=sig,
                                        headline=latest_headline,
                                        sentiment=sentiment,
                                        current_price=price_str
                                    )
                                except Exception as e:
                                    logger.error(f"Failed to send news alert to user {user_id}: {e}")
                            
                            # Mark as notified (expires in 12 hours)
                            state.set_sync(redis_key, "1", ex=43200)
                            logger.info(f"Sent news alerts for signal {sig.signal_id[:8]} to {len(user_ids)} users")
                
                except Exception as e:
                    logger.error(f"Error checking news for asset {asset}: {e}")
    
    except Exception as e:
        logger.error(f"Error in check_news_impact_on_active_signals: {e}", exc_info=True)


async def notify_news_alert(user_id: int, signal, headline: str, sentiment: float, current_price: str):
    """Send a news alert notification to a user."""
    try:
        from signalrank_telegram.bot import send_message_to_user
        
        asset = signal.asset
        direction = signal.direction.upper()
        ref = signal.signal_id[:8]
        
        # Determine sentiment emoji
        if sentiment > 0:
            sentiment_emoji = "📈🟢"
            sentiment_text = "BULLISH"
        else:
            sentiment_emoji = "📉🔴"
            sentiment_text = "BEARISH"
        
        message = (
            f"⚠️ **NEWS ALERT**\n\n"
            f"News may affect your {asset} {direction} signal:\n\n"
            f"{sentiment_emoji} **{sentiment_text} News:**\n"
            f"_{headline}_\n\n"
            f"📊 Signal Ref: `{ref}`\n"
            f"💰 Current Price: {current_price}\n\n"
            f"💡 **Consider reviewing your position**\n"
            f"Use /signal {ref} for details"
        )
        
        await send_message_to_user(user_id, message)
    
    except Exception as e:
        logger.error(f"Failed to send news alert: {e}", exc_info=True)

