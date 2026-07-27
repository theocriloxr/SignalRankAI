# SignalRankAI V7.1 Railway Deployment and Telegram Message-Recovery Guide

This guide deploys the repository in the safest useful order:

1. Telegram commands and buttons recover first.
2. PostgreSQL and two Redis services become healthy.
3. The worker starts, while signal generation remains disabled.
4. Owner-only crypto REST signals are enabled only after the bot is stable.
5. Payments, MetaApi, copy trading and real execution remain disabled.

Do not paste real keys into Git, screenshots, chat messages, logs or issue reports.

---

## 1. Use the corrected package

Use `SignalRankAI_V7_1_Telegram_Recovered_2026-07-27.zip`, not the earlier V7 archive.

The corrected package:

- preserves pending Telegram updates during startup;
- explicitly subscribes to `message` and `callback_query` updates;
- supports a separate direct migration database URL;
- makes runtime schema bootstrapping opt-in;
- makes Railway wait for `/readyz`, not just process liveness;
- includes `scripts/telegram_webhook_recovery.py`.

After extracting, the repository root must directly contain:

```text
railway.json
railway_main.py
start.sh
requirements.txt
alembic.ini
signalrank_telegram/
db/
engine/
worker/
```

If those files sit inside another folder, either move the contents to the GitHub repository root or set that folder as Railway's Root Directory.

---

## 2. Put the corrected repository on GitHub

From PowerShell inside the extracted repository:

```powershell
git init
git add .
git commit -m "Deploy SignalRankAI V7.1 Telegram recovery"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPOSITORY.git
git push -u origin main
```

For an existing Git repository:

```powershell
git add .
git commit -m "Apply SignalRankAI V7.1 Telegram recovery"
git push
```

Before pushing, confirm these files are not tracked:

```powershell
git status
git ls-files | Select-String -Pattern "(^|/)(\.env|\.env\.local)$|\.sqlite$|\.db$|secret|credential"
```

Never commit a filled `.env` file.

---

## 3. Create a separate Railway staging environment

Do not repair the bot directly in a customer-facing production environment first.

In Railway:

1. Open the SignalRankAI project.
2. Open **Project Settings → Environments**.
3. Create an environment called `staging`.
4. Connect the corrected GitHub repository to an application service.
5. Name the application service `SignalRankAI`.
6. Keep the application at **one replica**.
7. Generate a public Railway domain for the application service.

The application needs a public HTTPS domain because Telegram sends webhook POST requests to it.

---

## 4. Add the required data services

Add three separate data services to the same Railway project and staging environment:

```text
Postgres
RedisState
RedisDelivery
```

Rename them exactly as shown, or edit the reference-variable names in the supplied environment file.

### What each service does

- `Postgres`: durable users, signals, delivery proof, lifecycle, outcomes, payments and audit data.
- `RedisState`: cache, runtime state, provider health and non-critical coordination.
- `RedisDelivery`: Telegram webhook stream, pending work, retries and delivery coordination.

`RedisState` and `RedisDelivery` must not point to the same Redis URL.

---

## 5. Generate the required secrets locally

Run these commands locally. Do not send their output to anyone.

### Telegram webhook secret

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Use only letters, numbers, `_` and `-` for this value.

### Encryption key

```powershell
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

### API token pepper

```powershell
python -c "import secrets; print(secrets.token_hex(48))"
```

Store these three outputs in a password manager.

---

## 6. Obtain and verify the Telegram bot token

In Telegram:

1. Open the official `@BotFather` chat.
2. Create a separate staging bot with `/newbot`, or choose the existing bot.
3. Copy its token.
4. If the token may have leaked, use BotFather to revoke it and generate a new one.
5. Open the bot's private chat and press **Start**.

Verify the token from PowerShell:

```powershell
$env:TELEGRAM_BOT_TOKEN = "PASTE_TOKEN_HERE"
Invoke-RestMethod "https://api.telegram.org/bot$env:TELEGRAM_BOT_TOKEN/getMe" | ConvertTo-Json -Depth 8
```

Expected result:

```json
{
  "ok": true,
  "result": {
    "is_bot": true,
    "username": "your_bot_username"
  }
}
```

A `401 Unauthorized` result means the token is wrong or revoked.

---

## 7. Find your numeric Telegram user ID

Use one of these methods.

### Method A — existing trusted Telegram ID

Use the same numeric ID already configured in your old Railway variables.

### Method B — temporarily read one update before deploying

First remove any old webhook without deleting pending updates:

```powershell
Invoke-RestMethod -Method Post `
  -Uri "https://api.telegram.org/bot$env:TELEGRAM_BOT_TOKEN/deleteWebhook" `
  -Body @{ drop_pending_updates = "false" }
```

Send `/start` to the bot, then run:

```powershell
Invoke-RestMethod "https://api.telegram.org/bot$env:TELEGRAM_BOT_TOKEN/getUpdates" | ConvertTo-Json -Depth 20
```

Find:

```text
result[].message.from.id
```

That number is your `OWNER_TELEGRAM_ID`, `OWNER_IDS`, `ADMIN_IDS`, and initial `DEPLOYMENT_TEST_CHAT_ID`.

Do not keep using `getUpdates` after the Railway webhook is registered. Polling and webhooks are mutually exclusive.

---

## 8. Paste the Railway environment variables

Open:

```text
SignalRankAI service → Variables → RAW Editor
```

Paste the complete contents of:

```text
deployment_package/SignalRankAI_Railway_Owner_Beta.env
```

Replace every placeholder:

```text
<PASTE_BOTFATHER_TOKEN>
<GENERATE_VALID_WEBHOOK_SECRET>
<YOUR_NUMERIC_TELEGRAM_ID>
<GENERATE_FERNET_KEY>
<GENERATE_RANDOM_PEPPER>
```

Do not deploy while any `<...>` placeholder remains.

### Seal these variables

After saving, use the variable menu to seal:

```text
TELEGRAM_BOT_TOKEN
TELEGRAM_WEBHOOK_SECRET
ENCRYPTION_KEY
API_TOKEN_PEPPER
```

Later, also seal every provider, Gemini, Paystack, TradingView and MetaApi credential.

### Confirm reference variables resolve

The application service must show resolved references for:

```text
DATABASE_URL=${{Postgres.DATABASE_URL}}
DATABASE_MIGRATION_URL=${{Postgres.DATABASE_URL}}
REDIS_URL=${{RedisState.REDIS_URL}}
STATE_REDIS_URL=${{RedisState.REDIS_URL}}
DELIVERY_REDIS_URL=${{RedisDelivery.REDIS_URL}}
```

If you used different service names, change the names inside `${{...}}`.

---

## 9. Railway build and deployment settings

The repository includes `railway.json`. Confirm Railway uses these effective settings:

```text
Builder: Nixpacks
Start command: bash start.sh
Pre-deploy command:
python -m alembic upgrade head && python scripts/deployment_diagnostics.py --phase predeploy --strict-core --output /tmp/signalrank_predeploy_diagnostics.json
Healthcheck path: /readyz
Healthcheck timeout: 300 seconds
Restart policy: ON_FAILURE
Maximum restart retries: 5
```

Do not run Alembic during the image build. The pre-deploy container has access to Railway's private network and environment variables; the build stage should not modify the database.

Set one application replica only. Multiple replicas would duplicate process-local schedulers and bot ownership unless a later distributed ownership gate is implemented and certified.

---

## 10. First deployment: engine disabled

The supplied owner-beta environment deliberately uses:

```env
RUN_ENGINE_LOOP=0
RUN_WORKER_LOOP=1
```

This lets you repair Telegram commands and buttons without signal-generation load.

Deploy the staged changes.

Watch the deployment logs for these lines:

```text
[bot] webhook setup starting
[bot] identity: id=... username=@...
[bot] webhook registered: https://.../telegram/webhook
[webhook] startup status: url_set=True
[bot] webhook mode active
```

The following lines identify the immediate failure:

```text
webhook setup skipped: DATABASE_URL missing
webhook setup skipped: DRY_RUN enabled
webhook setup skipped: TELEGRAM_BOT_TOKEN missing
webhook setup failed: handlers not ready
application initialize/start failed
set_webhook failed
webhook_secret_not_configured
invalid_webhook_secret
```

---

## 11. Verify all runtime endpoints

Replace `YOUR_DOMAIN` with the generated Railway domain.

### Process liveness

```powershell
Invoke-RestMethod "https://YOUR_DOMAIN/healthz" | ConvertTo-Json -Depth 10
```

Expected: HTTP 200 and `status: ok`.

### Full readiness

```powershell
Invoke-RestMethod "https://YOUR_DOMAIN/readyz" | ConvertTo-Json -Depth 20
```

Every check must report `ok: true`:

```text
database
state_redis
delivery_redis
redis_separation
telegram
telegram_webhook_secret
resource_guard
```

A 503 response is useful: read its JSON body and fix the named failed dependency.

### Webhook runtime status

```powershell
Invoke-RestMethod "https://YOUR_DOMAIN/telegram/webhook_status" | ConvertTo-Json -Depth 20
```

Expected:

```text
bot_ready = true
webhook_info.url = https://YOUR_DOMAIN/telegram/webhook
webhook_info.pending_update_count is low and returns toward zero
webhook_info.last_error_message is empty
```

---

## 12. Run the included webhook diagnosis

With Railway CLI linked to the application service:

```powershell
railway run python scripts/telegram_webhook_recovery.py
```

To repair the webhook safely:

```powershell
railway run python scripts/telegram_webhook_recovery.py --repair --domain https://YOUR_DOMAIN
```

To verify outbound Telegram transport to your private chat:

```powershell
railway run python scripts/telegram_webhook_recovery.py --send-test YOUR_TELEGRAM_ID
```

The repair script:

- checks `getMe`;
- checks `getWebhookInfo`;
- registers the exact `/telegram/webhook` URL;
- explicitly enables messages and callback queries;
- preserves pending updates;
- can send one test message.

---

## 13. Manual webhook repair from PowerShell

Use this only when the included script cannot be run.

```powershell
$token = "PASTE_BOT_TOKEN"
$secret = "PASTE_TELEGRAM_WEBHOOK_SECRET"
$domain = "https://YOUR_DOMAIN"
$allowed = '["message","edited_message","callback_query","my_chat_member","chat_member","pre_checkout_query","shipping_query"]'

Invoke-RestMethod -Method Post `
  -Uri "https://api.telegram.org/bot$token/setWebhook" `
  -Body @{
    url = "$domain/telegram/webhook"
    secret_token = $secret
    allowed_updates = $allowed
    drop_pending_updates = "false"
    max_connections = "20"
  } | ConvertTo-Json -Depth 10
```

Then inspect it:

```powershell
Invoke-RestMethod "https://api.telegram.org/bot$token/getWebhookInfo" | ConvertTo-Json -Depth 20
```

Never use `drop_pending_updates=true` during normal deployment.

---

## 14. Determine where the message path is failing

### Test A — Telegram can authenticate the token

```powershell
Invoke-RestMethod "https://api.telegram.org/bot$token/getMe"
```

- Fails: token problem.
- Passes: continue.

### Test B — Telegram can send an outbound message

```powershell
Invoke-RestMethod -Method Post `
  -Uri "https://api.telegram.org/bot$token/sendMessage" `
  -Body @{ chat_id = "YOUR_TELEGRAM_ID"; text = "Direct Telegram transport test" }
```

- `chat not found`: open the bot and press Start, or use the correct chat ID.
- `bot was blocked by the user`: unblock it.
- Passes but bot commands do not: outbound transport works; investigate webhook ingress/dispatch.

### Test C — webhook points to the exact current deployment

```powershell
Invoke-RestMethod "https://api.telegram.org/bot$token/getWebhookInfo" | ConvertTo-Json -Depth 20
```

- `url` empty: run the repair command.
- wrong domain or path: re-register.
- `pending_update_count` continually grows: Telegram cannot get successful 2xx responses or the application queue is blocked.
- `last_error_message` contains 401: webhook secret mismatch.
- contains 404: wrong domain/path or route was not deployed.
- contains 502/503: application is unavailable or readiness/dependency checks are failing.
- contains timeout: deployment is too slow or blocked before acknowledging updates.

### Test D — application receives the update

Send `/start` and search Railway logs for:

```text
[webhook] ingress received update_id=
```

- No ingress line: Telegram-to-Railway webhook problem.
- Ingress exists, no dispatch completion: Redis/dispatcher problem.
- Dispatch exists, no reply: handler, DB, entitlement or send problem.

### Test E — Redis delivery stream

Open `/readyz` and ensure `delivery_redis` and `redis_separation` are healthy.

Search logs for:

```text
redis enqueue failed
redis enqueue timeout
queue_full
dead_letter
consumer group missing
```

Do not delete Redis streams to make the error disappear. Repair the consumer or replay only after confirming idempotency.

---

## 15. Telegram command and button test order

Test in this order:

```text
/start
/help
/myid
/selfcheck
/db_health
/system
/assets
/signals
/profile
/account
```

Then test every visible inline button.

For a button failure, check that:

1. The button spinner stops quickly.
2. Railway logs show a `callback_query` update.
3. The callback is acknowledged.
4. The clicking Telegram user owns the related delivery.
5. The signal ID still exists and is visible to that user.
6. The final message edit or fallback reply succeeds.

Do not enable paid broadcasts or signal generation until these basic tests pass.

---

## 16. Database migration verification

The pre-deploy command must finish successfully before Railway activates the new container.

To inspect the current Alembic head from a Railway shell:

```powershell
railway run python -m alembic current
railway run python -m alembic heads
```

There must be one head, and `current` must match it.

Run readiness again:

```powershell
Invoke-RestMethod "https://YOUR_DOMAIN/readyz" | ConvertTo-Json -Depth 20
```

The database check also verifies a critical schema column and the deployed Alembic revision.

Do not use `alembic stamp head` to hide a failed migration.

---

## 17. Optional PgBouncer setup

The first staging recovery can use Railway's direct private Postgres URL with the small application pool in the supplied environment file.

To satisfy the complete transaction-pooling architecture later:

1. Add a PgBouncer service in the same Railway environment.
2. Configure it for transaction pooling against the `Postgres` service.
3. Keep migrations direct:

```env
DATABASE_MIGRATION_URL=${{Postgres.DATABASE_URL}}
```

4. Point runtime traffic at PgBouncer using the URL variable exported by your PgBouncer service:

```env
DATABASE_URL=${{PgBouncer.DATABASE_URL}}
DB_USE_NULLPOOL=1
```

5. Redeploy and verify `/readyz`.
6. Run the DB session/admission diagnostics and a restart test.

Do not guess the PgBouncer service's exported variable name; use the variable shown by that service/template.

---

## 18. Enable owner-only crypto signal generation

Only after commands, buttons, database and both Redis services remain stable for at least one hour:

Change:

```env
RUN_ENGINE_LOOP=1
```

Keep:

```env
CRYPTO_ONLY_MODE=1
ASSET_CLASSES_ENABLED=crypto
CRYPTO_MARKET_DATA_PROVIDERS=coinbase,okx
WS_INGEST_ENABLED=0
CRYPTO_WS_ENABLED=0
FREE_RANDOM_DISTRIBUTION_ENABLED=0
FREE_SIGNAL_DISTRIBUTION_ENABLED=0
PAYMENTS_PUBLIC_ENABLED=0
AUTO_TRADE_ENABLED=0
COPY_TRADE_ENABLED=0
REAL_EXECUTION_ENABLED=0
```

Redeploy, then prove one exact signal through:

```text
candidate
→ accepted decision
→ owner eligibility
→ Telegram send
→ persisted delivery proof
→ active lifecycle
→ terminal outcome
```

The four-hour same-user/same-asset lock begins only after successful delivery proof.

---

## 19. Run the owner soak

Keep the owner-only crypto/REST deployment running for 24–72 hours.

Monitor:

- Railway memory and CPU;
- Postgres connection count;
- DB session hold warnings;
- Redis queue depth and pending work;
- Telegram pending update count;
- duplicate commands, messages or signals;
- callback latency;
- lifecycle/outcome lag;
- worker restarts;
- provider errors;
- event-loop lag.

Stop expansion if any critical error repeats.

---

## 20. Optional integrations — add one phase at a time

Use `deployment_package/SignalRankAI_Optional_Integrations.env.example` only after core recovery.

Recommended order:

1. Gemini advisory review.
2. News.
3. One additional market-data provider.
4. Additional asset class, one at a time.
5. TradingView signed alerts.
6. Paystack test mode.
7. Paper trading.
8. MetaApi demo.
9. Controlled internal users.
10. Public payments only after pricing, legal, security and reconciliation gates.
11. Real execution only after a separate approved pilot.

Missing credentials must leave the integration disabled; they must not be represented as successful tests.

---

## 21. Variables that must remain off now

```env
PAYMENTS_ENABLED=0
PAYMENTS_PUBLIC_ENABLED=0
REAL_PAYOUTS_ENABLED=0
AUTO_TRADE_ENABLED=0
COPY_TRADE_ENABLED=0
REAL_EXECUTION_ENABLED=0
MT5_ENABLED=0
MT5_ALLOW_LIVE_ACCOUNTS=0
FREE_RANDOM_DISTRIBUTION_ENABLED=0
FREE_SIGNAL_DISTRIBUTION_ENABLED=0
WS_INGEST_ENABLED=0
CRYPTO_WS_ENABLED=0
TELEGRAM_DROP_PENDING_UPDATES_ON_STARTUP=0
```

Do not turn all features on simultaneously.

---

## 22. Final acceptance checklist for “messages work”

The Telegram recovery is complete only when all of these are true:

- `getMe` returns the expected bot username.
- `/healthz` returns HTTP 200.
- `/readyz` returns `ready: true`.
- `/telegram/webhook_status` returns `bot_ready: true`.
- `getWebhookInfo.url` exactly matches the Railway `/telegram/webhook` URL.
- `pending_update_count` returns toward zero.
- `last_error_message` is empty.
- `/start` responds.
- `/help` responds.
- `/selfcheck` responds.
- `/db_health` responds.
- visible callback buttons stop loading and produce a result.
- a direct outbound test message succeeds.
- messages still work after one redeploy and one application restart.
- no queued updates were deliberately discarded.
