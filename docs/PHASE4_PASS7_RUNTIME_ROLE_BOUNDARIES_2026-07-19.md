# Phase 4 Pass 7 — Runtime Role Boundaries

Date: 2026-07-19  
Status: Foundation complete; compatibility migration remains active.

`runtime.roles` defines the eight supported roles (web, bot, engine, delivery,
outcome, analytics, scheduler, and all/dev). `runtime.dispatcher` lazily starts
an adapter and preserves the legacy `worker` alias. Importing role metadata does
not create a DB pool or start background work. `scripts/architecture_smoke.py`
checks role imports, dispatcher coverage, safe defaults, and main-entrypoint
ownership. The legacy monolith remains the all/dev composition until staged
behavior comparison and deployment canaries approve further ownership moves.

Verification: `tests/test_phase4_pass7_runtime_roles.py` (6 passed),
`python scripts/architecture_smoke.py` (all checks passed).
