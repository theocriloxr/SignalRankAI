# Living AI And ML Register

Last updated: 2026-06-29
Owner: Quant/Engineering

| Component | Purpose | Files | Data/Features | Prompt/Model Version | Calibration/Drift | Explainability | Tests | Status | Planned Improvements |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ML filter | Score/filter candidate signals. | `ml/*`, `engine/core.py` | Market, macro, on-chain, signal features | Model artifacts/configured thresholds | Threshold optimizer and shadow prediction records exist | DecisionLog/MLRejectedSignal | ML and engine tests | Active | Add champion/challenger governance and calibration dashboard |
| ML rejection tracker | Preserve rejected signals for outcome learning. | `engine/signal_deduplicator.py`, `db/models.py` | Rejected signal features and outcomes | N/A | Backfills decision logs into rejection table | Rejection reason and feature payload | Full suite | Active | Add false positive/negative analysis reports |
| Shadow predictions | Record non-production model predictions. | `ml/ml.py`, `db/models.py`, `engine/shadow_outcome_worker.py` | Feature schema and probability | `MLShadowPrediction` model metadata | Shadow outcome worker planned/available | Meta payload | Existing tests plus future replay | Partial | Add precision/recall/calibration reports |
| Gemini confluence | AI-assisted veto/explanation/audit. | `services/gemini_ml.py` | Signal, news, recent outcomes/rejections | Env-configured Gemini model | No formal drift/cost dashboard yet | Admin replies and decision metadata | Command tests | Partial | Add prompt registry, prompt tests, cost/latency tracking |
| Decision intelligence | Structured audit of signal reasoning. | `services/decision_intelligence.py`, `engine/core.py` | Strategy votes, ML, news, risk, regime, shadow | `decision-intelligence-v1` | Supports confidence calibration section | `_log_decision()` enriches DecisionLog meta with `decision_intelligence` | `tests/test_decision_intelligence.py`, full suite | Active | Pass richer Gemini/news/shadow/liquidity/historical payloads from each gate |
| News intelligence | Evidence scoring for news impact. | `services/news_intelligence.py` | Source, title, body, asset aliases, event classes | Deterministic v1 | Uncertainty/fake-news scoring | Structured assessment output | `tests/test_news_intelligence.py` | Active | Add historical event learning and cross-source consensus |
