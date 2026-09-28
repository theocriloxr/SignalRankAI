# SignalRankAI Canonical Branch Topology — 2026-09-28

## Canonical branches

- `main` is the single production source of truth.
- `staging` is the single staging source of truth.
- New product work should branch from `staging`, be certified there, then be promoted to `main`.
- Historical feature/release/hotfix branches are evidence only once their functionality is merged or explicitly superseded.

## Canonical commits at consolidation

At the time this document was written:

- production `main`: `b479cb0894c18901dfee02c4c8f3b069c933a1fc`
- staging: `d28607a3f1e5ed852c270be18cfe8fadac3e273a`

The staging commit differs from main only by its staging rollout marker.

## Railway source aliases

Railway's connected-service source selector could not be changed through the available connector because the Railway Agent quota was exhausted. To keep deployment safe without recreating services or copying redacted secrets:

- production Railway services remain connected to `fix/provider-discovery-readiness-20260923`;
- staging Railway services remain connected to `codex/signalrank-master-blueprint-20260925`.

Those branches are maintained as exact aliases of `main` and `staging` respectively. Release-source gates remain pinned to the actual Railway source branch **and** the exact canonical commit.

One manual Railway UI cleanup remains:

1. Change the four production SignalRank application services' source branch to `main`.
2. Change the four staging SignalRank application services' source branch to `staging`.
3. Preserve domains, variables, regions, build/deploy commands and watch patterns.
4. Keep production watch pattern `production-release/**`.
5. Keep staging watch pattern `staging-rollout/**`.
6. After the source selector changes, change `EXPECTED_RELEASE_BRANCH` to `main` in production and `staging` in staging while keeping `EXPECTED_RELEASE_COMMIT` pinned to the intended SHA.

Until that UI cleanup occurs, the aliases are intentionally kept byte-for-byte identical to the canonical branches.

## Consolidated / superseded lines

The following major workstreams have been incorporated into the canonical tree and must not be independently deployed:

- master blueprint and cross-chat implementation directives;
- full-platform hardening and production integration;
- provider discovery/readiness;
- MT4/MT5 multi-account UX, account-scoped risk and PROP policy;
- staging-certified / MetaApi-authorized release lines;
- live site session/account/billing hardening;
- OpenAI/Gemini governance and owner/operator controls;
- final cross-channel Telegram/web parity;
- canonical workstation redesign.

Older AI branches contain a small number of branch-only commits, but their product behavior is superseded by newer canonical implementations and tests. They are not wholesale-merged because doing so would reintroduce obsolete provider/status contracts and older command-policy assumptions.

## Promotion rule

A branch name is not release evidence. Promotion requires:

1. exact source SHA;
2. single Alembic head and schema gate;
3. deterministic Docker/repository gate;
4. staging runtime-role admission;
5. `/healthz` and `/readyz` success;
6. no unexplained entitlement, delivery, outcome, performance, provider or broker-account regressions;
7. production financial/execution gates remaining fail-closed unless explicitly and separately authorized.
