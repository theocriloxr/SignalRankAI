# SignalRankAI Fix All Issues & Incomplete Code - Approved Plan
Status: Approved by user. Step 1a COMPLETE: Removed all print statements → logger.

## Logical Steps from Plan (Step-by-Step Execution)

### 1. HIGH-PRIORITY FIXES (Stability)
- [x] 1a. Remove/replace ALL print statements → logger (worker.py ✅, data/fetcher.py ✅, data/ws_ingest.py ✅, data/pair_discovery.py ✅, data/startup_selfcheck.py ✅, scripts/post_deploy_smoke.py ✅)
- [ ] 1b. Complete _bypass_fingerprint impl (core/redis_state.py)
- [ ] 1c. Add signal expiry cleanup job (worker.py → cron DELETE archived/expired >30d)
- [ ] 1d. Add schema bootstrap startup check (railway_main.py/main.py → STARTUP_SCHEMA_BOOTSTRAP)

### 2. MEDIUM-PRIORITY (Data/Features)
- [ ] 2a. FX data fallback if no ALPHAVANTAGE_KEY (data/fetcher.py → Yahoo/Polygon)
- [ ] 2b. Complete provider cascade w/ breakers/alerts (data/fetcher.py)
- [ ] 2c. Memory mitigations + gc.collect() (worker.py)

### 3. CLEANUP
- [ ] 3a. Update ISSUES_AND_FIXES.md (mark completed, add new)
- [ ] 3b. Update TODO.md (clear old)

### 4. VALIDATION
- [ ] 4a. Run `python test_all_features.py`
- [ ] 4b. Run `python verify_system.py`
- [ ] 4c. Run `python scripts/post_deploy_smoke.py`
- [ ] 4d. Final ISSUES_AND_FIXES.md review

**Next Step**: 1b fingerprint bypass → 1c expiry cleanup.
