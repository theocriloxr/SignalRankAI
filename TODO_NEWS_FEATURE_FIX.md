# News Feature Implementation Plan - SignalRankAI

## Problem Statement
The News Confirmation feature is NOT running. The engine fetches price data but never reaches out to a News API. This means:
- `economic_events` table is EMPTY
- No news sync task in startup
- Technical signals (like 85.01 score) are "liquidity traps" during high-impact news events

## Current State Analysis

### Files that EXIST (Good):
1. ✅ `data/news.py` - Fetches news from multiple sources (NewsAPI, CryptoPanic, BraveSearch)
2. ✅ `services/economic_calendar.py` - Fetches economic calendar from Finnhub + fallback events
3. ✅ `engine/news_filter.py` - News killswitch to block trades during high-impact events
4. ✅ `services/gemini_ml.py` - AI-powered sentiment analysis  
5. ✅ `db/models.py` - HAS EconomicEvent table

### What's MISSING:
1. ❌ No background worker to sync economic events to DB
2. ❌ No news sync task in `railway_main.py` startup
3. ❌ `economic_events` table is EMPTY (no data)

## Implementation Plan

### Phase 1: Add Economic Calendar Sync Worker
- Create `worker/news_sync_worker.py` that:
  - Runs every 6 hours (configurable)
  - Fetches economic events from Finnhub
  - Stores in `economic_events` table

### Phase 2: Add News Sync to Railway Startup  
- Add news sync task to `railway_main.py`:
  - `asyncio.create_task(sync_news_periodically())`
  - Start on app startup

### Phase 3: Improve News Filter Integration
- Make sure `engine/news_filter.py` is called in engine pipeline:
  - Already integrated via `is_no_trade_zone_sync` 
  - Add volatility buffer improvements

### Phase 4: Volatility Buffer (Improvement)
- When High Impact news detected:
  - Increase SL distance by 1.5x
  - OR reduce position size automatically

### Phase 5: Gemini Sentiment Integration  
- Send news headlines to Gemini alongside technical data
- Allow AI to veto conflicting trades

## Files to CREATE:
1. `worker/news_sync_worker.py` - Background news sync

## Files to MODIFY:
1. `railway_main.py` - Add news sync task
2. `worker/worker.py` - Import news sync worker

## Next Steps:
1. Create news sync worker
2. Add to startup sequence
3. Test the integration
