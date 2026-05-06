---
title: "Adaptive Learning & Self-Correction System Implementation"
date: "2026-05-06"
status: "Complete"
---

# Adaptive Learning & Self-Correction System for SignalRankAI

## Overview
Implemented a complete outcome-tracking and self-correction loop that:
1. **Captures ALL rejections** (ML, consensus, risk, score, advanced filters)
2. **Labels outcomes** across 5 time windows (5m, 15m, 1h, 4h, 1d) using 3 methods
3. **Triggers adaptive learning** globally at 100 cumulative outcomes (accepted + rejected)
4. **Optimizes thresholds** + retrains ML + gets Gemini confirmation + notifies admin/owner
5. **Available to admin/owner only** for privacy and model improvement

---

## Architecture

### 1. **Unified Rejection Capture** (`engine/signal_deduplicator.py`)

**Source:** All non-issued signals logged via `persist_decision_log()`
```
decision_log(decision="rejected"|"skipped")
  ├─ ML filter rejection
  ├─ Consensus filter rejection  
  ├─ Risk/volatility check rejection
  ├─ Score gate rejection
  ├─ Advanced filter rejection
  └─ Any other "skipped" decision
```

**Signal Snapshot:** Every decision log includes full signal context:
```python
meta = {
    "direction": "long|short",
    "entry": float,
    "stop_loss": float,
    "take_profit": float|list,
    "score": float,
    "ml_probability": float,
    "strategy_name": str,
    "strategy_group": str,
    # ... additional context
}
```

**Backfill Process:**
- `MLRejectionTracker._ingest_non_ml_rejections_from_decision_log()`
- Runs on each `track_rejection_outcomes()` cycle
- Loads decision_log records (past 14 days, configurable) into `ml_rejected_signals`
- Tracks progress via `runtime_state` key: `rejections_backfill_last_decision_id`
- Prevents duplicates and re-processing

---

### 2. **Multi-Window, Multi-Method Outcome Labeling**

**Windows (configurable via `REJECT_OUTCOME_WINDOWS`):**
- 5 minutes
- 15 minutes  
- 1 hour
- 4 hours
- 1 day

Each window evaluated at **close of that window**, using **3 independent methods**:

#### Method 1: **Target Hit** (`_label_target_window`)
- Fetch candles for [signal_time → window_end]
- Check if SL hit, TP hit, both, or neither
- Returns: `"win" | "loss" | "ambiguous" | "no_hit" | "no_data"`

#### Method 2: **Directional** (`_directional_label`)
- Compare entry price vs. close price at window end
- Long: close > entry = win, close < entry = loss
- Short: close < entry = win, close > entry = loss
- Returns: `"win" | "loss" | "flat" | "no_data"`

#### Method 3: **% Move** (`_pct_move_label`)
- Calculate % change: `(close - entry) / entry × 100`
- Threshold: `REJECT_OUTCOME_MOVE_PCT` (default 1%)
- Long: +% ≥ threshold = win, -% ≤ -threshold = loss
- Short: reversed logic
- Returns: `"win" | "loss" | "no_hit" | "no_data"`

**Consensus Across Methods:**
```python
methods = {
    "target_hit": "win",
    "directional": "loss",
    "pct_move": "win"
}
→ label = "win"  # 2 wins > 1 loss
```

**Storage:**
```python
features = {
    "outcome_labels": {
        "5m": "win",
        "15m": "loss",
        "1h": "win",
        "4h": "ambiguous",
        "1d": "win",
        "overall": "win"
    },
    "outcome_methods": {
        "5m": {"target_hit": "win", "directional": "loss", "pct_move": "win", "source_timeframe": "15m"},
        "15m": {...},
        ...
    },
    "outcome_close_prices": {
        "5m": 102.5,
        "15m": 101.8,
        ...
    },
    "outcome_windows_minutes": [5, 15, 60, 240, 1440],
    "evaluation_mode": "close_at_each_window"
}
```

---

### 3. **Global Outcome Tracking Counter**

**Trigger: 100 Total Outcomes Globally**

Maintained in `runtime_state`:
- `adaptive_learning_last_total`: Last batch-processed count
- When `accepted_outcomes + rejected_outcomes >= last_mark + 100`, triggers:

```python
total_accepted = COUNT(*) FROM outcomes WHERE closed_at IS NOT NULL
total_rejected = COUNT(*) FROM ml_rejected_signals WHERE outcome_tracked_at IS NOT NULL
total = total_accepted + total_rejected

if total >= (last_mark + 100):  # Batch of 100
    → Adaptive Learning Pipeline
```

---

### 4. **Adaptive Learning Pipeline (Triggered Every 100 Outcomes)**

Runs atomically when batch threshold hit:

#### Step 1: **Refresh Thresholds** (`engine/threshold_optimizer.py`)
```
analyze_and_adjust(force=True)
  ├─ Query last 7 days of outcomes
  ├─ Calculate: win_rate, avg_R, net_R, signal volume
  ├─ Score performance (win rate vs. 60% target, R vs. 1.5 target)
  ├─ Adjust ml_prob_threshold, min_score_threshold, confluence_min
  ├─ Bounds: ML [0.30, 0.85], Score [0, 100], Confluence [0, 100]
  └─ Save to runtime_state["adaptive_thresholds"]
```

**Thresholds Applied Immediately** to next signal evaluation.

#### Step 2: **Gemini Review** (`services/gemini_ml.py`)
```
run_gemini_review_pipeline(trigger="adaptive_learning_batch", scope="all_time")
  ├─ Aggregate stats: outcomes, wins, losses, rejection reasons
  ├─ Per-signal records (up to 80 from DB)
  ├─ Send to Gemini with prompt:
  │    - Confirm each signal outcome (signal_id, direction, outcome, timestamp)
  │    - Identify patterns (best/worst assets, timeframes, directions)
  │    - Suggest ML features to improve win rate
  │    - Suggest bot features for better execution
  │    - Point out data quality issues
  ├─ Parse Gemini response
  ├─ Extract feature suggestions
  └─ Store in runtime_state["gemini_ml_last_run"]
```

**Gemini Cooldown:**
- On HTTP 429: Cooldown 24h (configurable `GEMINI_COOLDOWN_HOURS`)
- Respects Railway restarts via `runtime_state`

#### Step 3: **ML Retrain** (`ml/train_model.py`)
```
train_main()
  ├─ Load all training data (outcomes + rejected signals)
  ├─ Feature engineering
  ├─ Train model
  ├─ Overwrite model.json
  └─ Log metrics
```

#### Step 4: **News Confirmation** (Optional)
```
For top 3 assets by rejection count:
  get_news_sentiment(asset, lookback_minutes=120)
  → Filter signals where news sentiment opposes direction
  → Log patterns
```

#### Step 5: **Admin/Owner Notification**
```
Telegram message to OWNER_IDS + ADMIN_IDS:
  "Adaptive learning applied immediately. 
   global_outcomes=147 (accepted=80, rejected=67), batch=100.
   thresholds=ml=0.52, score=71.5, confluence=2.5.
   gemini_ok=True. retrain_ok=True. 
   news_hint=BTC:0.85, ETH:-0.42, ADA:0.12"
```

---

## Implementation Details

### File Changes

#### **`engine/core.py`**
- Enhanced `_log_decision()` to persist full signal metadata in decision_log

#### **`engine/signal_deduplicator.py`** (Major)
- **Windows:** Support 5m/15m/1h/4h/1d (parsed from `REJECT_OUTCOME_WINDOWS`)
- **Methods:** Added `_directional_label()`, `_pct_move_label()`, `_window_label_from_methods()`
- **Backfill:** `_ingest_non_ml_rejections_from_decision_log()` converts decision_log → ml_rejected_signals
- **Evaluation:** `_evaluate_window()` runs 3 methods, returns consensus label + methods dict + close price
- **Trigger:** `_run_adaptive_learning_if_due()` checks batch counter, triggers entire pipeline
- **Notifications:** `_notify_admin_owner()` sends Telegram messages

### Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `REJECT_OUTCOME_WINDOWS` | `"5m,15m,1h,4h,1d"` | Time windows for outcome evaluation |
| `REJECT_OUTCOME_MIN_TRACK_AGE_MINUTES` | `5` | Min age before labeling window (avoid early labels) |
| `REJECT_OUTCOME_MOVE_PCT` | `1.0` | % threshold for pct_move method |
| `ADAPTIVE_LEARNING_BATCH_SIZE` | `100` | Trigger adaptive learning every N outcomes |
| `REJECTION_DECISION_LOOKBACK_DAYS` | `14` | Backfill decision_log up to N days old |
| `GEMINI_API_KEY` | (required) | Google Gemini API key |
| `GEMINI_MODEL` | `"gemini-2.0-flash"` | Primary Gemini model |
| `GEMINI_REVIEW_MAX_TOKENS` | `1200` | Max output tokens for review |
| `GEMINI_COOLDOWN_HOURS` | `24` | Cooldown after 429 error |
| `TELEGRAM_BOT_TOKEN` | (required) | Bot token for notifications |
| `OWNER_IDS` / `ADMIN_IDS` | (optional) | Comma-separated Telegram user IDs |

---

## Data Flow

```
Signal Evaluated
  ↓
[Passes all filters?]
  ├─ YES → persist to signals table
  └─ NO → persist_decision_log(decision="rejected|skipped", meta={signal context})
           ↓
           [Every 2-5 minutes, async]
           ↓
           track_rejection_outcomes()
             ├─ Backfill decision_log → ml_rejected_signals
             ├─ For each ml_rejected_signal without outcome_tracked_at:
             │    ├─ Evaluate each window (5m, 15m, 1h, 4h, 1d)
             │    ├─ Run 3 methods per window
             │    ├─ Store outcome_labels + outcome_methods + close_prices
             │    └─ When all windows labeled, mark outcome_tracked_at = NOW
             ├─ Count: total = outcomes + ml_rejected_signals(tracked)
             ├─ If total >= (last_mark + 100):
             │    ├─ Refresh adaptive thresholds (env vars updated immediately)
             │    ├─ Run Gemini review (aggregate + per-signal)
             │    ├─ Retrain ML model
             │    └─ Notify admin/owner with results
             └─ Return tracked count
```

---

## Privacy & Access Control

**Only visible to admin/owner:**
- Rejected signal outcomes
- Adaptive threshold changes
- Gemini review feedback
- Retrain metrics
- Notifications sent via Telegram to configured OWNER_IDS + ADMIN_IDS

**Regular users:** See nothing; system learns silently.

---

## Validation Checklist ✅

- [x] Rejection capture from all sources (ML, consensus, risk, score, advanced)
- [x] Full signal metadata persisted in decision_log
- [x] Multi-window evaluation (5m, 15m, 1h, 4h, 1d)
- [x] Three outcome methods (target_hit, directional, pct_move)
- [x] Consensus across methods
- [x] Backfill from decision_log to ml_rejected_signals
- [x] Global outcome counter (100-outcome trigger)
- [x] Threshold optimizer integration
- [x] Gemini review pipeline
- [x] ML retrain on full dataset
- [x] News sentiment confirmation (optional)
- [x] Admin/owner notification system
- [x] Runtime state persistence for cooldowns & progress

---

## Example: Rejected Signal Outcome Tracking

**Signal rejected at 10:00 UTC:**
```python
DecisionLog {
    decision: "rejected",
    reason: "ml_filter",
    meta: {
        "direction": "long",
        "entry": 100.5,
        "stop_loss": 99.0,
        "take_profit": 105.0,
        "score": 62.5,
        "ml_probability": 0.48
    },
    created_at: 2026-05-06T10:00:00Z
}
```

**Ingested into ml_rejected_signals, outcome evaluation:**

| Window | Window End | Target Hit | Directional | Pct Move (1%) | Consensus | Close Price |
|--------|-----------|-----------|-------------|--------------|-----------|------------|
| 5m | 10:05 | no_hit | win | win | win | 100.8 |
| 15m | 10:15 | win | win | win | win | 101.2 |
| 1h | 11:00 | win | win | win | win | 102.3 |
| 4h | 14:00 | win | loss | loss | loss | 99.8 |
| 1d | next day | ambiguous | ... | ... | ambiguous | 104.5 |

**Overall:** "win" (3 wins, 1 loss, 1 ambiguous → majority wins)

**Stored for Gemini:**
```python
ml_rejected_signals {
    actual_outcome: "win",
    outcome_tracked_at: 2026-05-07T10:00:00Z,
    features: {
        outcome_labels: {
            "5m": "win", "15m": "win", "1h": "win", "4h": "loss", "1d": "ambiguous", "overall": "win"
        },
        outcome_methods: {
            "5m": {target_hit: no_hit, directional: win, pct_move: win},
            ...
        },
        outcome_close_prices: {
            "5m": 100.8, "15m": 101.2, ...
        }
    }
}
```

**100 outcomes later:**
- Gemini analyzes: "This signal was correctly rejected by ML (0.48 prob) but would have won. Consider: (a) signal score was borderline (62.5); (b) ML model may underweight this pattern."
- Thresholds adjusted: ML from 0.55→0.52
- Model retrained on all outcomes
- Admin notified: "Adaptive learning: ml=0.52, wins% ↑2%"

---

## Next Steps (Optional Enhancements)

1. **Per-Asset Learning:** Track outcomes separately per asset, auto-tune per-asset thresholds
2. **Rejection Reason Analysis:** Group rejections by reason, identify which are "too strict"
3. **False Rejection Metrics:** Count "would-have-been-profitable" rejections to measure overfitting
4. **A/B Testing:** Run old vs. new thresholds in parallel (shadow mode)
5. **News Integration:** Fetch historical news to explain outcome patterns

---

## Testing

Run validation:
```bash
python validate_adaptive_learning.py
```

Expected output:
```
✅ Window parsing: [5m, 15m, 1h, 4h, 1d]
✅ Multi-method consensus labeling works
✅ Directional labeling works
✅ Pct move labeling works
✅ Core system validated
```

---

## Support

Contact: Admin/Owner via Telegram
Logs: Check engine logs for `[adaptive_learning]`, `[gemini]`, `[threshold_optimizer]` tags
