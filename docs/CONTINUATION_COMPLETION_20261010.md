# Completion continuation from PR #189

Start: `e18034312bb1ab6fac5ff3d4a4af68b93ab472ac`, tree
`501fa6d3d8f33cf6ca40837708ed26d27b309388`, recovery branch
`fix/release-recovery-20261008`. Both that checkpoint and PR base `c7684b34`
are ancestors. All eleven recovery commits are included. The original root
checkout and dirty October 7 scratch work are preserved; this work uses
`.pytest-tmp/completion-20261010`. No duplicate cherry-pick or failing release
merge was performed. PR #189 remains draft.

## Changes

Adaptive dataset reads now freeze an observation cutoff and reject future
decision/outcome/correction availability. Sequence references record actual
process capture time separately from unverified provider publication vintages.
The worker loads their scope, timing and provider metadata; canonical dataset
fingerprints bind those values. Invalid provenance, post-decision capture and
unclosed bars block WFO. Unknown legacy metadata remains unverified; another
missing field cannot conceal a known violation. Ambiguous timestamp aliases do
not acquire an invented bar-open convention. Snapshot rows and provenance have
hard budgets; oversized inputs reject rather than silently truncating evidence.

The local PostgreSQL server uses Africa/Lagos. This exposed a pre-existing
baseline bug: NOW() inherited local time when cast into canonical UTC-naive
columns, making valid approvals appear future-dated. Lifecycle serialization
now sets transaction-local UTC in the same round trip as its advisory lock.
Real PostgreSQL checks cover Lagos, New York and Tokyo, approvals, receipts,
commit and rollback. Existing immutable history is not rewritten or shifted.
Any previously invalid historical baseline still needs governed revalidation.
No migration, execution permission, health reset or automatic resume is added.

The completion matrix preserves exact text/subrequirements for all 560 numbered
specification sections and all 431 overlapping master clauses. Its separate
reviewed dispositions preserve missing acceptance instead of inferring success
from files, test names or historical labels. A required manifest gate detects
source drift, omitted clauses and stale generated output. Original attachment
hashes use CRLF, while Git preserves LF: the verifier accepts only that explicit
lossless conversion. The October 10 supplied research source and review are
current; older source-unavailable statements remain historical. Most individual
implementation reviews remain AUDIT_PENDING; this inventory is not a completed
991-item audit or a test count.

## Retained verification

The starting SHA's push run 38056860381 and PR run 38056864292 passed manifest,
both backend versions, frontend, static and research browser. Mobile failed
four high node-forge/Expo audit rows; aggregate release failed and production
approval was skipped. The primary advisory still lists no patched version:
https://github.com/advisories/GHSA-86w9-cpqp-85rv . No waiver or renamed vulnerable
package is introduced.

Focused local sequence/dataset/research checks passed 112 cases before the
additional inventory/budget cases. Inventory/availability checks then passed
38 cases with an owned temporary directory. The first PostgreSQL snapshot run
had three assertion failures because the test read a nested field instead of
the canonical stored result; the corrected four-case successor passed. The
expanded research run passed 408 cases and failed the baseline timezone case.
After its repair, all four baseline/timezone cases passed. Required broad and
hosted successor acceptance remains necessary; overlapping counts are not summed.

Early local inventory fixtures encountered the sandbox's inaccessible global
pytest directory and a missing local parent directory. An explicitly owned
workspace temporary directory resolved both; these were not accepted as passes.
Exact frozen source, later checks and publication results must be recorded in
the successor handoff/PR. Local artifacts remain under
`artifacts/ui-refresh-20261003/` in the root workspace, named by owned database.

## Refreshed infrastructure observations

At 2026-10-10T16:21:30Z, all four production application roles had active
SUCCESS deployments of `8f8583933a853a54ba1b3585610ee466903c08fc`.
That is the serving historical release, not recovery-branch deployment proof.
No production configuration or financial activation was changed.

A separate staging project now exists:
`a0f2739b-0922-4489-be0e-57ce9922ca3e`, environment
`31ed8d28-88ef-4d51-b983-e3a70573ada3`. It contains separate PostgreSQL and
two Redis resources plus frontdoor, engine, delivery, API and web services.
The API reported no active deployment for any of these eight resources.
Inspected application sources follow `deploy/signalrank-certification-20261008`
at `7c8941e80e260047e51cad73f01a74e854b5cb16`, rather than the recovery SHA.
The 16:32:22Z read-only configuration refresh confirmed all six required
production execution/payout flags explicitly false and the kill switch true
across all four roles. Some additional equivalent flags are unset; an unset
variable is not evidence of enabled execution. Their effective defaults still
require inspection against the serving historical source.

Staging's four backend-shaped services have the kill switch true and the other
inspected financial flags false, but PROP_EXECUTION_ENABLED and
EXPECTED_ALEMBIC_HEAD are unset. The web service has a smaller configuration
and needs its actual role identified. None has a configured deployment trigger.
An analytics-role mapping, deployment history, credentials and resource/queue/
broker separation must be inspected before staging activation. These observations
are retained in the local completion-configuration-20261010.json artifact.
No staging soak or external acceptance was performed by these read-only queries.

## Next work in the mandated order

Continue R1's historical universes/vintages, immutable replay inputs and calendar
qualification, then R2's complete feature/strategy audit and R3–R17 in the full
October 10 prompt. Do not certify survivorship, feature repainting, venue costs,
regimes, portfolio interaction or profitable edge from captured bar timing.
Continue customer UX, complete web/native design, multi-broker authority and
sections 126–363 individually. The self-improving ecosystem remains after those
foundations. The matrix marks unreviewed acceptance explicitly.

Resolve mobile security only with an actual safe supported upstream patch or
legitimate tested replacement. Before promotion, run all required gates on the
published immutable SHA, prepare the isolated staging resources and all roles,
verify current-head migrations/full restore/storage, every enabled market class,
real delivery/failure drills, actual authorized demo broker lifecycle and
installed Android/iOS journeys. Start a fresh 24–72-hour staging observation
only when that candidate is eligible. Retain old failed/degraded observations.
Two complete final audits and later explicit human live-pilot approval remain.
Financial production flags must remain zero and the kill switch one throughout.
