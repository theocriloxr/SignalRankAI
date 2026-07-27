# Payment Receipts Migration Recovery

## Failure

Railway reached revision `0020_payment_receipts` but stopped because the table
`payment_receipts` already existed outside the recorded Alembic migration state.

## Resolution

Revision `0020_payment_receipts` is now idempotent and drift-aware. It:

- creates the table only when absent;
- adds missing columns without replacing the table;
- preserves every existing receipt row;
- audits and archives duplicate receipt identities without deleting data;
- fails closed when financial rows lack non-derivable required fields;
- creates the canonical uniqueness and lookup indexes idempotently;
- retains payment evidence on downgrade.

## Pre-deploy diagnosis

```bash
python scripts/diagnose_payment_receipts_schema.py \
  --output /tmp/payment_receipts_diagnosis.json
```

## Deployment

Keep Railway pre-deploy migration enabled:

```bash
python -m alembic upgrade head
```

The migration should continue from `0019_user_timezone_privacy` through
`0020_payment_receipts`, `0021_runtime_truth_hardening`, and
`0022_active_guard_reconcile`.
