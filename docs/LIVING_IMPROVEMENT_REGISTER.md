# Living Improvement Register

Last updated: 2026-06-29
Owner: Product/Engineering

Record anything that can become better, even when it is not broken.

| ID | Opportunity | Category | Priority | Explanation | Affected Files | Proposed Action | Tests/Verification | Status | Date Opened | Owner |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| IMP-001 | Wire decision intelligence through full lifecycle | AI/Architecture | High | `_log_decision()` now enriches all existing decision-log call paths with structured `decision_intelligence`; richer subsystem payloads still need to be passed from individual gates. | `engine/core.py`, `services/decision_intelligence.py` | Add deeper Gemini/news/shadow/liquidity/historical payloads at each gate. | Governance/decision tests plus full suite passed. | In Progress | 2026-06-29 | Engineering |
| IMP-002 | Premium Telegram message rewrite | UX | High | User trust and conversion depend on clear, consistent, premium messaging. | `signalrank_telegram/*` | Inventory every command and message, rewrite workflow by workflow, add snapshots. | Contract/snapshot tests. | Open | 2026-06-29 | Product/Engineering |
| IMP-003 | Enterprise observability | Reliability | High | Production needs metrics, alerting, latency, and health visibility. | `core`, `engine`, `web`, `worker` | Add metrics endpoints/events and alert thresholds. | Metrics contract tests and health checks. | Open | 2026-06-29 | Engineering |
| IMP-004 | Historical news impact learning | Trading intelligence | Medium | News assessment is deterministic but not yet outcome-trained. | `services/news_intelligence.py`, `db`, `engine` | Join event classifications with outcomes and calibrate impact scores. | Backtest/replay tests. | Open | 2026-06-29 | Quant/Engineering |
| IMP-005 | Config drift dashboard | Operations | Medium | Env fallback differences can change signal behavior. | `config.py`, `web`, `signalrank_telegram/owner_commands.py` | Expose sanitized config snapshot and profile diff. | Startup/config tests. | Open | 2026-06-29 | Engineering |
