import requests
import os
from datetime import datetime, timedelta

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
