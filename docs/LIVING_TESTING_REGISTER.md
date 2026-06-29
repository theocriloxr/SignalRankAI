# Living Testing Register

Last updated: 2026-06-29
Owner: QA/Engineering

| Test Area | Type | Current Coverage | Commands | Missing Coverage | Status | Owner |
| --- | --- | --- | --- | --- | --- | --- |
| Full project regression | Regression | Full pytest suite passed after production launch engineering pass: `263 passed, 34 warnings`. | `.venv/Scripts/python.exe -m pytest -q` | Live external integrations disabled by default. | Active | Engineering |
| Governance docs | Unit/contract | Validates living register presence and required content; validator passed for 17 documents. | `.venv/Scripts/python.exe -m pytest tests/test_governance_docs.py -q`; `.venv/Scripts/python.exe scripts/validate_governance_docs.py` | Automated freshness scoring not yet implemented. | Active | Engineering |
| News intelligence | Unit | Deduplication, source reliability, fake-news suppression. | `.venv/Scripts/python.exe -m pytest tests/test_news_intelligence.py -q` | Historical event learning and provider aggregation. | Active | Engineering |
| Decision intelligence | Unit | Record completeness, validation, repository delegation. | `.venv/Scripts/python.exe -m pytest tests/test_decision_intelligence.py -q` | Lifecycle integration across all engine branches. | Active | Engineering |
| Telegram commands | Contract | Command access, keyboard callback safety, Gemini audit path. | `.venv/Scripts/python.exe -m pytest tests/test_command_contracts.py -q` | Full Bot API E2E for every command/callback. | Partial | Engineering |
| Outcome tracking | Unit/integration | Persistence, user performance IDs, TP parsing. | `.venv/Scripts/python.exe -m pytest tests/test_realtime_outcome_tracker_user_perf_ids.py tests/test_time_stop_outcome_persistence.py -q` | Live price stream stress testing. | Active | Engineering |
| Security | Contract/integration | Token/payment/webhook tests exist. | `.venv/Scripts/python.exe -m pytest tests/test_web_api_tokens.py tests/test_enterprise_features.py -q` | Full security audit, dependency scan, secret rotation drill. | Partial | Security/Engineering |
| Performance/load | Performance | Not yet formalized. | Planned | Load, stress, endurance, Telegram latency, worker throughput. | Open | Engineering |
| Observability | Contract | Prometheus text and endpoint tests exist. | `.venv/Scripts/python.exe -m pytest tests/test_telemetry.py -q` | Dashboard/alert integration tests. | Partial | Engineering |
