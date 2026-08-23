# Cross-Chat Decision Ledger

Last updated: 2026-07-26

This file is the self-contained historical decision source for an implementation agent that cannot access prior conversations.

| Decision ID | Canonical decision | Supersedes/clarifies |
|---|---|---|
| SCD-001 | SignalRankAI is a Telegram-first full trading ecosystem, not just an alert bot. | Narrow signal-bot interpretations |
| SCD-002 | Initial Railway target is one coordinated async service, one Uvicorn worker, PostgreSQL and two Redis services. | Earlier multi-process suggestions |
| SCD-003 | PostgreSQL is durable truth; Redis is acceleration/queue state and must be reconstructible. | Redis-authoritative implementations |
| SCD-004 | Delivery proof requires successful Telegram response and persisted `sent_ok`, chat ID and message ID. | Generated/stored-as-delivered claims |
| SCD-005 | `/signals` defaults to active signals actually delivered to the requesting user in the last seven days. | Global/stored signal lists |
| SCD-006 | Canonical tiers are `free`, `premium`, `vip`, `admin`, `owner`. | Legacy aliases |
| SCD-007 | Canonical profiles are `scalp`, `day`, `swing`, `position`, `all`; day signals should normally resolve within one day. | Generic profile placeholders |
| SCD-008 | Product timeframes include 5m, 15m, 1h, 4h and 1d. | Provider-only timeframe assumptions |
| SCD-009 | Same-user same-asset repeat lock defaults to four hours after proven delivery, direction agnostic; active-position and fingerprint locks still apply. | Historical 12h/6h tier defaults |
| SCD-010 | Historical timeframe cooldown defaults: 15m 10m, 1h 20m, 4h 90m, 1d 6h, subject to latest central policy. | Inconsistent scattered defaults |
| SCD-011 | Prefer quality over forced signal frequency; a 60% win rate is an aspirational research target, never a guarantee or release assertion. | Frequency/win-rate pressure |
| SCD-012 | Generated, rejected, delivered, paper, shadow, backtest, walk-forward, demo and real execution performance remain separate. | Blended statistics |
| SCD-013 | Track rejected/near-miss candidates, MFE, MAE, duration, market context and technical features for offline ML. | Winner-only datasets |
| SCD-014 | Heavy training, SHAP and bulk replay do not run continuously on the live Railway monolith. | Live in-process training |
| SCD-015 | Multi-provider support must be capability-, quota-, freshness- and provenance-aware; public/mock tests do not equal live certification. | Provider-name-only integrations |
| SCD-016 | Supported markets include crypto spot/derivatives, FX, commodities, equities, indices and broker instruments where genuinely supported. | Crypto-only final product |
| SCD-017 | WebSockets are optional optimisations; REST must preserve correctness during degradation. | WebSocket-only correctness |
| SCD-018 | Every Telegram command and visible button is treated as unverified until end-to-end tested; callbacks ACK immediately and are idempotent. | Registration-only claims |
| SCD-019 | Early-exit warnings are recommendations and do not rewrite the official signal outcome. | Outcome manipulation |
| SCD-020 | Paystack public payments and real payouts remain disabled until test-mode reconciliation and support flows pass. | Premature paid release |
| SCD-021 | MetaApi/demo execution is the Railway-compatible broker path; native Windows MT5 cannot be pretended to run inside Railway Linux. | Unsafe native bridge assumptions |
| SCD-022 | Real execution, copy trading and Smart DCA remain gated by consent, account/spec/risk truth, idempotency, kill switch and separate approval. | Feature-presence-as-release |
| SCD-023 | The system must recover safely from DB pressure, Redis loss, provider outage, process restart and uncertain Telegram sends. | Happy-path readiness |
| SCD-024 | The implementation agent must keep working on unblocked tasks, request permissions in one queue and defend completion with reproducible evidence. | Plan-only/premature completion |
| SCD-025 | V8 is authoritative over preserved V7/adaptive appendices; newer verified repository/runtime evidence remains stronger than historical completion claims. | Equal treatment of historical prompt layers |
| SCD-026 | Continuous improvement may aggregate, review, recommend, experiment and create Codex tasks, but cannot autonomously apply code, deploy, change risk, or activate financial features. | Unsafe production self-modification |

## Historical incidents that remain regression contracts

Database pool exhaustion; broadcasts failing; generated signals not received; callbacks not responding; provider outages; yfinance timestamp issues; CoinGecko instability; WebSocket restart loops; stored-only exposure contamination; Redis-empty mass expiry; synthetic ML contamination; TradingView route interception; waitlist import failures; Bybit category errors; derivative-as-spot errors; unsafe MT5 fallback sizing; Smart DCA state/account/Redis defects; fan-out N+1 queries; queue expiry; local `telegram` package shadowing; inconsistent UTC timestamps; and weakened token-rotation tests.
