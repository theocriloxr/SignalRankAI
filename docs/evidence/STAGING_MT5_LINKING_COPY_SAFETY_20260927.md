# Staging MT5 Linking Copy Safety — 2026-09-27

## Scope

This evidence records the staging correction that aligns Telegram MT4/MT5
onboarding language with SignalRank's canonical fail-closed execution model.

A broker connection or provisioned MetaApi account is **not** execution
permission.

## Repository change

Certified rollout commit:

`d09535105bf44ca9c53008007394d9f804104a81`

The active Telegram command implementation in
`signalrank_telegram/commands.py` now states that:

- linking does not enable trading;
- provider provisioning does not grant execution permission;
- `/verifybroker` is the next read-only verification step;
- DEMO accounts use the web **Prepare DEMO certification** workflow;
- that workflow applies a bounded `DEMO/MANUAL` policy while execution remains
  OFF;
- execution may only be enabled separately after verification, healthy
  reconciliation, policy checks and explicit confirmation.

The inactive legacy helper `signalrank_telegram/mt5_commands.py` is kept
wording-compatible so a future import cannot reintroduce unsafe onboarding
language.

The inaccurate phrase `AES-256 (Fernet)` was removed. User-visible copy now
refers to the configured credential vault rather than claiming a specific
cipher construction that the UI does not need to expose.

## Deterministic verification

Clean-room deployment:

`84547621-9f22-429f-8d22-3493ebe9c2f9`

Results:

- compile: PASS;
- Alembic release chain: PASS at
  `0045_mt5_credential_retirement`;
- schema audit: PASS;
- release provenance: PASS for `d09535105...`;
- targeted pytest: **465 passed**;
- `tests/test_mt5_linking_copy_safety.py` included in the clean-room list;
- final marker: `CLEANROOM_PASS`.

The regression rejects copy such as:

- `execute instantly`;
- `Ready for signal execution`;
- `one-click MT5 execution`;
- `Execution bridge: READY`;
- misleading `AES-256` wording in this onboarding path.

## Staging rollout

Frontdoor deployment:

`33c9b981-29c0-4fef-890f-b314e817a566`

Release commit:

`d09535105bf44ca9c53008007394d9f804104a81`

Build evidence:

- **356 tests passed**;
- release provenance: PASS;
- all 12 production-readiness checks: PASS.

Runtime evidence:

- release-source gate: PASS;
- Alembic current/head:
  `0045_mt5_credential_retirement`;
- database schema admission: PASS;
- runtime ownership:
  `mode=frontdoor`, `http=true`, `telegram=true`,
  `engine=false`, `worker=false`;
- signal engine: DISABLED on the frontdoor;
- worker/outcome ownership: DISABLED on the frontdoor;
- Telegram handler readiness: **209 handlers**, ready=true;
- webhook registered at the staging ingress;
- webhook startup state: pending=0, no error;
- `GET /healthz`: HTTP 200.

Role-isolation evidence for the same rollout marker:

- engine deployment: SKIPPED;
- delivery deployment: SKIPPED;
- analytics deployment: SKIPPED.

No production rollout was triggered.

## Remaining external boundary

This correction does not change the broker-demo certification boundary.

Latest read-only staging preflight still has:

- canonical broker connections: **0**;
- activation performed: false;
- orders placed: 0;
- secrets returned: false.

The next valid step is for an authenticated user to connect one explicitly
owned DEMO account through the canonical web/Telegram account-linking flow.
Environment-level credentials must not be silently adopted as account
ownership.
