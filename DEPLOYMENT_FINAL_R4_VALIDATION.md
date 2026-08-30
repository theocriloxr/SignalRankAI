# SignalRankAI v1.5.1 — Deployment Final R4 Validation

Date: 2026-08-07
Patch level: `deployment-final-r4`

## Live staging evidence carried forward

Owner-provided staging terminal evidence proves the PostgreSQL migration chain
completed through `0038_account_security_product` and the required-schema gate
returned `PASS` with no missing unified-platform objects. No credentials or
connection strings from that evidence are stored in this archive.

## R4 fixes validated

- asyncpg-safe, typed and rerunnable subscription-price seed;
- complete canonical feature entitlement persistence;
- PostgreSQL read-back bootstrap verification;
- deterministic catalogue commit before optional provider discovery;
- self-pair/non-tradable instrument rejection;
- profile-to-registry asset-class alias normalization;
- DB-backed structural and strict runtime certification;
- Railway R4/head post-deployment proof;
- automated Railway soak log/status/metrics certification.

## Hermetic local certification

`artifacts/r4-local-complete/complete_system_test_report.json` records:

```text
Overall: PASS
Evidence scope: HERMETIC_LOCAL_ONLY
Pytest passed: 1365
Pytest skipped: 1
Pytest failed: 0
Pytest errors: 0
Unparsed batches: 0
```

The complete-system orchestration also passed compilation, environment
contracts, schema audit, architecture smoke, DB-session audit, governance
validation, secret scan, production-readiness checks, runtime-config snapshot,
Railway simulation, delivery fanout load, and static provider certification.

A fresh rerun of the final governance/provider batch passed 115/115 tests on
the first attempt after governance artifacts were current.

## Independent final checks

- Alembic heads: exactly one, `0038_account_security_product`.
- Governance artifact check: PASS.
- Governance document validation: PASS, 24 documents.
- Secret scan: PASS, 0 findings.
- Python compilation: PASS.

## What this does not claim

This local evidence does not prove a fresh real Telegram delivery, Paystack
transaction, SMTP delivery, mobile push, provider SLA, 24-hour elapsed staging
soak, backup/restore drill, penetration test, legal approval, or any guaranteed
trading win rate. R4 provides deterministic commands to collect several of
those runtime proofs once the corresponding real events exist.
