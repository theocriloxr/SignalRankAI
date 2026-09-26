# Staging 0045 Credential Retirement Evidence — 2026-09-26

## Scope

This evidence records the staging-only rollout of:

- `0044_broker_credential_envelope`;
- `0045_mt5_credential_retirement`;
- versioned, account-bound broker credential envelopes;
- duplicate MT5 password-ciphertext retirement;
- long-lived analytics, engine, delivery and frontdoor admission on the
  resulting schema.

Production was not migrated or activated by this staging evidence.

## Schema and inventory proof

Certified staging schema/inventory deployment:

- Railway deployment: `a41c2703-63a8-4d60-9437-f85c349f7823`
- database Alembic head: `0045_mt5_credential_retirement`
- schema gate: PASS
- missing required schema objects: none

Counts-only broker credential inventory:

- `BROKER_INVENTORY_STATUS=PASS`
- `BROKER_CANONICAL_ENVELOPE_V1_ROWS=0`
- `BROKER_CANONICAL_LEGACY_ROWS=0`
- `MT5_LEGACY_SECRET_ROWS=0`
- `MT5_DUPLICATE_SECRET_ROWS=0`
- `MT5_UNMIGRATED_SECRET_ROWS=0`
- `BROKER_LIVE_MONEY_SECRET_READINESS=1`

Interpretation: staging contains no residual legacy broker credential ciphertext
or duplicate MT5 password ciphertext. It also currently contains no persisted
`envelope_v1` broker credential rows, so this evidence certifies the storage
and retirement boundary but does **not** claim a real broker/demo credential has
already been exercised end-to-end.

The inventory is deliberately counts-only. It does not select, decrypt, print
or persist broker secret values.

## Credential-envelope contract

Canonical broker credentials are written through
`services/broker_credentials.py`.

The version-1 envelope binds encrypted material to:

- canonical `user_id`;
- immutable `connection_id`;
- normalized provider/platform;
- normalized connector;
- credential revision;
- key ID and envelope version.

Copying ciphertext to another user, connection, provider or connector fails
closed during decryption. Keyrings support reading an older key while all new
writes/rotations use the configured active key. Credential rotation disables
execution until the account is deliberately re-enabled and records an audit
event without exposing secret material.

`0045_mt5_credential_retirement` makes
`mt5_credentials.password_encrypted` nullable and scrubs duplicate legacy
password ciphertext only when an equivalent canonical MT5/MetaApi
`envelope_v1` connection exists. The migration never decrypts a credential.

## Long-lived staging role proof

All four long-lived roles admitted against the same staging database at
`0045_mt5_credential_retirement`.

| Role | Railway deployment | Git SHA | Runtime proof |
|---|---|---|---|
| Analytics | `4d0bf12c-0a7d-4f53-8cc5-15e0109a5cf1` | `d61d773fae5b502aa46118e27bb56a3040fe6a6c` | release-source PASS; schema PASS; `run_mode=analytics` |
| Engine | `7aac8cf2-d287-49fc-a89b-7185f6d90e1a` | `bdc3f3a58980e4db8196aec78381e3ad34fe9091` | release-source PASS; schema PASS; `run_mode=engine` |
| Delivery | `2eaf24e7-a024-4b4d-8c6b-6a4ac9bc2776` | `99cce8b48982bc406ebd47c604515100f1a5446f` | release-source PASS; schema PASS; `run_mode=delivery` |
| Frontdoor | `7abdb8e6-f603-49a1-a9e5-8e100ef7dd3c` | `fd88074a36c9d76bb499d1f97bd4984c5a01f9c2` | release-source PASS; schema PASS; role=frontdoor; engine loop skipped |

Frontdoor health evidence on the successful rollout includes:

- Railway healthcheck success;
- `GET /healthz -> 200`;
- `GET /app -> 200`;
- Telegram webhook configured;
- webhook pending updates = 0.

## Safety posture

This is staging certification, not real-money activation.

During the staged migration and role certification:

- global execution kill switch remained enabled;
- live-financial feature gate remained off;
- real execution, auto execution and copy trading remained off;
- Bybit execution remained off;
- MT5 live-account execution remained off;
- Hyperliquid mainnet execution remained off;
- real payouts and Paystack transfers remained off.

A real demo/broker credential must still be linked through the canonical
connection flow and independently certified before broker-provider execution
evidence can be claimed. A PROP account additionally requires its exact
versioned account policy to be operator-certified before any PROP execution
gate can pass.
