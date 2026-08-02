# SignalRankAI Referral Reliability and DB Pool Fix

Date: 2026-08-02
Target release: v1.3.4 referral reliability hotfix
Current package migration head: `0033_ml_learning_runtime`

Referral reliability migration: `0032_referral_reliability`

## Confirmed runtime problems

The August 2 deployment requested a PostgreSQL pool of 12 with overflow 6, but the monolith safety contract forced an effective pool of 2 with overflow 0. The two slots were then monopolized by startup tier-scope refresh and readiness probes, causing `/referral`, outcome tracking, monitor callbacks, free distribution, and delivery work to time out.

The referral implementation also contained correctness defects independent of the pool:

- `/invite` could display a synthetic code that was never stored.
- `/referral` could fall back to the Telegram user ID as an unstored code.
- `/start` swallowed referral processing exceptions.
- Signup rewards and first-purchase rewards used competing implementations.
- Paystack passed a Telegram ID to logic expecting the internal `users.id`.
- Reward batch references repeated after the progress counter was reset.
- Zero referrals could be displayed as a completed milestone.
- Referral reward resolution opened a nested DB session.
- Referrer notifications could be duplicated and failures were discarded.
- Redis Stream `XACK=0` after successful processing caused already-processed Telegram updates to be treated as failed.

## Implemented fixes

### Canonical referral service

`db/pg_features.py` is now the source of truth:

- Referral links are returned only after the code is persisted.
- Referrer and referred-user rows are locked during attribution.
- A genuinely new Telegram user can be attributed only once.
- Self-referrals and existing-user referrals are rejected.
- Three valid referrals grant seven Premium days by default.
- Lifetime referral totals are retained and never reset.
- Reward batches use stable unique references such as `REFERRAL:<telegram_id>:<batch>`.
- First purchase is recorded as conversion analytics only; it does not run a competing reward policy.
- Tier extension is resolved using the caller's existing DB session.

### Referral schema migration

Migration `0032_referral_reliability` adds:

- `referral_rewards.reference`
- `referral_rewards.meta`
- unique idempotency index for non-null reward references
- referral lookup/performance indexes
- legacy attribution normalization
- lifetime referral-count backfill

### Telegram commands

- `/invite` and `/referral` fail closed instead of emitting invalid links.
- Referral failures are logged with actionable markers.
- `/start` no longer silently discards referral failures.
- Referrer notification is sent once per canonical outcome.
- Referral leaderboard/reward commands use explicit interactive DB priorities and timeouts.

### Paystack

The payment webhook records first-purchase conversion within its existing transaction and resolves Telegram IDs to internal users correctly.

### DB pool

A bounded temporary monolith override was added. It is disabled unless explicitly acknowledged:

```env
DB_ALLOW_REVIEWED_MONOLITH_POOL=1
DB_POOL_SIZE=8
DB_MAX_OVERFLOW=2
DB_POOL_RAILWAY_ABSOLUTE_CAP=8
DB_MAX_OVERFLOW_RAILWAY_ABSOLUTE_CAP=2
DB_REVIEWED_MONOLITH_POOL_MAX=8
DB_REVIEWED_MONOLITH_OVERFLOW_MAX=2
DB_MAX_CONCURRENT_SESSIONS=10
DB_BACKGROUND_MAX_CONCURRENT_SESSIONS=2
```

The override is capped in code at 16 pooled plus 4 overflow, and public-testing mode always forces 2 plus 0. The recommended initial deployment is 8 plus 2, not 12 plus 6.

### Startup command scopes

The unbounded per-user command-scope refresh is disabled by default:

```env
BOT_COMMAND_SCOPE_BULK_REFRESH_ENABLED=0
BOT_COMMAND_SCOPE_BULK_LIMIT=500
```

Global free commands and owner/admin scopes are published at startup. This removes the startup query that held an interactive DB slot for more than 100 seconds.

### Webhook queue acknowledgement

An `XACK=0` returned after a Telegram update was successfully handled is now logged as an idempotent warning instead of retrying the already-processed business action.

### Historical repair

`scripts/reconcile_referral_events.py` scans historical `user_start` bot events for referral tokens that failed or were never attributed.

Dry run:

```bash
python scripts/reconcile_referral_events.py --days 30
```

Apply:

```bash
python scripts/reconcile_referral_events.py --days 30 --apply
```

## Deployment

1. Set the reviewed pool variables from `SignalRankAI_v1.3.4_Referral_Reliability.env.example`.
2. Keep `PUBLIC_TESTING_MODE=0`.
3. Deploy the code.
4. Run the migration:

```bash
python -m alembic upgrade head
python -m alembic current
```

Expected:

```text
0033_ml_learning_runtime (head)
```

5. Run a dry reconciliation, inspect results, then apply it.
6. Stop every duplicate Railway/Render service using the same Telegram token, database, or Redis lock scope.

## Verification

Use an existing referrer account:

1. Send `/invite` twice. Both responses must contain the same durable code.
2. Send `/referral`; it must respond without a DB-admission timeout.
3. Open the referral link from a genuinely new Telegram account.
4. Confirm the new account sees `Referral applied`.
5. Confirm the referrer receives one progress notification.
6. Repeat with three unique new accounts.
7. Confirm exactly one seven-day subscription grant and one `premium_days` reward row for batch 1.
8. Repeat for another three accounts and confirm batch 2 has a distinct reference.
9. Test self-referral, reused account, invalid code, duplicate `/start`, and repeated Paystack webhook delivery.

Expected log markers:

```text
[db_pool_reviewed_monolith] ... capped=8+2
[referral_code_created]
[referral_start] status=attributed
[referral_reward_granted]
[referral_conversion_recorded]
[webhook] stream ack returned zero after successful processing
```

Must not recur:

```text
referral_command ... db_admission_timeout
requested_pool=12 ... effective_pool=2
stream acknowledgement failed
```

## Validation completed

- Python compilation passed for all modified Python modules.
- Alembic reports `0033_ml_learning_runtime` as the only head; referral fixes remain in revision `0032_referral_reliability`.
- 34 focused migration, pool-safety, referral-reliability, and performance/paper-reliability tests passed.

## Remaining operational requirement

The logs still show another instance holding the production advisory lock. A code patch cannot stop an extra deployed service. Only one scheduler/resend owner should use a given database, Redis scope, and Telegram bot token.
