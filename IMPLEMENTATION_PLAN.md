# SignalRankAI Implementation Plan

Based on analysis of the codebase, here is the comprehensive implementation plan addressing all 11 features in the task.

---

## Phase 1: Fix Score Collapse (Priority: CRITICAL)

### Problem
In `engine/scoring.py`, line ~134: `return round(min(score, 100.0), 2)` causes hard saturation where many signals collapse to 100.

### Solution
1. Replace hard saturation with soft cap using exponential decay
2. Store component breakdown in every signal

### Changes Required

**File: engine/scoring.py**

```python
import math  # Add at top

# Replace line ~134:
# OLD: return round(min(score, 100.0), 2)
# NEW:
raw_score = score  # Store raw before cap

# Soft-cap: exponential decay prevents collapse while preserving ordering
# At raw_score=75, soft_score≈63; At raw_score=150, soft_score≈86
soft_score = 100.0 * (1.0 - math.exp(-raw_score / 75.0))
display_score = round(min(soft_score, 99.5), 2)

# Add component breakdown
signal["score_components"] = {
    "rr": rr_component,
    "vol": vol_component,
    "confidence": confidence,
    "confluence": confluence_score,
    "regime_bonus": regime_bonus,
    "ml_boost": ml_boost,
}
signal["raw_score"] = raw_score
signal["display_score"] = display_score

return display_score
```

---

## Phase 2: Fix risk_passed=0 Bottleneck (Priority: CRITICAL)

### Problem
In `engine/risk.py`, multi-target signals are evaluated only by TP1, causing good setups to be rejected.

### Solution
1. Add helper `best_target_for_direction()` to find best RR target
2. Gate on best RR, not weakest
3. Add tracking for rejection reasons

### Changes Required

**File: engine/risk.py**

```python
def best_target_for_direction(entry, stop, targets, direction):
    """Return the best valid target for given direction based on RR."""
    if not targets:
        return None
    valid = []
    for t in targets:
        try:
            t = float(t)
            rr = abs(t - entry) / max(abs(entry - stop), 1e-9)
            valid.append((rr, t))
        except Exception:
            continue
    if not valid:
        return None
    return max(valid, key=lambda x: x[0])[1]

# In risk_check() function, after getting targets:
best_tp = best_target_for_direction(entry, stop, targets, direction)
if best_tp is None:
    return False
rr = abs(best_tp - entry) / abs(entry - stop)
if rr < min_rr_risk:
    logger.warning(f"[RISK_DEBUG] RR_REJECTED: rr={rr} < min={min_rr_risk}")
    return False
```

Add tracking dict:
```python
# Log all RR metrics separately
risk_stats = {
    "rr_tp1": rr_tp1,
    "rr_final": rr_final,
    "rr_best": rr_best,
    "risk_rejected_rr": 0,
    "risk_rejected_volatility": 0,
    "risk_rejected_news": 0,
}
```

---

## Phase 3: Enforce Market Hours (Priority: HIGH)

### Problem
`data/market_hours.py` has `is_market_open()` but it's not called in the engine cycle.

### Solution
Call `is_market_open()` early in engine/core.py before strategy generation.

### Changes Required

**File: engine/core.py**

```python
# Add import at top
from data.market_hours import is_market_open, get_asset_class

# In main_loop, after asset filtering (around line where market_closed_reason is checked):
asset_class = get_asset_class(asset)
is_open, reason = is_market_open(asset_class)
if not is_open:
    logger.info("[engine] market-hours gate: %s blocked: %s", asset, reason)
    _record_gate_failure(asset, "market_hours", reason)
    continue
```

---

## Phase 4: Signal Lifecycle (Priority: HIGH)

### Problem
No explicit lifecycle state management; causes duplicates and repeated messages.

### Solution
`SignalOrchestrator` already exists in `services/signal_orchestrator.py`. Add explicit status tracking.

### Changes Required

**File: services/signal_orchestrator.py**

Add to class:
```python
# Add status enum
SIGNAL_STATUSES = {
    "draft": "draft",
    "issued": "issued", 
    "active": "active",
    "closed": "closed",
    "archived": "archived",
}

# Add to signal tracking
signal_state = {
    "signal_signature": compute_signature(signal),  # Add this
    "status": SIGNAL_STATUSES["issued"],
    "first_seen_at": datetime.utcnow(),
    "last_seen_at": datetime.utcnow(),
    "message_id": None,
    "edit_count": 0,
    "last_reason_code": reason,
}
```

Also update `engine/core.py` to set status when storing signals:
```python
stored_signal["status"] = "issued"
```

---

## Phase 5: Threshold Drift Protection (Priority: MEDIUM)

### Problem
Threshold changes too aggressive on small sample sizes.

### Solution
1. Add minimum sample count check
2. Add hysteresis band
3. Add rollback on performance drop

### Changes Required

**File: ml/dynamic_threshold.py**

```python
# Add constants
MIN_SAMPLES_FOR_ADJUSTMENT = 50
HYSTERESIS_BAND = 0.03  # Don't change if difference < 3%

def calculate_dynamic_threshold(base_threshold, current_auc, target_auc):
    sample_count = get_sample_count()  # Add this function
    
    # Check minimum samples
    if sample_count < MIN_SAMPLES_FOR_ADJUSTMENT:
        logger.info("[ml] Insufficient samples %d < %d, keeping threshold",
                   sample_count, MIN_SAMPLES_FOR_ADJUSTMENT)
        return base_threshold
    
    # Calculate new threshold
    new_threshold = _calculate(base_threshold, current_auc, target_auc)
    
    # Apply hysteresis
    current = get_current_threshold()
    if current and abs(new_threshold - current) < HYSTERESIS_BAND:
        return current  # Keep current if change is small
    
    return new_threshold
```

**File: engine/threshold_optimizer.py**

```python
# Add rollback on performance drop
async def analyze_and_adjust(self, force: bool = False) -> ThresholdConfig:
    # ... existing code ...
    
    # Check if recent performance worsened
    if self._check_performance_drop():
        logger.warning("[threshold_optimizer] Performance dropped, rolling back")
        await self._rollback_to_previous()
        return self._current
    
    # ... rest of code ...

def _check_performance_drop(self) -> bool:
    """Check if recent performance dropped significantly."""
    # Compare last N outcomes vs previous N
    recent_winrate = self._get_winrate(last_n=20)
    previous_winrate = self._get_winrate(previous_n=20)
    
    if recent_winrate < previous_winrate - 0.15:  # 15% drop threshold
        return True
    return False

async def _rollback_to_previous(self) -> None:
    """Rollback to previous threshold."""
    if self._previous_config:
        self._current = self._previous_config
        await self._save_to_db()
```

---

## Phase 6: Backtesting and Walk-Forward (Priority: MEDIUM)

### Problem
No offline validation path exists.

### Solution
Create walk-forward validation module.

### Changes Required

Create new files:
1. `ml/walk_forward.py` - Walk-forward optimization
2. `engine/backtest_runner.py` - Backtest execution
3. `tests/test_walk_forward.py` - Tests

```python
# ml/walk_forward.py
class WalkForwardValidator:
    """Walk-forward validation for signal strategies."""
    
    def __init__(self, train_window_days=30, test_window_days=7):
        self.train_window = timedelta(days=train_window_days)
        self.test_window = timedelta(days=test_window_days)
    
    def run_walk_forward(self, strategy, symbol, start_date, end_date):
        """Run walk-forward validation."""
        results = []
        current = start_date
        
        while current + self.train_window + self.test_window <= end_date:
            train_end = current + self.train_window
            test_end = train_end + self.test_window
            
            # Train on window
            train_data = self._get_data(symbol, current, train_end)
            strategy.train(train_data)
            
            # Test on next window
            test_data = self._get_data(symbol, train_end, test_end)
            result = self._backtest(strategy, test_data)
            results.append(result)
            
            current = test_end
        
        return self._aggregate_results(results)
```

---

## Phase 7: News and Macro-Event Gating (Priority: MEDIUM)

### Problem
High-impact events can cause unexpected losses.

### Solution
Wire `engine/news_filter.py` into engine/core.py.

### Changes Required

**File: engine/core.py**

```python
# Add import
from engine.news_filter import is_no_trade_zone

# In main_loop, before signal finalization:
if is_no_trade_zone(asset, buffer_minutes=60):
    logger.info("[engine] news gate: skipping %s (high-impact event)", asset)
    _record_gate_failure(asset, "news", "no_trade_zone")
    continue
```

Enhance `engine/news_filter.py`:
```python
def is_no_trade_zone(symbol: str, buffer_minutes: int = 60) -> bool:
    """Check if within no-trade window around high-impact events."""
    # Check 30/60/120 minute buffers
    for mins in [30, 60, 120]:
        if is_high_impact_event_near(symbol, mins):
            if buffer_minutes >= mins:
                return True
    return False

def is_high_impact_event_near(symbol: str, minutes: int) -> bool:
    """Check if high-impact event within N minutes."""
    # Events: CPI, NFP, FOMC, rate decisions
    HIGH_IMPACT_EVENTS = ["NFP", "CPI", "FOMC", "RATE"]
    
    events = get_upcoming_events(symbol)
    for event in events:
        if event.type in HIGH_IMPACT_EVENTS:
            if abs(event.minutes_until) <= minutes:
                return True
    return False
```

---

## Phase 8: Portfolio-Level Risk Control (Priority: MEDIUM)

### Problem
Risk is only per-signal, not at portfolio level.

### Solution
Create portfolio risk module.

### Changes Required

Create `engine/portfolio_risk.py`:
```python
class PortfolioRiskManager:
    """Portfolio-level risk management."""
    
    def __init__(self):
        self.max_total_exposure = 0.3  # 30% of account
        self.max_per_asset_class = 0.15  # 15% per class
        self.max_correlation = 0.85
    
    def is_trade_allowed(self, signal, active_positions) -> tuple[bool, str]:
        """Check if trade allowed at portfolio level."""
        # 1. Check total correlation exposure
        if self._exceeds_correlation_limit(signal, active_positions):
            return False, "correlation_limit"
        
        # 2. Check per-asset-class limit
        if self._exceeds_class_limit(signal, active_positions):
            return False, "asset_class_limit"
        
        # 3. Check drawdown limit
        if self._exceeds_drawdown_limit():
            return False, "drawdown_limit"
        
        return True, "ok"
    
    def _exceeds_correlation_limit(self, signal, positions) -> bool:
        """Check if new tradetoo correlated with existing."""
        # Implementation using correlation matrix
        pass
```

---

## Phase 9: Data Ingestion Resilience (Priority: MEDIUM)

### Problem
No fallback for data source failures.

### Solution
Build failover for data sources.

### Changes Required

**File: data/fetcher.py**

```python
def fetch_with_fallback(symbol, timeframe):
    """Fetch with provider fallback."""
    providers = get_providers_for(symbol, timeframe)
    
    for provider in providers:
        try:
            data = provider.fetch(symbol, timeframe)
            if data and is_fresh(data):
                return data
        except Exception as e:
            logger.warning(f"[fetcher] %s failed for %s: %s", provider.name, symbol, e)
            continue
    
    # Fallback to cached last-good data
    return get_cached_data(symbol, timeframe)
```

---

## Phase 10: New Features (Priority: LOW)

### Features to Add Next
1. Daily digest: issued, active, closed, win rate, drawdown, best asset
2. Explainability panel: why signal passed/failed
3. Trailing stop manager
4. Partial exit support (TP1/TP2/TP3)
5. Regime classifier: trend/range/breakout/chop
6. Correlation dashboard
7. Shadow mode: generate without sending
8. Dead-man switch: alert if engine stops
9. Admin controls
10. Signal ranking audit

---

## Phase 11: Tests (Priority: CRITICAL)

### Tests to Add Immediately

```python
# tests/test_score_distribution.py
def test_score_not_all_100():
    """Score distribution should spread, not collapse to 100."""
    # Generate 100 signals
    # Check score distribution
    # Assert: not all scores == 100
    pass

def test_rr_best_target():
    """Best target should be used for multi-target signals."""
    pass

def test_market_hours_gate():
    """Market hours should block closed sessions."""
    pass

def test_signal_dedup():
    """Duplicate signals should be suppressed."""
    pass

def test_threshold_rollback():
    """Threshold should rollback on performance drop."""
    pass
```

---

## Implementation Order

| Phase | Priority | Complexity | Estimated Time |
|-------|----------|------------|----------------|
| 1 | CRITICAL | Low | 30 min |
| 2 | CRITICAL | Medium | 1 hr |
| 3 | HIGH | Low | 30 min |
| 4 | HIGH | Medium | 1 hr |
| 5 | MEDIUM | Medium | 2 hr |
| 6 | MEDIUM | High | 4 hr |
| 7 | MEDIUM | Medium | 2 hr |
| 8 | MEDIUM | Medium | 2 hr |
| 9 | MEDIUM | Low | 1 hr |
| 10 | LOW | High | 8+ hr |
| 11 | CRITICAL | Low | 1 hr |

---

## Files to Modify

1. `engine/scoring.py` - Phase 1
2. `engine/risk.py` - Phase 2
3. `engine/core.py` - Phase 3, 4
4. `services/signal_orchestrator.py` - Phase 4
5. `ml/dynamic_threshold.py` - Phase 5
6. `engine/threshold_optimizer.py` - Phase 5
7. Create `ml/walk_forward.py` - Phase 6
8. Create `engine/backtest_runner.py` - Phase 6
9. `engine/news_filter.py` - Phase 7
10. Create `engine/portfolio_risk.py` - Phase 8
11. `data/fetcher.py` - Phase 9
12. Create test files - Phase 11
