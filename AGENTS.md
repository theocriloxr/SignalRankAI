# SignalRankAI continuation contract

Before changing this repository, read `docs/release/MASTER_EXECUTION_CONTRACT.md`,
`docs/release/baseline.json`, `docs/release/RELEASE_BLOCKERS.md`,
`docs/release/BRANCH_RECONCILIATION.md` and `docs/release/COMPLETION_EVIDENCE.md`.
Use `docs/release/requirements.json` for complete source/interface accounting;
the readable matrix is `docs/release/REQUIREMENTS_TRACEABILITY.md`.

Do not infer verification from historical reports, closed PRs, code presence,
mock fills, provider catalogue entries, or a green health endpoint. Record the
exact tested revision, environment, command, exit result, log and evidence scope.
Preserve source clauses and IDs when revising their dispositions.

Never enable or change real-money trading/payout permissions as part of baseline
recovery. Never run migrations, test suites, destructive cleanup, broker calls,
billing operations or restore drills against production. Use a separate owned
test database and sanitized environment. Do not print credentials.

Preserve other worktrees and uncommitted user changes. Integrate through reviewed
commits and a PR; never force-push or overwrite `main`. Review the active GitHub
ruleset and deployment triggers before any remote write. A local branch or draft
PR does not mean a production deployment is authorized.

After a change: run relevant behavioral tests, regenerate/check the release
inventory and existing governance artifacts when their inputs change, update the
six release documents and leave an exact handoff commit. Frontend work also obeys
`frontend/AGENTS.md`. Do not rewrite historical source documents to manufacture
current completion evidence.
