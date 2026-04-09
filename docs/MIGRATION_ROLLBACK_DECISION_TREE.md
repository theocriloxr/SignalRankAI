# Migration Rollback Decision Tree

This decision tree is tied to the active Alembic chain configured in [alembic.ini](alembic.ini#L1), which points to [db/migrations](db/migrations).

Current active head:

- 0012_outcome_notify_state in [db/migrations/versions/0012_outcome_notify_state.py](db/migrations/versions/0012_outcome_notify_state.py)

## 1. Determine Current State

1. Get current revision:
   - python -m alembic current
2. Get available heads:
   - python -m alembic heads
3. If more than one head appears, stop and resolve branch divergence before rollback.

## 2. Decision Tree

1. Is production failing immediately after deploy and failure is schema-related?
   - If no: rollback app code only, keep schema unchanged.
   - If yes: continue to step 2.
2. Is failure isolated to outcome notification state features?
   - If yes: downgrade one step to 0011_platform_harden_security.
   - Command: python -m alembic downgrade 0011_platform_harden_security
3. Is failure broader and tied to platform hardening objects (api_tokens, processed_webhook_events, user_webhooks, ml_shadow_predictions)?
   - If yes: downgrade to 0010_consolidate_full_schema.
   - Command: python -m alembic downgrade 0010_consolidate_full_schema
4. Is failure tied to consolidated catch-up migration (new columns/tables from full-schema catch-up)?
   - If yes: downgrade to 0009_archived_column.
   - Command: python -m alembic downgrade 0009_archived_column

## 3. Revision Map (Active Chain)

- 0008_user_tier_column -> [db/migrations/versions/0008_user_tier_column.py](db/migrations/versions/0008_user_tier_column.py)
- 0009_archived_column -> [db/migrations/versions/0009_archived_column.py](db/migrations/versions/0009_archived_column.py)
- 0010_consolidate_full_schema -> [db/migrations/versions/0010_consolidate_full_schema.py](db/migrations/versions/0010_consolidate_full_schema.py)
- 0011_platform_harden_security -> [db/migrations/versions/0011_platform_hardening_security_scaling.py](db/migrations/versions/0011_platform_hardening_security_scaling.py)
- 0012_outcome_notify_state -> [db/migrations/versions/0012_outcome_notify_state.py](db/migrations/versions/0012_outcome_notify_state.py)

## 4. Rollback Safety Profiles

## Profile A: Fast Containment (preferred)

1. Roll back application revision first in Railway.
2. Keep DB schema at current revision if backward-compatible.
3. Run smoke checks.
4. Only run Alembic downgrade if old code is incompatible with current schema.

## Profile B: Schema Rollback (when required)

1. Put bot ingress in low-risk mode:
   - WEBHOOK_QUEUE_USE_REDIS=0 (temporary only if queue path is unstable)
2. Downgrade one revision at a time:
   - python -m alembic downgrade 0011_platform_harden_security
3. Re-test health and critical paths.
4. Continue additional downgrade only if still blocked.

## 5. What Each Downgrade Removes

## Downgrade to 0011_platform_harden_security

Removes:

- outcome_notifications table and indexes from [db/migrations/versions/0012_outcome_notify_state.py](db/migrations/versions/0012_outcome_notify_state.py)

Risk:

- Outcome per-recipient idempotent notification state is lost.

## Downgrade to 0010_consolidate_full_schema

Removes:

- processed_webhook_events, api_tokens, user_webhooks, ml_shadow_predictions and several query-path indexes from [db/migrations/versions/0011_platform_hardening_security_scaling.py](db/migrations/versions/0011_platform_hardening_security_scaling.py)

Risk:

- Webhook idempotency and token-based API features regress.

## Downgrade to 0009_archived_column

Removes:

- Catch-up schema assets from [db/migrations/versions/0010_consolidate_full_schema.py](db/migrations/versions/0010_consolidate_full_schema.py)

Risk:

- Multiple newer runtime assumptions can break (trade tables, queue tables, newer columns).

## 6. Post-Rollback Validation

Run all three before reopening traffic:

1. python -m alembic current
2. python scripts/post_deploy_smoke.py
3. c:/Users/sammm/Desktop/SignalRankAI/.venv/Scripts/python.exe -m pytest -q tests/test_broker_permission_validation.py tests/test_time_stop_outcome_persistence.py

## 7. Note on Legacy Migration Folder

There is also a legacy folder at [alembic/migrations](alembic/migrations), but active Alembic operations use [db/migrations](db/migrations) per [alembic.ini](alembic.ini#L1).
