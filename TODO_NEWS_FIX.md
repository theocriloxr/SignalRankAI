# TODO: News Feature Implementation - SignalRankAI

## Phase 1: Create News Sync Worker ✅
- [x] Analyze existing files (news.py, economic_calendar.py, news_filter.py, gemini_ml.py)
- [ ] Create worker/news_sync_worker.py - Background worker to sync economic events to DB
- [ ] Add DB persistence for economic_events table

## Phase 2: Add News Sync to Startup ✅
- [ ] Modify railway_main.py - Add asyncio.create_task(sync_news_periodically())  
- [ ] Modify worker/worker.py - Import news sync worker
- [ ] Ensure economic_events table gets populated on startup

## Phase 3: Verify Integration ✅
- [ ] Verify engine/core.py already calls is_no_trade_zone_sync
- [ ] Verify news_sentiment is stored with signals
- [ ] Confirm news filter blocks trades during high-impact events

## Phase 4: Volatility Buffer (Improvement) ⬜
- [ ] Add position size reduction during high-impact events
- [ ] Add SL widening during volatile periods

## Phase 5: Gemini Integration ⬜
- [ ] Ensure Gemini gets news headlines for sentiment analysis
- [ ] Allow AI to veto trades during conflicting news

## Current Status:
- ✅ data/news.py EXISTS - Fetches news headlines
- ✅ services/economic_calendar.py EXISTS - Fetches calendar from Finnhub
- ✅ engine/news_filter.py EXISTS - News killswitch  
- ✅ services/gemini_ml.py EXISTS - AI sentiment
- ✅ db/models.py HAS EconomicEvent table
- ✅ engine/core.py ALREADY calls is_no_trade_zone_sync in pipeline
- ❌ No worker syncs economic events to DB table (table is empty)
- ❌ No news sync task in startup
