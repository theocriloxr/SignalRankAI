# SignalRankAI Deployment Diagnostics Runbook

## Required staging topology

Create an isolated Railway environment containing:

1. `SignalRankAI`
2. `Postgres`
3. `RedisState`
4. `RedisDelivery`
5. a dedicated Telegram staging bot and test chat

Do not run destructive recovery tests against the customer bot or production database.

## Required variables

```env
DATABASE_URL=${{Postgres.DATABASE_URL}}
REDIS_URL=${{RedisState.REDIS_URL}}
STATE_REDIS_URL=${{RedisState.REDIS_URL}}
DELIVERY_REDIS_URL=${{RedisDelivery.REDIS_URL}}
REQUIRE_DISTINCT_DELIVERY_REDIS=1

TELEGRAM_BOT_TOKEN=<sealed>
TELEGRAM_WEBHOOK_SECRET=<sealed random value>
OWNER_IDS=<numeric Telegram ID>
OWNER_TELEGRAM_ID=<numeric Telegram ID>
ADMIN_IDS=<numeric Telegram ID>
ENCRYPTION_KEY=<Fernet key>
API_TOKEN_PEPPER=<sealed random value>

WS_INGEST_ENABLED=0
CRYPTO_WS_ENABLED=0
FREE_RANDOM_DISTRIBUTION_ENABLED=0
FREE_SIGNAL_DISTRIBUTION_ENABLED=0
PROXY_VALIDATION_ENABLED=0

REAL_EXECUTION_ENABLED=0
AUTO_TRADE_ENABLED=0
COPY_TRADE_ENABLED=0
REAL_PAYOUTS_ENABLED=0
PAYMENTS_PUBLIC_ENABLED=0
MT5_ALLOW_LIVE_ACCOUNTS=0

DEPLOYMENT_DIAGNOSTICS_ENABLED=1
DEPLOYMENT_DIAGNOSTICS_LIVE_PROVIDERS=0
DEPLOYMENT_FULL_TESTS_ENABLED=0
DEPLOYMENT_DIAGNOSTICS_ENDPOINT_ENABLED=1
DEPLOYMENT_DIAGNOSTICS_KEY=<sealed random value>
```

## Pre-deploy gate

Railway automatically performs:

```bash
python -m alembic upgrade head && \
python scripts/deployment_diagnostics.py \
  --phase predeploy \
  --strict-core \
  --output /tmp/signalrank_predeploy_diagnostics.json
```

Deployment is blocked when a critical/high core check fails.

## Runtime report

After startup, wait for the configured delay, then request:

```bash
curl -H "X-Diagnostics-Key: $DEPLOYMENT_DIAGNOSTICS_KEY" \
  https://YOUR_DOMAIN/diagnostics/deployment
```

The report contains no raw secrets.

## Manual complete certification

Run this in an isolated certification service using the same release commit:

```bash
python scripts/deployment_diagnostics.py \
  --phase full \
  --base-url https://YOUR_STAGING_DOMAIN \
  --run-full-suite \
  --live-providers \
  --providers coinbase,okx,kraken,bybit,twelvedata,polygon,fmp,oanda \
  --continue-on-failure \
  --output /tmp/signalrank_full_diagnostics.json
```

Use only provider names and credentials actually configured.

## Explicit network-send tests

Telegram send test:

```env
DEPLOYMENT_TELEGRAM_SEND_TEST=1
DEPLOYMENT_TEST_CHAT_ID=<dedicated test chat ID>
```

The diagnostic sends only one labelled test message.

Paystack, TradingView, Gemini and MetaApi remain `BLOCKED` until their test/demo credentials are supplied. Real-money actions are never enabled by the diagnostics command.

## Recovery from accidental FREE queue creation

Dry run:

```bash
python scripts/quarantine_free_signal_queue.py
```

Apply after review:

```bash
python scripts/quarantine_free_signal_queue.py --apply --status suppressed
```

## Required evidence before soak

- `/healthz` HTTP 200
- `/livez` HTTP 200
- `/readyz` HTTP 200 and `ready=true`
- exact deployed migration head
- `decision_log.created_at=true`
- both Redis checks pass and URLs are distinct
- Telegram bot identity and exact webhook URL pass
- webhook pending count returns to zero
- no webhook 503 responses
- no engine event-loop warnings
- no repeated auxiliary engine creation
- no DB admission timeout
- REST provider smoke passes
- one signal follows the same ID from generation through terminal outcome

Only after these pass should the 24–72 hour soak begin.

## Delivery queue evidence

The deployment audit now inspects the Redis delivery stream without consuming work. It reports:

- stream depth;
- consumer-group lag;
- pending-entry count;
- oldest pending idle time;
- oldest unconsumed age;
- consumer count;
- dead-letter depth;
- legacy Redis-list depth;
- the state-side signal-dispatch list depth.

A stale pending entry, stale consumer-group lag, dead-letter item, or stranded legacy-list item fails the runtime audit. Before the first app startup, a missing consumer group is reported as a warning rather than blocking the corrected deployment.

## Extended scans

The normal production image runs the repository-native compile, migration, architecture, DB-session, secret, governance, dependency and environment checks. For deeper scanners, deploy an isolated certification service from the same commit, install `requirements-audit.txt`, and set:

```env
DEPLOYMENT_EXTENDED_SCANS_ENABLED=1
DEPLOYMENT_FULL_TESTS_ENABLED=1
```

The report inventories Ruff, Mypy, Pyright, Bandit, pip-audit, Semgrep, Vulture, ShellCheck, Hadolint, Coverage and mutation testing. A missing scanner is `BLOCKED`, never `PASS`. Mutation testing remains separately opt-in because it can run for a long time:

```env
DEPLOYMENT_MUTATION_TESTS_ENABLED=1
```

Do not run the full/mutation suite inside the customer-facing bot service on a small Railway plan. Use a temporary certification service with a dedicated test bot and staging-only infrastructure.
