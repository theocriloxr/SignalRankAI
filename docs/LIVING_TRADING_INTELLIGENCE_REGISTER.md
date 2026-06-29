# Living Trading Intelligence Register

Last updated: 2026-06-29
Owner: Quant/Engineering

Every trading rule should be documented with a reason.

| Rule/Subsystem | Purpose | Files | Reason | Inputs | Output | Tests | Status | Planned Improvements |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Strategy execution | Generate candidate trade ideas. | `strategies/*`, `engine/strategies/runner.py` | Multi-strategy coverage improves opportunity discovery. | Candles, indicators, regime | Candidate signals | Strategy tests | Active | Add strategy contribution reports |
| Dynamic targets | Set SL/TP based on volatility and quality. | `strategies/dynamic_targets.py` | Targets must adapt to market volatility and signal quality. | Entry, candles, indicators, direction | Stop loss, take profits, RR | Strategy/risk tests | Active | Calibrate by historical outcome |
| Risk engine | Enforce sizing, volatility, drawdown, expectancy rules. | `engine/risk.py`, `engine/filters.py` | Prevent uncontrolled downside and poor conditions. | Signal, account state, volatility | Approve/reject/sizing | `tests/test_risk_dynamic.py` | Active | Time handling modernization |
| Score/ranking | Prioritize high-quality signals. | `engine/scoring.py`, `engine/ranking.py` | Users need fewer, better signals. | Technical/ML/risk factors | Score/rank | Scoring tests | Active | Add calibration by tier/outcome |
| On-chain alpha | Avoid long/short trades during flow spikes. | `engine/onchain_alpha.py` | Exchange flows can precede crypto price moves. | Provider context, direction | Veto/reason | `tests/test_onchain_providers.py` | Active | Add provider live tests |
| News weighting | Delay/suppress uncertain or high-impact news conditions. | `services/news_intelligence.py` | News can invalidate technical setups. | Source evidence | News assessment/action | `tests/test_news_intelligence.py` | Active | Wire to signal lifecycle and outcome learning |
| Gemini weighting | AI confluence/veto for contextual risk. | `services/gemini_ml.py` | LLM can identify contextual traps when bounded by prompts. | Signal/news/recent history | Approval/veto/explanation | Command tests | Partial | Prompt registry and cost/latency governance |
| Session/regime logic | Adjust quality by market state and session. | `engine/regime.py`, `market/session_classifier.py` | Edge changes across sessions/regimes. | Time, market data | Regime/session labels | Strategy tests | Active | Add regime outcome dashboard |
| Shadow learning | Compare live decisions with alternatives. | `db/models.py`, `engine/shadow_outcome_worker.py`, `ml/ml.py` | Improvements must be evidence-backed before promotion. | Production/shadow decisions/outcomes | Metrics/recommendations | Partial | Partial | Add replay, significance, and promotion gates |
