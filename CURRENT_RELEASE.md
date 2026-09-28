# Current SignalRankAI Release

```text
Version: 1.5.1
Patch level: blueprint-hardening-20260926
Fingerprint: signalrank-blueprint-0045-multi-account-execution-hardening-20260926
Repository Alembic head: 0045_mt5_credential_retirement
Staging schema: certified at 0045_mt5_credential_retirement
Staging topology: decomposed frontdoor + engine + delivery + analytics
Staging live-money posture: disabled / fail-closed
Current verified frontdoor release: c4d1e6d6ec5e968497d080b7fc288704b561bbd4
Current read-only demo preflight: 9757cac0-7f68-466a-a9a0-8e458f1390cd on 3656eabaf56a... (BLOCKED_EXTERNAL; 0 canonical broker connections)
Production promotion: separate controlled gate; not implied by staging health
```

The current release line includes the 2026-09-25/26 multi-user,
multi-account, execution-safety, broker-credential, ML-lineage, delivery,
runtime-ownership, dependency-lock and supply-chain provenance hardening.

Current deterministic release controls include:

- exact release-source admission before business work;
- Alembic/schema admission before business work;
- locked Python dependency graph with `--no-deps` installation and
  `pip check`;
- Railway image build regression/readiness gate;
- zero-secret clean-room compile, migration-chain, schema-audit and targeted
  safety/regression verification;
- deterministic CycloneDX SBOM and release-provenance generation/self-check;
- role-specific staging rollout isolation;
- global/live-money execution and payout gates independent of ordinary health;
- live/public certification for every enabled staging market-data provider,
  with optional uncertified providers explicitly disabled behind operator gates.

The shared staging database and all four long-lived staging roles have passed
the `0045_mt5_credential_retirement` admission contract with real-money
execution disabled. Production remains a separate controlled rollout and must
satisfy its own backup, release, provider, demo/canary, legal and owner
authorization gates.

Staging disaster recovery is independently verified through a full isolated
PostgreSQL restore drill. Canonical demo broker connections currently present
in staging: **0**. The latest secure Broker Hub handoff is live on frontdoor
deployment `68219e01-9b4a-48a8-8abb-9e4372f634f9` at
`c4d1e6d6ec5e...`. Telegram no longer collects broker passwords in chat; users
are handed off to the authenticated Broker Hub, where canonical ownership,
credential-envelope storage, read-only verification and the explicit
fail-closed **Prepare DEMO certification** workflow apply. Linking/provisioning
does not grant execution permission; provider-backed read-only
verification/reconciliation → bounded `DEMO/MANUAL` policy → execution remains
OFF.

Clean-room `c4d1e6d6...` passed Alembic 0045/schema/provenance and **469
targeted tests**; the frontdoor image passed **356 build tests** plus all 12
readiness checks. Runtime ownership is frontdoor-only (http+Telegram on;
engine+worker off), webhook pending=0, and /healthz=200. The post-secure-link
read-only preflight `9757cac0-7f68-466a-a9a0-8e458f1390cd` on marker
`3656eabaf56a...` still found zero canonical broker connections and confirmed
activation=false, orders=0 and secrets_returned=false. Demo execution
certification therefore remains blocked only until an explicitly owned DEMO
account is linked and the external broker lifecycle is proven.
Environment-level broker credential variables are not treated as account
ownership or execution authorization.

Current completion boundary:

- `FINAL_COMPLETION_REPORT_20260926.md`
- `BLOCKED_EXTERNAL_REQUIREMENTS_20260926.md`
- `docs/security/THREAT_MODEL.md`
- `docs/architecture/REQUIREMENTS_TRACEABILITY_MATRIX.md`
- `docs/evidence/STAGING_0045_CREDENTIAL_RETIREMENT_20260926.md`
- `docs/evidence/STAGING_PROVIDER_CERTIFICATION_20260926.md`

Older R4/v1.5.1 reports remain historical evidence and must not be used as the
current deployment/schema authority.
