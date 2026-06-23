# SignalRankAI Full Codebase Audit & Refactor TODO

## Completed
- [x] Refactor `config.py` with strict typing + backward compatibility
- [x] Refactor `db/database.py` compatibility wrappers
- [x] Refactor `db/access.py` DB-safe tier resolution + defensive logging
- [x] Refactor `db/session.py` hardened URL resolution + async session factory + compatibility exports
- [x] Validate DB tranche compile + URL precedence checks

## In Progress: `engine/core.py` phased refactor
- [ ] Phase 1: Structural safety pass
- [ ] Phase 2: DB hygiene pass
- [ ] Phase 3: Idempotency/state-machine pass
- [ ] Phase 4: Performance pass
- [x] Phase 5: Validation pass (compile + targeted runtime checks)

## In Progress: `engine/cycle_queue.py` refactor
- [ ] Harden input normalization and duplicate handling
- [ ] Add defensive guards for refresh interval and batch size
- [ ] Correct round accounting counters
- [ ] Add non-breaking observability helper(s)
- [ ] Validate with compile + targeted tests

## Next
- [ ] Continue file-by-file through `engine/` after `core.py` and `cycle_queue.py`
- [ ] Continue file-by-file through remaining project directories
