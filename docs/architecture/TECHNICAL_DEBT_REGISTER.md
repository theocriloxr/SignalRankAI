# TECHNICAL_DEBT_REGISTER — SignalRankAI

Priority: P0 = blocks certification, P1 = must fix before scale, P2 = hygiene.

| ID | Item | Area | Priority | Note |
|---|---|---|---|---|
| TD-001 | `core/event_bus.py` legacy pub/sub duplicates the modern stream layers | events | P2 | Keep for compatibility; migrate consumers to `DurableEventStream`/`RecoverableStream` |
| TD-002 | `EventBus.publish` fallback queue is unbounded in-memory | events | P1 | Memory outbox is contract-only; production must use Redis/Postgres outbox |
| TD-003 | `core/paper_ledger.py` stores positions in `RuntimeState` JSON blobs | paper | P1 | Target a dedicated position table with index (user_id, asset, status) |
| TD-004 | `PaperLedger.close_position` recomputes balance from a single entry | paper | P2 | Reconcile from ledger entries rather than mutable balance |
| TD-005 | `_minimal_scheduler_mode` branches duplicate registrations | scheduler | P1 | Registry tests treat them as exclusive; runtime still needs one owner per env |
| TD-006 | Provider adapters exist as declarations only | providers | P1 | See `BLOCKED_EXTERNAL_REQUIREMENTS.md` |
| TD-007 | Financial ledger is in-memory; migration `0029_live_financial_ledger` tables unused | ledger | P1 | Wire `core/financial_ledger.py` to the `0029` schema next |
| TD-008 | No SAST/DAST/SBOM pipeline wired into CI | security | P1 | Repository documents checks; CI execution pending |
| TD-009 | One-minute public delivery freshness vs queue deadline | delivery | P1 | Policy: disable public 1m delivery until immediate path meets p95 < 5 s |
| TD-010 | `requirements/` split across many YAML files | packaging | P2 | Validate pinned sets periodically |
