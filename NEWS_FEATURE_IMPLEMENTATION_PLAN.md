# News Feature Implementation Plan

## Current State Analysis

### What's Working:
1. `services/economic_calendar.py` - Fetches economic events from Finnhub API ✓
2. `data/news.py` - Basic news sentiment from multiple sources ✓  
3. `engine/news_filter.py` - News killswitch logic exists ✓
4. `db/models.py` - EconomicEvent table defined ✓

### What's Missing:
1. `worker/news_sync_worker.py` NOT started in worker/worker.py
2. `engine/news_filter.py` NOT integrated in engine/core.py pipeline
3. Background sync runs but no one is listening

## Implementation Plan

### Phase 1: Fix Imports & Verify ✓
- [x] Fix Any import in data/providers.py

### Phase 2: Add News Sync to Worker Startup
- [ ] Add news sync background task to worker/worker.py
- [ ] Add news sync to main.py/Railway startup

### Phase 3: Integrate News Filter in Engine
- [ ] Add news killswitch check in engine/core.py pipeline
- [ ] Add is_no_trade_zone check after regime detection

### Phase 4: Database & Testing
- [ ] Verify EconomicEvent table exists
- [ ] Test complete flow

## Changes Required:

### File: worker/worker.py
Add to _register_task section:
```python
_register_task("news_sync", lambda: start_news_sync_worker(), restart_on_failure=True)
```

### File: engine/core.py  
Add in pipeline after regime detection:
```python
# News killswitch gate
try:
    if _is_no_trade_zone_sync(asset, buffer_minutes=60):
        logger.info(f"[engine] no_trade_zone gate: skipping asset={asset}")
        _record_gate_failure(asset, "macro", "no_trade_zone_60m")
        continue
except Exception:
    pass
```

## Recommendations per Task:
1. Volatility Buffer - Increase SL distance when High Impact news
2. Gemini Sentiment - Pass news headlines to Gemini for confirmation
3. Missing Table Handling - Ensure sync task is started
