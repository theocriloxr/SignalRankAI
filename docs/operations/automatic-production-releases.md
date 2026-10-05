# Automatic production application releases

Production follows `fix/provider-discovery-readiness-20260923`. The final
`approve-production-source` job in `.github/workflows/ci.yml` advances the four
application source pins after every required certification job succeeds.

The controller checks the run ID, attempt, repository, workflow, push event,
branch and full SHA against GitHub's API. It requires both backend matrix jobs,
manifest, static, frontend, mobile and release certification to succeed. It
checks the current branch head twice and rejects superseded runs. A serialized
job prevents two approval operations from interleaving.

Automatic source promotion is limited to the paper/advisory phase: every role
must have the execution kill switch on and every live-money flag off. Unavailable
or ambiguous flag values block promotion. Once live-money operation is enabled,
new source requires a separately certified trading release; old financial
approvals cannot be carried forward by this application-only CI job. The
controller reads rendered settings in memory and never logs their values.

All four Railway triggers must use the release branch and Wait for CI. A single
explicit environment patch updates `EXPECTED_RELEASE_COMMIT`,
`EXPECTED_RELEASE_BRANCH` and the repository's `EXPECTED_ALEMBIC_HEAD` across
the four application services, without committing unrelated staged changes.
The job then queues each service at that exact SHA, using fresh configuration
snapshots. It does not redeploy old deployment snapshots or resolve a moving
`latestCommit` reference. Railway holds requests until the complete CI workflow
finishes successfully. An API failure fails the approval job; rerunning it is
idempotent with respect to the pins, but can create another deployment request.

Only the frontdoor runs the existing backup-gated controlled migration. The
other roles perform read-only schema admission with a bounded 600-second wait,
so they can start after the migrator rather than fail immediately on its old
schema. Missing backup/storage evidence still blocks migrations. Missing schema
or required columns still blocks workers after the wait. The frontdoor's
readiness healthcheck remains required.

## Credential setup

The GitHub environment `signalrank-production-release` must allow deployments
only from the release branch. Store an environment-scoped Railway project token
for project `5baa1c14-a748-4dc8-8eb6-411c621e56c3`, production environment
`05a014d1-73c1-485c-b767-e734c7ea2877`, as its encrypted environment secret
`RAILWAY_PRODUCTION_TOKEN`. Do not use a Railway account token or a repository
secret available to every branch. The job's GitHub token needs only Actions
read and Contents read. Missing credentials fail closed.

## Meaning of success

Approval success means the approved pins and deployment requests were accepted.
It does **not** mean all deployments are healthy or that live trading is
certified. Verify active deployment SHA and health for all four services, then
run a fresh release-bound soak. Failed CI leaves the prior healthy deployment
serving; Railway's skipped deployment in that case is intentional.

This automation never changes execution, prop, payout or kill-switch settings,
provider/broker certification, backup timestamps or storage observations.
Account-specific trading authorization remains independent. Production database,
Redis, backup and verification services are not application source deployments
and are excluded from this controller.

Railway references: [Wait for CI](https://docs.railway.com/deployments/github-autodeploys)
and [project-token authentication](https://docs.railway.com/integrations/api).
