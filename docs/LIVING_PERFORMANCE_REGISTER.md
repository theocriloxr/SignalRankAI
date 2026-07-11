# Living Performance Register

Last updated: 2026-06-29
Owner: Engineering

| Metric | Target | Current Evidence | Instrumentation | Improvement Plan | Status |
| --- | --- | --- | --- | --- | --- |
| API latency | p95 under 500 ms for common health/admin endpoints | `core/telemetry.py` exposes `signalrank_http_request_seconds`; `/metrics/prometheus` is tested. | Prometheus metrics endpoint | Add dashboard and alert thresholds. | Partial |
| Signal generation latency | Complete engine cycle within configured worker cadence | `signalrank_engine_cycle_seconds` and `signalrank_engine_task_seconds` exist. | Prometheus histograms | Wire per-cycle observations consistently and add alerts. | Partial |
| Database performance | Indexed critical lookups and bounded worker queries | Migrations include indexes for decisions and token paths. | DB logs/manual inspection | Add slow-query logging and query budget tests. | Partial |
| Telegram delivery latency | p95 under 10 seconds from signal eligibility to send | `signalrank_signal_dispatch_seconds` and dispatch totals exist. | Prometheus histograms/counters | Add delivery SLO dashboard and paging threshold. | Partial |
| News processing latency | Provider sync within configured worker interval | News worker exists; no p95 dashboard. | Worker logs | Add news ingestion timing metrics. | Open |
| ML inference latency | Predict within signal pipeline budget | Tests do not measure latency. | Planned timing wrapper | Add timing and circuit-breaker thresholds. | Open |
| Gemini response latency | Avoid blocking signal pipeline beyond configured budget | Gemini calls are isolated/fail-open where needed. | Planned timing wrapper | Add timeout/cost/performance report. | Open |
| Memory/CPU | Stable under worker and bot load | Not formally measured in project code. | Planned process metrics | Add lightweight process telemetry or platform dashboard binding. | Open |
