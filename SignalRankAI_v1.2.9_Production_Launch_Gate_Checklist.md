# SignalRankAI v1.2.9 Railway Staging Gate

## Deploy

- Deploy the complete v1.2.9 ZIP.
- Set `APP_VERSION=1.2.9`.
- Keep `APP_ENV=staging`, `PUBLIC_TESTING_MODE=1` and the full-system staging acknowledgement.
- Keep the tester audience allowlisted.
- Do not enable MT5 live accounts.
- Keep Bybit on testnet.

## Boot proof

Confirm:

- `[boot] SignalRankAI v1.2.9`
- `release=v1.2.9-lifecycle-profile-observability-hotfix-20260730`
- Telegram webhook active with pending updates `0`
- signal engine, worker outcome tracker, scheduler and adaptive candle capture enabled
- migration head `0027_launch_paper_trading`
- only one owner-ready notification during a rolling deployment

## Lifecycle proof

Within two outcome cycles confirm:

- no `func` NameError;
- `active_scan` and `reconciliation_backfill` run;
- at least one durable lifecycle transition is logged when price evidence crosses a boundary;
- `/outcome <reference>` reflects the reconciled state;
- `/system` untracked and pending counts begin decreasing when terminal conditions exist;
- portfolio exposure no longer remains stuck solely because old terminal signals lack outcome rows.

## Profile proof

Use a new tester and an existing tester:

1. `/profile`
2. `/profile day`
3. `/profile`
4. `/profile risk conservative`
5. `/profile`

Pass criteria:

- no `TimeoutError`;
- no duplicate error after the profile card;
- style and risk changes persist;
- timezone button remains responsive.

## Observability proof

- `/healthz` = 200
- `/livez` = 200
- `/readyz` = 200
- `/metrics/prometheus` = 200 with SignalRank metrics
- `/system` reports the main pool capacity when the command runs on an auxiliary loop
- PostgreSQL max connections is populated when the health query is admitted

## Paystack gate

The staging profile requires a matching key pair:

- `PAYSTACK_SECRET_KEY=sk_live_...`
- `PAYSTACK_PUBLIC_KEY=pk_live_...`

Both must belong to the same Paystack account and mode. Keep the user allowlist and maximum amount cap. If either key is absent, mismatched or test-mode, public payments and real payouts must remain blocked.

## Release decision

Do not promote to public production until every applicable item passes and the evidence is saved with timestamps and deployment ID.
