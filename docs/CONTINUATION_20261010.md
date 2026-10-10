# SignalRankAI continuation — 2026-10-10

Continuing draft PR #189 from published source `0d438360969c44af6ce889ac507098fec56b0368`
(tree `11083e5bd0f21a795ef07eab324ca4fc4f2d9d21`) on the actual release base
`fix/provider-discovery-readiness-20260923`.

The owner supplied the previously inaccessible research source. Its complete
text, hash, independent review, mathematical criticisms and concept dispositions
are preserved in `docs/specs/20261010/research-source-supplied.md` and
`docs/research-source-review-20261010.md`. The supplied-content review is complete;
Google Docs revision/authorship identity is not independently authenticated.

## Implemented successor

- Revision `0051_strategy_health_baselines`: immutable approved delivery
  baselines, fixed owner-selected decay conditions and append-only health events.
- Baselines derive from actual eligible confirmed-delivery outcomes, require
  explicit owner identity/confirmation and bind profile version/configuration.
  The request cannot supply metrics, approval time or approver identity.
- Forward evidence excludes decisions made before approval, including decisions
  that close after it. Expectancy, PF, drawdown/duration and optional qualified
  calibration comparisons retain missing/invalid evidence and reason codes.
- Required absent/invalid comparison evidence cannot receive cache approval.
  Publication requires a fresh matched immutable surveillance receipt; arbitrary
  publication calls cannot renew old health evidence. Insufficient forward
  samples may collect CANARY evidence under the existing promotion policy.
- Breaches suspend adaptive profiles under the existing lifecycle lock; approval
  cannot silently restore a suspended profile or reset its baseline.
- Telegram promotion obtains approved kill-condition evidence from the stored
  baseline rather than a research-result boolean. The web API enforces owner
  approval and owner/admin reads. Operator tables expose comparison states and
  forward counts with escaped reason text and mobile card bounds.
- Current-head release/schema contracts advance to 0051. Startup/runtime guards
  inspect both health tables and their four enabled immutable-history triggers.
  Earlier retained deployment reports are not rewritten as 0051 evidence.

## Verification before publication

Local focused checks passed: 141 tests spanning baseline boundaries, owner
authorization, health lifecycle, startup admission and release provenance.
The broader research/current-schema selection passed 290 tests. A final focused
rerun covers the subsequent missing-PF and receipt-freshness adjustments.
Critical Pyright and undefined-name Ruff passed; the portable full Alembic
release-chain verifier passed with head 0051 and all 16 required SQL markers.
JavaScript syntax and Git whitespace checks passed.

Initial local checks caught a misplaced import indentation and stale 0050
mocked revision values. Both were repaired; their earlier failed check output
was retained locally while the passing successors were run. New PostgreSQL
cases cover immutable history, idempotent retries, actual forward decay,
configuration binding and physical startup/runtime guard rejection.

An isolated local PostgreSQL server was unavailable in this process environment.
Hosted CI must run those cases with its required real PostgreSQL service and
both backend Python versions. The published source/head/tree, exact hosted run
IDs, outcomes and browser artifact identity are recorded in PR #189 metadata.
No mocked or skipped SQL check substitutes for that required evidence.

## Remaining scope

The research directive remains in progress. Broker/paper/portfolio baselines,
instrument execution/capacity stress, point-in-time universes, rich regime
qualification, all search-call-site integration, portfolio survival/interaction,
full approval/recovery UI, telemetry/alert retention and the other runbook gaps
remain open. Customer UX/design, multi-broker/native acceptance, two complete
audits and a fresh clean release observation remain unfinished.

The prior exact source passed backend/frontend/static/browser checks, but mobile
audit failed on four high rows in the node-forge/Expo signing graph. This successor
must be checked again; it contains no dependency waiver or vulnerability bypass.
Live-money execution stays disabled and production readiness is not certified.
