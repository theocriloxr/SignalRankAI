# SignalRankAI All Bugs Fix Implementation TODO

## Progress Tracking

### Priority 1: Critical Production Bugs
| # | Fix | Status | Notes |
|---|-----|--------|-------|
| 1.1 | Fix signal fingerprint | ✅ DONE | candle_timestamp removed, entry_zone removed |
| 1.2 | Add Redis lock | ✅ DONE | Created dedup_wrapper.py with signal_lock |
| 1.3 | Add active signal protection | ✅ DONE | check_active_signal_exists() in signal_lock.py |
| 1.4 | Add PostgreSQL uniqueness | ⚠️ PARTIAL | Need to add unique constraint via migration |
| 1.5 | Telegram delivery cooldown | 🔲 PENDING | Need tier-based cooldown in bot.py |

### Priority 2: Buttons Not Working
| # | Fix | Status | Notes |
|---|-----|--------|-------|
| 2.1 | Unify callback handlers | 🔲 PENDING | Create callback_router.py |
| 2.2 | Add callback logging | 🔲 PENDING | Log all button presses |

### Priority 3: Outcome Tracking
| # | Fix | Status | Notes |
|---|-----|--------|-------|
| 3.1 | Unify outcome ownership | 🔲 PENDING | RealtimeOutcomeTracker as sole owner |
| 3.2 | Add signal_state enum | 🔲 PENDING | ACTIVE/TP1_HIT/TP2_HIT/SL_HIT/etc |

### Priority 4: Freshness Bug
| # | Fix | Status | Notes |
|---|-----|--------|-------|
| 4.1 | Fix freshness source | 🔲 PENDING | Use single source for age |
| 4.2 | Fix "Aging 0m" display | 🔲 PENDING | Logic fix in formatting |

### Priority 5: Stale Signal Logic
| # | Fix | Status | Notes |
|---|-----|--------|-------|
| 5.1 | Refactor validate() | 🔲 PENDING | Return VALID/INVALID/ENTRY_ZONE_OVERRIDE |

### Priority 6: Railway Stability
| # | Fix | Status | Notes |
|---|-----|--------|-------|
| 6.1 | Redis health monitor | 🔲 PENDING | PING every minute |
| 6.2 | PostgreSQL health | 🔲 PENDING | SELECT 1 every minute |
| 6.3 | Engine heartbeat table | 🔲 PENDING | Track last_cycle, last_signal, etc |

### Priority 7: Database
| # | Fix | Status | Notes |
|---|-----|--------|-------|
| 7.1 | Add indexes | 🔲 PENDING | Signals table, Outcomes table, Deliveries table |

### Priority 8: Signal Lifecycle
| # | Fix | Status | Notes |
|---|-----|--------|-------|
| 8.1 | Message threading | 🔲 PENDING | NEW -> UPDATED -> TP1 -> etc |

### Priority 9: ML System
| # | Fix | Status | Notes |
|---|-----|--------|-------|
| 9.1 | Confidence calibration | 🔲 PENDING | Store predicted/actual for recalibration |
| 9.2 | Monthly recalibration | 🔲 PENDING | Improve accuracy over time |

### Priority 10: Enhancements
| # | Fix | Status | Notes |
|---|-----|--------|-------|
| 10.1 | Trade Journal | 🔲 PENDING | Per-user win rate, profit factor |
| 10.2 | Signal Replay | 🔲 PENDING | Show EMA, RSI, OB, Volume |
| 10.3 | Portfolio Exposure | 🔲 PENDING | Prevent correlated exposure |
| 10.4 | Market Regime Detection | 🔲 PENDING | TRENDING/RANGING/VOLATILE |
| 10.5 | Institutional Scoring | 🔲 PENDING | Liquidity sweep, FVG, etc |

## Implementation Details

### 1. Fingerprint Fix (DONE)
- Removed candle_timestamp from compute_signal_fingerprint() in db/pg_features.py
- Removed entry_zone from fingerprint (was causing duplicates when price changed)
- Now uses: asset|timeframe|direction|entry|sl|tp|strategy_group|strategy_name

### 2. Redis Lock (DONE)
- Created engine/signal_lock.py - Redis-backed signal locks
- Key format: signal_lock:{ASSET}:{DIRECTION}:{TIMEFRAME}[-{STRATEGY_GROUP}]
- TTL: 4 hours for 4H, 6 hours for 1D, 90 min for others
- Created engine/dedup_wrapper.py - unified dedup layer

### 3. Active Signal Protection (DONE)
- Added check_active_signal_exists() in signal_lock.py
- Checks PostgreSQL for active signal (status='active')

### 4. PostgreSQL Uniqueness (PENDING)
- Need to add unique constraint on Signals table
- Columns: (asset, direction, timeframe, status='active')

### 5. Telegram Delivery Cooldown (PENDING)
- Need to add per-user Redis key: delivery:{USER_ID}:{ASSET}:{DIRECTION}
- TTL based on tier:
  - VIP: 4 hours
  - Premium: 6 hours  
  - Free: 12 hours

## Files Modified
- db/pg_features.py - fingerprint fix ✅
- engine/dedup_wrapper.py - new unified dedup ✅
- engine/signal_lock.py - new lock module ✅

## Files Needed
- signalrank_telegram/callback_router.py - unified callbacks
- signalrank_telegram/delivery.py - cooldown logic

## Testing Commands
```bash
# Test fingerprint
python -c "
from db.pg_features import compute_signal_fingerprint
sig = {'asset': 'SOLUSDT', 'direction': 'long', 'timeframe': '4h', 'entry': 100.0, 'stop_loss': 95.0, 'take_profit': 110.0, 'strategy_group': 'breakout', 'strategy_name': 'breakout_ema'}
fp = compute_signal_fingerprint(sig)
print(f'Fingerprint: {fp}')
"
