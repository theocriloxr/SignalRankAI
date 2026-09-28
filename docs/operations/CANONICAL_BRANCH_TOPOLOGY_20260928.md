# SignalRankAI Canonical Branch Topology — 2026-09-28

## Authoritative branches

- `main`: production source of truth. Only staging-certified commits are promoted here.
- `staging`: integration/pre-production source of truth. All new work lands and is certified here before production promotion.

Both branches were consolidated from the 2026-09-25 master-blueprint line after auditing the advanced provider, MT5/multi-account, hardening, AI/OpenAI, staging and isolated production-hotfix branches.

## Preserved history

No historical work was deleted. Important previous release lines are retained under archive branches, including:

- `archive/main-pre-canonical-20260928`
- `archive/staging-source-pre-canonical-20260928`
- `archive/provider-discovery-readiness-pre-prod-hotfix-20260928`

Older hardening/provider/MT5 branches that are ancestors of the canonical tree remain available for forensic comparison but must not be used as deployment sources.

## Promotion rules

1. Build and test on `staging`.
2. Staging source gate must identify branch `staging` and the exact expected commit.
3. Schema gate must pass at the repository Alembic head.
4. Frontdoor, engine, worker/delivery and analytics roles must all start on the exact same commit.
5. Financial/execution flags remain fail-closed unless the corresponding live-provider certification is current.
6. Public health alone is not release evidence. Promotion requires the repository Docker gate, release provenance, runtime role/source proof and relevant provider/E2E proof.
7. Promote the exact certified staging SHA to `main`; never merge an unbounded backlog directly into production.
8. Production source gate must identify branch `main` and the exact promoted commit.

## Current product baseline

The canonical tree includes multi-asset signals; Telegram/web identity and entitlement parity; paper, portfolio and performance workspaces; provider-backed market search; watchlists/alerts; VIP research; billing/Paystack confirmation; transactional-email outbox; multi-account MT4/MT5/MetaApi and exchange connection registry; per-account execution/risk/PROP policy; canonical broker ledger/reconciliation; OpenAI + fallback AI routing; adaptive learning governance; and owner/admin diagnostics.

The web workstation additionally exposes the canonical Telegram command catalogue and operator controls so capabilities are discoverable outside chat. Owner mutations remain confirmed, audited and fail-closed.

## Deployment topology

Staging and production must remain isolated at the environment/data/provider level. The normal decomposed roles are:

- frontdoor/web
- engine
- worker/delivery
- analytics

Each role must use its environment's own Postgres/Redis/provider credentials. Never point staging services at production state merely to make a readiness check pass.

## Current external infrastructure note

Railway service source branches still need to be connected to these canonical branch names where an older source branch is configured. Changing a GitHub branch pointer alone does not change the source branch selected in an existing Railway service. Until that source setting is updated, keep the exact release-source gate enabled and do not claim environment parity.
