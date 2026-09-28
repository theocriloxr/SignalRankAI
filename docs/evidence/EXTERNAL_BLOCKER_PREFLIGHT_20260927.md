# SignalRank External Blocker Preflight — 2026-09-27

## Scope

This evidence records the fail-closed external-activation preflight against the
staging environment. The preflight does **not** activate providers, make a scale
claim, enable copy trading, or enable the public marketplace.

- source branch: `codex/signalrank-master-blueprint-20260925`
- preflight source commit: `49b98a5bc6ca1f91da809f18479352360b95b491`
- staging preflight deployment: `3a95addd-510d-47d2-acd8-f2257f529ea4`
- contract: `requirements/external_activation_requirements.yaml`
- executable: `scripts/external_blocker_preflight.py`
- all checks returned `BLOCKED` / exit code `2`
- every check reported `activation_performed=false`

No credential values were emitted or retained in this evidence.

## Optional providers — SR-PROVIDER-008

### Financial Modeling Prep

Status: `BLOCKED`.

Missing external evidence:

- entitlement approval;
- live market-data certification;
- redistribution-rights approval.

The staging preflight found a configured provider secret reference, so
`required_provider_secret_missing` was **not** a blocker. This does not prove
that the plan/entitlement is suitable.

### Alpha Vantage

Status: `BLOCKED`.

Missing external evidence:

- entitlement approval;
- request-budget approval;
- live market-data certification;
- redistribution-rights approval.

The staging preflight found a configured provider secret reference, so
`required_provider_secret_missing` was **not** a blocker. This does not prove
that the plan/entitlement is suitable.

### OANDA

Status: `BLOCKED`.

Blockers:

- required provider secret missing;
- required provider config missing: `OANDA_ACCOUNT_ID`;
- intended-environment approval missing;
- market-data certification missing;
- regional-access approval missing.

No OANDA gate was activated by the preflight.

### FRED

Status: `BLOCKED`.

Blockers:

- required provider secret missing;
- attribution-requirements approval missing;
- live macro-data certification missing;
- vintage/point-in-time discipline certification missing.

No FRED gate was activated by the preflight.

## Representative scale — SR-SCALE-003

Status: `BLOCKED`.

The empty/non-certification input was correctly rejected for all mandatory
large-scale proof dimensions:

- invalid certification kind;
- wrong scale profile;
- certification is not PASS;
- claim is not allowed;
- actual concurrency below 20,000;
- configured load-summary concurrency below 20,000.

Result: `capacity_claim_allowed=false`.

This confirms the repository cannot accidentally turn unit/integration tests
into a 100k-user capacity claim.

## Public copy marketplace — SR-MARKETPLACE-001

Status: `BLOCKED`.

Missing external trust/legal/commercial evidence:

- publisher identity review;
- follower consent and revocation;
- suitability review;
- transparent performance disclosure;
- abuse-controls review;
- jurisdiction approval;
- commercial-terms approval.

Missing runtime certification:

- account-risk certification;
- copy-execution certification;
- duplicate-order protection certification;
- kill-switch certification.

Result: `public_marketplace_claim_allowed=false`.

## Conclusion

The three `BLOCKED_EXTERNAL` requirements remain correctly fail-closed.
Nothing in this preflight changes the current demo-first / later-prop workflow,
and no live-money or public marketplace capability was activated.
