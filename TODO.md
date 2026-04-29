# SignalRankAI Production Upgrade - Approved Plan (Phase 2+)
User approved plan. Priority: A (risk/expectancy) > B (incompletes) > C (research). 
Dynamic real-time values from data/news/gemini/ML/outcomes (no fixed).

## Progress Tracker [11/32 complete]

### Phase 1: Audit & Plan ✅ COMPLETE
- [x] Repo scan + TODO/FIXME audit
- [x] Core files read (risk_manager, signal_validator, consensus, core, scoring, risk)
- [x] Plan written + user approved

### Phase 3: DB Live Metrics [3/3] ✅ COMPLETE
9. [x] db/models.py: Add AssetLiveMetric, StrategyLiveMetric
10. [x] alembic migration: manual run recommended (DB connection needed)
11. [x] engine/risk.py + core.py: Query live expectancy (updated expectancy_gate.py)

### Phase 2: Risk/Expectancy Gates ✅ COMPLETE
(1-8 as above)

### Phase 4: Dynamic Targets/Stubs [1/6]
12. [x] strategies/dynamic_targets.py: BASE_RR=2.0 (dynamic ATR/structure) ✅ created
13. [ ] Fix calculate_position_size stubs (risk.py etc.)
14. [ ] admin/auto_kill.py: real impl (not pass)
15. [ ] worker/worker.py: handle signals (not pass)
16. [ ] utils/proxy_manager.py: real proxy rotation
17. [ ] data/startup_selfcheck.py: real checks

### Phase 5: ML/Research Enhancements [0/8]
18. [ ] services/gemini_ml.py: realtime sentiment to scoring/news
19. [ ] data/news.py: integrate to scoring gates
20. [ ] ml/drift_monitor.py: realtime retrain trigger
21. [ ] Research Freqtrade/QuantConnect → add confluence/ML patterns
22. [ ] engine/advanced_filters.py: gemini/news vol-adjusted
23. [ ] engine/ultra_quality_filter.py: expectancy + live PnL
24. [ ] engine/ranking.py: PREMIUM=70 align + live boost
25. [ ] ml/retrain.py: auto on expectancy drop

### Phase 6: Tests/Deploy [0/7]
26. [ ] NEW test_expectancy_gate.py
27. [ ] NEW test_risk_dynamic.py
28. [ ] test_all_functions.py --fix failures
29. [ ] verify_system.py run + fix
30. [ ] alembic upgrade head
31. [ ] deploy smoke tests
32. [ ] attempt_completion

Next: Phase 4 Step 13 - Fix position sizing stubs in risk.py and dependent files. Type hints + real impl.

Run command to test: python test_risk_dynamic.py (create first)
