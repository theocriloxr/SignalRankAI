# SignalRankAI - Comprehensive System Analysis

## Executive Summary

Based on analysis of the codebase and the provided logs, SignalRankAI is a sophisticated Telegram-based trading signal generation and delivery system deployed on Railway. The system generates signals for:

- **Crypto** (BTC, ETH, SOL, etc.)
- **FX** (USD/JPY, EUR/USD, etc.)
- **Stocks** (AAPL, TSLA, etc.)
- **Commodities** (BRENT, GOLD, SILVER, WTI, etc.)

Signals are delivered to users via Telegram bot with tiered access (FREE/PREMIUM/VIP/OWNER).

**Current Issue**: The logs show `final_signals=0 stored=0` - no signals are being generated despite strategy signals being created (120 signals at consensus stage).

---

## System Architecture

### 1. Monolith Deployment (Railway)
The entire system runs as a monolith via `railway_main.py`:
- **FastAPI** web server (port 8080)
- **APScheduler** for background jobs
- **Telegram Bot** in webhook mode
- **Engine Loop** - signal generation
- **Worker Loop** - outcome tracking

### 2. Run Modes
| Mode | Description |
|------|------------|
| `all` | Full monolith (web+engine+worker+bot) |
| `web` | FastAPI only |
| `worker` | Outcome tracking loop |
| `bot` | Telegram polling |
| `engine` | Signal generation loop (default) |

---

## Signal Pipeline (Engine Core)

The signal generation pipeline in `engine/core.py` runs through multiple stages:

```
1. fetch_market_data → 2. run_strategies → 3. normalize/dedupe
4. consensus_filter → 5. pick_best_direction → 6. compute_fingerprint
7. validate_structure → 8. risk_check → 9. confluence_check
10. ML_filter → 11. score → 12. advanced_filters
13. ultra_quality → 14. calculate_stops → 15. score_gate
16. expectancy_gate → 17. store → 18. deliver
```

### Key Gates That Block Signals

Based on code analysis, here are all gates that can reject signals:

| Gate | Location | Threshold | Rejection Message |
|------|----------|-----------|------------------|
| Duplicate fingerprint | core.py | N/A | `duplicate_fingerprint` |
| Validation structure | signal_validator.py | N/A | `validation:{reason}` |
| Risk check | risk.py | N/A | `risk/volatility` |
| Confluence | core.py | CONFLUENCE_GATE_MIN (default 0) | `confluence {value}%` |
| News conflict | core.py | STRONG_SENTIMENT_THRESHOLD=2 | `news_conflict` |
| ML filter soft | ml/inference.py | ML_PROB_THRESHOLD (default 0.55) | `filtered_by_ml` |
| ML filter hard | core.py | ML_HARD_FILTER_MIN=0.55 | `filtered_by_ml_hard_threshold` |
| Score threshold | core.py | PREMIUM_SCORE_THRESHOLD (default 70) | `score {value} < {threshold}` |
| **Expectancy gate** | **core.py** | **EXPECTANCY_MIN=0.15** | **`low expectancy {value}`** |
| Invalid TP structure | core.py | N/A | `invalid_tp_structure` |
| Confluence direction | core.py | N/A | Signal direction != confluence direction |

---

## The Expectancy Gate Issue

From logs and code analysis, the **EXPECTANCY_MIN=0.15** gate is likely blocking all signals. Here's why:

### Current Logic (engine/core.py ~line 2160):
```python
# Expectancy gate (Phase 3 full impl)
live_exp = float(sig.get('live_expectancy', 0.15))
if live_exp < 0.15:
    sig['rejection_reason'] = f"low expectancy {live_exp:.3f}"
    _log_decision("skipped", sig, reason=sig['rejection_reason'])
    continue
```

### Problem
1. **Default value is 0.15** - signals default to exactly the threshold
2. **No live expectancy data exists yet** for new assets
3. **get_live_expectancy()** queries outcomes from DB but likely returns 0.15 (fail-safe default) for most assets

### How Expectancy Works (engine/expectancy_gate.py):
```python
async def get_live_expectancy(asset, strategy, lookback_hours=168):
    # Query outcomes from last 7 days
    # Calculate: (Win% × AvgWinR) - (Loss% × AvgLossR)
    # If no data: return EXPECTANCY_MIN (0.15)
```

---

## Log Analysis

### Key Log Entries:
```
2026-05-07T13:21:55.737580171Z [inf]  [engine] cycle=1 assets=20 generated_signals=0 max_score=62.68 
max_score_pre_threshold=62.68 strategy_signals=120 normalized=120 consensus=64 selected=29 
unique=29 strict_candidates=26 risk_passed=26 final_signals=0 stored=0
```

### Pipeline Breakdown:
| Stage | Count | Notes |
|-------|-------|-------|
| strategy_signals | 120 | Strategies generating signals ✓ |
| normalized | 120 | Deduplication passed ✓ |
| consensus | 64 | Down from 120 - some filtered ✓ |
| selected | 29 | Direction selection passed ✓ |
| unique | 29 | Fingerprint dedupe passed ✓ |
| strict_candidates | 26 | Validation gates passed ✓ |
| risk_passed | 26 | Risk checks passed ✓ |
| **final_signals** | **0** | **ALL REJECTED HERE** ✗ |
| stored | 0 | Nothing stored ✗ |

### Score Analysis:
- `max_score=62.68` - Below 70 threshold for PREMIUM
- `max_score_pre_threshold=62.68` - Same as after threshold (no adjustment)

---

## Files to Modify (Fixes)

### Fix 1: Lower EXPECTANCY_MIN Threshold
**File**: `core/tier_constants.py`
```python
# Change from:
EXPECTANCY_MIN: Final[float] = 0.15

# To (temporary for testing):
EXPECTANCY_MIN: Final[float] = 0.10
# Or disable entirely with env var
```

### Fix 2: Add Debug Logging for Gate Rejections
**File**: `engine/core.py` - Add detailed logging around line 2160:
```python
# Before expectancy check, add:
logger.warning(
    f"[engine] expectancy_check: asset={sig.get('asset')} "
    f"live_exp={live_exp:.3f} threshold={EXPECTANCY_MIN} "
    f"pass={'YES' if live_exp >= EXPECTANCY_MIN else 'BLOCKED'}"
)
```

### Fix 3: Fix Default Expectancy Value
**File**: `engine/core.py` - Change default from 0.15 to 0.0:
```python
# Change from:
live_exp = float(sig.get('live_expectancy', 0.15))

# To:
live_exp = float(sig.get('live_expectancy', 0.0))
# This allows signals without history to pass
```

### Fix 4: Score Threshold
**File**: Add env override
```
PREMIUM_SCORE_THRESHOLD=60
```

---

## Tier System

### User Tiers (from db/models.py):
| Tier | Score Required | Daily Limit |
|------|---------------|-------------|
| FREE | 80+ | 3 |
| PREMIUM | 70+ | 10 |
| VIP | 75+ | 20 |
| OWNER | 0 | Unlimited |
| ADMIN | 0 | Unlimited |

### Score Thresholds (core/tier_constants.py):
- FREE: 80
- PREMIUM: 70
- VIP: 75
- OWNER/ADMIN: 0

---

## Data Providers

### Working Providers (from logs):
- **CryptoCompare** - Working for crypto
- **Yahoo Finance** - Some FX working
- **Twelvedata** - Rate limited (429 errors)
- **Polygon** - Rate limited (429 errors)
- **Binance** - Disabled ("restricted location")

### Provider Fallback Chain:
1. Binance → 2. Bybit → 3. CryptoCompare → 4. Yahoo Finance → 5. Twelvedata

---

## Database Schema (Key Tables)

### signals (db/models.py):
- Signal model with asset, timeframe, direction, entry, stop_loss, take_profit
- score, strength, strategy_name, regime, ml_probability
- fingerprint (for deduplication)
- expires_at, expired, archived flags

### outcomes (db/models.py):
- Tracks signal results: tp, tp1, tp2, tp3, sl, expired, timeout
- r_multiple, percent, duration_seconds
- Used for expectancy calculations

### users (db/models.py):
- telegram_user_id, username, tier
- subscription management
- referral tracking

---

## Immediate Actions to Fix

1. **Lower EXPECTANCY_MIN to 0.10** or disable via env
2. **Set PREMIUM_SCORE_THRESHOLD=60** in env
3. **Enable ENGINE_CYCLE_LOG=true** for detailed debugging
4. **Deploy and check new logs for rejection reasons**

---

## Configuration Variables (Key)

| Variable | Default | Purpose |
|----------|---------|---------|
| ENGINE_CYCLE_SLEEP_SECONDS | 30 | Engine loop sleep |
| ENGINE_UNIVERSE_CAP | 20 | Max assets per cycle |
| PREMIUM_SCORE_THRESHOLD | 70 | Min score to deliver |
| ML_PROB_THRESHOLD | 0.55 | ML confidence threshold |
| EXPECTANCY_MIN | 0.15 | Live expectancy minimum |
| DRY_RUN | false | Test without sending |
| ENGINE_CYCLE_LOG | true | Log each cycle |

---

## Contact & Owner System

- **OWNER_IDS**: Telegram IDs that receive ALL signals
- **ADMIN_IDS**: Admin users with elevated access
- Tiers resolved from User.tier field in database

---

## Summary

The system is well-architected but has strict gates designed for production that are blocking signals in the current state. The main culprits are:
1. **EXPECTANCY_MIN=0.15** - blocks signals without outcome history
2. **PREMIUM_SCORE_THRESHOLD=70** - max_score was only 62.68

Recommendations:
1. Temporarily lower EXPECTANCY_MIN to 0.0 or 0.05
2. Lower PREMIUM_SCORE_THRESHOLD to 60
3. Add detailed rejection logging
4. Monitor logs after changes
