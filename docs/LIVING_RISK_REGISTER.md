# Living Risk Register

Last updated: 2026-06-29
Owner: Engineering

| ID | Risk | Type | Probability | Impact | Mitigation | Contingency Plan | Owner | Status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| RISK-001 | Telegram Bot API outage or rate limiting delays notifications. | Third-party/Telegram | Medium | High | Retry helpers, idempotent delivery records, delivery queue. | Pause non-critical sends, notify admins, replay pending deliveries. | Engineering | Open |
| RISK-002 | Market data provider returns stale or low-quality candles. | Data | High | High | Data quality checks, provider fallbacks, stale signal validation. | Disable affected provider and fail open/closed by asset class policy. | Engineering | Open |
| RISK-003 | News or social source publishes false market-moving rumor. | News/Data | Medium | High | Source reliability, fake-news risk flags, cross-source confidence. | Suppress/delay affected signals until reliable confirmation. | Product/Engineering | Open |
| RISK-004 | ML model drifts during regime change. | ML | Medium | High | Shadow predictions, threshold optimizer, rejection/outcome tracking. | Raise thresholds, fall back to rule-based gates, retrain after review. | Quant/Engineering | Open |
| RISK-005 | Gemini API unavailable, slow, or costly. | AI/Third-party | Medium | Medium | Fail-open where appropriate, admin audit isolation, prompt controls. | Disable Gemini gate and rely on deterministic filters. | Engineering | Open |
| RISK-006 | Payment webhook replay or provider issue affects subscriptions. | Security/Business | Low | High | Processed event table, signature validation, idempotency. | Manual entitlement reconciliation and Paystack audit. | Engineering | Open |
| RISK-007 | Configuration drift changes production behavior. | Deployment | High | Medium | Config register and planned startup snapshot. | Roll back env changes and compare with known-good profile. | Engineering | Open |
| RISK-008 | Broker/execution integration behaves differently from signal assumptions. | Broker/Trading | Medium | High | MT5 bridge abstractions, execution records, risk controls. | Disable auto-execution and send advisory-only signals. | Engineering | Open |
