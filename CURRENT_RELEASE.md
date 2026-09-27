# Current SignalRankAI Release

```text
Version: 1.5.1
Patch level: blueprint-hardening-20260926
Fingerprint: signalrank-blueprint-0045-multi-account-execution-hardening-20260926
Repository Alembic head: 0045_mt5_credential_retirement
Staging schema: certified at 0045_mt5_credential_retirement
Staging topology: decomposed frontdoor + engine + delivery + analytics
Staging live-money posture: disabled / fail-closed
Current verified frontdoor release: d09535105bf44ca9c53008007394d9f804104a81
Current read-only demo preflight: e80fa087-d487-40fc-859e-76df71a3b7b7 (BLOCKED_EXTERNAL; 0 canonical broker connections)
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
in staging: **0**. Frontdoor deployment
`33c9b981-29c0-4fef-890f-b314e817a566` at `d09535105bf44...`
retains the explicit fail-closed **Prepare DEMO certification** workflow and
also aligns Telegram MT5 linking/status copy with the same account-safety
contract: linking/provisioning does not grant execution permission;
provider-backed read-only verification/reconciliation → bounded
`DEMO/MANUAL` policy → execution remains OFF. Clean-room marker
`d09535105bf44...` passed Alembic 0045/schema/provenance and **465 targeted
tests**, including MT5 linking-copy safety; the frontdoor image passed **356
build tests** plus readiness checks. Runtime ownership is frontdoor-only
(http+Telegram on; engine+worker off), webhook pending=0, and /healthz=200.
Fresh read-only preflight `e80fa087-d487-40fc-859e-76df71a3b7b7` still found
zero canonical accounts and confirmed activation=false, orders=0 and
secrets_returned=false. Demo execution certification therefore remains blocked
only until an explicitly owned demo account is linked and the external broker
lifecycle is proven. Environment-level broker credential variables are not
treated as account ownership or execution authorization.

Current completion boundary:

- `FINAL_COMPLETION_REPORT_20260926.md`
- `BLOCKED_EXTERNAL_REQUIREMENTS_20260926.md`
- `docs/security/THREAT_MODEL.md`
- `docs/architecture/REQUIREMENTS_TRACEABILITY_MATRIX.md`
- `docs/evidence/STAGING_0045_CREDENTIAL_RETIREMENT_20260926.md`
- `docs/evidence/STAGING_PROVIDER_CERTIFICATION_20260926.md`

Older R4/v1.5.1 reports remain historical evidence and must not be used as the
current deployment/schema authority.
