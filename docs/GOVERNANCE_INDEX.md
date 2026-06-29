# Engineering Governance Index

Last updated: 2026-06-29
Owner: Engineering

SignalRankAI1 is managed as a continuously evolving software product. These
living documents are part of the product surface and must be updated whenever
the codebase is audited, implemented, refactored, optimized, or release-hardened.

## Living Registers

| Register | File | Purpose |
| --- | --- | --- |
| Technical Debt | `docs/LIVING_TECHNICAL_DEBT_REGISTER.md` | Verified debt, accepted risk, and closed remediation history. |
| Features | `docs/LIVING_FEATURE_REGISTER.md` | Discoverable map of user, trading, ML, data, and operational features. |
| Bugs | `docs/LIVING_BUG_REGISTER.md` | Known and closed bugs with reproduction and regression prevention. |
| Improvements | `docs/LIVING_IMPROVEMENT_REGISTER.md` | Non-bug improvements discovered during continuous discovery. |
| Risks | `docs/LIVING_RISK_REGISTER.md` | Technical, market, data, provider, security, and deployment risks. |
| ADR | `docs/LIVING_ADR.md` | Architecture decisions, alternatives, trade-offs, consequences. |
| Testing | `docs/LIVING_TESTING_REGISTER.md` | Test coverage inventory, missing tests, and quality gates. |
| Performance | `docs/LIVING_PERFORMANCE_REGISTER.md` | Latency, throughput, resource, and monitoring targets. |
| AI/ML | `docs/LIVING_AI_ML_REGISTER.md` | Models, features, prompts, drift, calibration, shadow learning. |
| UX | `docs/LIVING_UX_REGISTER.md` | Telegram/web/payments/onboarding UX inventory and gaps. |
| Trading Intelligence | `docs/LIVING_TRADING_INTELLIGENCE_REGISTER.md` | Strategies, indicators, gates, weighting, regime and outcome logic. |
| Deployment | `docs/LIVING_DEPLOYMENT_REGISTER.md` | Release topology, health checks, migration, rollback, and launch controls. |
| Knowledge Graph | `docs/KNOWLEDGE_GRAPH.md` | Map of files, functions, commands, models, APIs, tests, and dependencies. |
| Readiness Scorecard | `docs/PRODUCTION_READINESS_SCORECARD.md` | Subsystem readiness scores and next actions. |
| Shadow Governance | `docs/SHADOW_INTELLIGENCE_GOVERNANCE.md` | Rules for shadow evaluation and safe promotion. |
| Launch Runbook | `docs/PRODUCTION_LAUNCH_RUNBOOK.md` | Public production launch sequence, rollback, and evidence checklist. |
| Five-Year Roadmap | `docs/FIVE_YEAR_TRADING_SYSTEM_ROADMAP.md` | Research-backed durable architecture and feature roadmap for broker, risk, ML, data, portfolio, and audit upgrades. |

## Definition Of Done For Future Sessions

- Update affected living registers.
- Add or update tests for changed behavior.
- Add ADR entries for significant design decisions.
- Update the knowledge graph when files, APIs, commands, models, or workflows change.
- Update production readiness scores when evidence improves or degrades.
- Run `python scripts/validate_governance_docs.py`.
- Record verification commands and results in the relevant report or register.
