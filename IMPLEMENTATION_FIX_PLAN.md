# SignalRankAI Implementation Fix Plan

**Project:** SignalRankAI - Multi-Asset Signal Engine  
**Date:** 2025-01-14  
**Status:** ARCHITECTURE REVIEWED - FIXES IDENTIFIED

---

## Executive Summary

The SignalRankAI codebase has strong architectural foundations with most major components already present. The main issues are:

1. **Scattered implementations** - Many features already implemented but not consolidated
2. **Missing consolidation layer** - Market/session awareness exists as helpers but no unified module
3. **Some edge cases** - Minor fixes needed but core logic is sound

---

## Information Gathered

### Already Working (Good Shape)
- ✅ `data/pair_discovery.py` - Multi-asset discovery across crypto, FX, commodities, stocks
- ✅ `services/asset_mapper.py` - Asset class mapping
- ✅ `engine/signal_deduplicator.py` - Semantic dedupe implemented
- ✅ `signalrank_telegram/tier_delivery.py` - Tier-aware delivery
- ✅ `engine/realtime_outcome_tracker.py` - Live + shadow outcome tracking (uses timezone-aware UTC)
- ✅ `engine/shadow_outcome_worker.py` - Shadow tracking present
- ✅ `services/gemini_ml.py` - Has both live gate and review pipeline functions
- ✅ `signalrank_telegram/bot.py` - Centralized command registration with self-audit

### Architecture Present But Needs Completion
- ⚠️ **Scoring soft-cap** - Implemented in `scoring.py` (soft_score) but needs display_score field
- ⚠️ **Market/session awareness** - Exists partially in helpers, needs unified module
- ⚠️ **Risk gate** - Has `best_target_for_direction` but needs better rejection logging
- ⚠️ **Signal lifecycle** - Exists but needs explicit state model

---

## Plan: Fix Implementation

### Phase 1: Consolidation & Hardening (Critical)

#### 1.1 Add display_score to scoring output
**File:** `engine/scoring.py`
- Keep `raw_score` for internal ranking
- Add `display_score` for user-facing display  
- Use soft-cap formula already present

#### 1.2 Create unified market/session module
**New File:** `market/session_classifier.py`
- Consolidate session detection logic
- Add asset-class specific hours
- Create session-aware scoring adjustments

**Existing to reference:**
- `data/market_hours.py` - Exchange hours
- `core/tier_constants.py` - Session constants

#### 1.3 Add rejection reason tracking to risk gate
**File:** `engine/risk.py`
- Add `_risk_stats` diagnostic logging
- Track rejection reasons: RR, spread, volatility, correlation, regime, news, session
- Keep strict but make explainable

### Phase 2: Enhanced Features

#### 2.1 Gemini structured output verification
**File:** `services/gemini_ml.py`
- Already has structured functions: `gemini_confluence_check_with_tech_context`, `run_gemini_review_pipeline`
- Verify output format includes: decision, confidence, veto_reason, risk_tags, recommended_action

#### 2.2 Signal lifecycle explicit state
**Action:** Add explicit state model to Signal entity
- States: draft → issued → active → closed → archived
- Single canonical signal_signature
- Update Telegram message when setup changes materially

#### 2.3 Outcome tracking verification
**File:** `engine/realtime_outcome_tracker.py`
- Already uses timezone-aware UTC: `datetime.now(timezone.utc)`
- Verify idempotency on (signal_id, status)

### Phase 3: New Feature Additions (Recommended)

#### 3.1 Per-asset-class thresholds
**Config:** Add separate thresholds for:
- CRYPTO_SCORE_THRESHOLD = 30
- FX_SCORE_THRESHOLD = 28
- STOCK_SCORE_THRESHOLD = 25
- COMMODITY_SCORE_THRESHOLD = 32

#### 3.2 Session-aware scoring bonuses
**Example:**
- LONDON_NY_OVERLAP: +5 score
- US_EQUITY_POWER_HOUR: +3 score  
- AFTER_HOURS: -10 score

---

## Dependent Files to Edit

| Priority | File | Changes Required |
|-----------|------|------------------|
| CRITICAL | `engine/scoring.py` | Add display_score field |
| CRITICAL | `market/session_classifier.py` | NEW - consolidation |
| HIGH | `engine/risk.py` | Enhanced rejection logging |
| MEDIUM | `services/gemini_ml.py` | Verify structured output |
| MEDIUM | `engine/core.py` | Update to use session classifier |

---

## Followup Steps

After implementing edits:

1. **Test startup:** Run `python -c "from engine.core import main_loop; print('OK')"`
2. **Test scoring:** Run test signals through scoring module
3. **Check logs:** Verify rejection reasons are logged
4. **Deploy to Railway:** Push and verify heartbeat

---

## Notes for User

Based on my analysis, the codebase is actually in better shape than described in the task. Key observations:

1. **No startup-breaking indentation error visible** - The `_FallbackThresholdOptimizer` class appears properly indented in the current version
2. **Soft-cap already implemented** - `scoring.py` already has soft_score formula
3. **Most architecture present** - The issue is consolidation, not missing components
4. **Timezone awareness** - Already using `datetime.now(timezone.utc)` in outcome tracker

The main work is consolidating existing implementations into a unified system and adding the final polish pieces.

---

## Implementation TODO

- [ ] Phase 1.1: Add display_score to scoring.py
- [ ] Phase 1.2: Create market/session_classifier.py  
- [ ] Phase 1.3: Enhance risk.py rejection logging
- [ ] Phase 2.1: Verify Gemini structured output
- [ ] Phase 2.2: Add explicit signal lifecycle state
- [ ] Phase 3.1: Add per-asset-class thresholds
- [ ] Phase 3.2: Add session-aware scoring
