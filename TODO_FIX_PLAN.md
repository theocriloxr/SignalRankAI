# FIX PLAN - SignalRankAI Bugs

## Bugs to Fix:

### 1. Duplicate Trade Bug (Already Fixed in core.py)
- Location: engine/core.py lines 1845-1870
- Fix: Check for active trades before opening new ones
- Status: ✅ ALREADY IMPLEMENTED

### 2. API Rate Limits (HTTP 429) - Already Fixed in fetcher.py
- Location: data/fetcher.py lines 10-35
- Fix: Macro data caching with 1-hour TTL
- Status: ✅ ALREADY IMPLEMENTED

### 3. Missing Database Column
- Location: Railway PostgreSQL
- SQL to run:
```sql
ALTER TABLE signal_deliveries ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
```

### 4. Stats Import Mismatch
- Status: ✅ ALREADY CORRECT (core.py imports from engine.stats_manager)

### 5. Missing Veto Counters - NEED TO ADD
- Location: engine/core.py
- Need to add stats increments at rejection gates:
  - ML rejections (around line 1300-1330)
  - Score rejections (around line 1550-1600)
  - Squeeze/Microstructure rejections

## Execution Steps:

Step 1: Add stats.vetoed_ml counter at ML rejections
Step 2: Add stats.vetoed_score counter at score rejections  
Step 3: Add stats.vetoed_squeeze counter at microstructure rejections
Step 4: Run SQL for missing created_at column
