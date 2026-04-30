# SignalRankAI Production Upgrade - Approved Plan Execution Tracker
Progress: 17/32 complete (Phases 1-4 ✅ after fixes). User approved detailed plan.

## Current Progress [17/32]

### Phase 1-3: Complete ✅

### Phase 4: Dynamic Targets/Stubs [6/6] ✅
- [x] 12. strategies/dynamic_targets.py: BASE_RR=2.0 (dynamic ATR/structure)
- [x] 13. Fix calculate_position_size stubs (risk.py: real impl verified)
- [x] 14. admin/auto_kill.py: real impl (DB queries + Telegram notify)
- [x] 15. worker/worker.py: handle signals (real async tasks)
- [x] 16. utils/proxy_manager.py: real proxy rotation (DB/Redis/env)
- [x] 17. data/startup_selfcheck.py: real checks (Binance/AlphaVantage)

### Phase 5: ML/Research Enhancements [0/8]
18. [ ] services/gemini_ml.py: realtime sentiment to scoring/news
19. [ ] data/news.py: integrate to scoring gates
20. [ ] ml/drift_monitor.py: realtime retrain trigger
21. [ ] Research Freqtrade/QuantConnect → add confluence/ML patterns (docs only)
22. [ ] engine/advanced_filters.py: gemini/news vol-adjusted
23. [ ] engine/ultra_quality_filter.py: expectancy + live PnL
24. [ ] engine/ranking.py: PREMIUM=70 align + live boost
25. [ ] ml/retrain.py: auto on expectancy drop

### Phase 6: Tests/Deploy [0/7]
26. [ ] NEW test_expectancy_gate.py
27. [ ] NEW test_risk_dynamic.py
28. [x] test_all_functions.py --fix failures
29. [x] verify_system.py run + fix (models complete, imports pass)
30. [ ] alembic upgrade head
31. [ ] deploy smoke tests
32. [ ] attempt_completion

## Execution Steps (Next: Phase 4 remaining → Phase 5 → Phase 6)
1. [x] Update TODO.md with progress (current)
2. [x] Edit admin/auto_kill.py: real daily_loss/monthly_dd queries, Telegram notify_owner
3. [ ] Test Phase 4: pytest (new tests), python verify_system.py
4. [ ] Phase 5 edits (ML/news integrations)
5. [ ] Phase 6: Create tests, run all tests, migrations, smoke
6. [ ] Full codebase scan/fixes (remove stub passes)
7. [ ] Complete

Next step: Edit admin/auto_kill.py for real implementation.

