# SignalRankAI — Manual Setup Checklist

> Complete these steps **before** your first production deployment.
> Code changes are done — everything below is external configuration only.

---

## Step 1 — Create your `.env` file

Create a file called `.env` in the project root. **Never commit it to git** (it is already in `.gitignore`).

```env
# ── Telegram ────────────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN=           # from BotFather (see Step 2)

# ── Database ────────────────────────────────────────────────────────────────
DATABASE_URL=                 # postgresql+asyncpg://user:pass@host:5432/dbname

# ── Paystack ────────────────────────────────────────────────────────────────
PAYSTACK_SECRET_KEY=          # sk_live_... from Paystack → Settings → API Keys
PAYSTACK_WEBHOOK_SECRET=      # same value as PAYSTACK_SECRET_KEY (Paystack reuses it for HMAC)
PAYSTACK_PREMIUM_PLAN_CODE=   # PLN_... created in Step 3
PAYSTACK_VIP_PLAN_CODE=       # PLN_... created in Step 3
PAYSTACK_CALLBACK_URL=        # https://t.me/YourBotUsername  (or your web redirect URL)

# ── Pricing ─────────────────────────────────────────────────────────────────
VIP_SEAT_LIMIT=15
PREMIUM_PRICE_NGN=1500000     # kobo: 15,000 NGN × 100
VIP_PRICE_NGN=3000000         # kobo: 30,000 NGN × 100

# ── Data Providers ──────────────────────────────────────────────────────────
FINNHUB_API_KEY=              # free tier from finnhub.io

# ── Features ────────────────────────────────────────────────────────────────
REFERRAL_BONUS_DAYS=7
FERNET_KEY=                   # generated in Step 6

# ── MT5 Broker Execution (optional) ─────────────────────────────────────────
METAAPI_TOKEN=                # from metaapi.cloud dashboard

# ── Infrastructure (optional) ────────────────────────────────────────────────
RAILWAY_HEALTH_BASIC=         # basic-auth value for /health endpoint (optional)
```

---

## Step 2 — Set up the Telegram Bot (BotFather)

1. Open Telegram → message **@BotFather**
2. Send `/newbot` → follow the prompts → copy the **token** into `TELEGRAM_BOT_TOKEN`
3. Send `/setprivacy` → select your bot → choose **Disable**
   *(allows the bot to read messages in groups if needed)*
4. **Do not** run `/setcommands` manually — the bot registers all commands automatically on first start

---

## Step 3 — Create Paystack Recurring Plans

Go to [dashboard.paystack.com](https://dashboard.paystack.com) → **Products → Plans → Create Plan**

### Premium Plan
| Field | Value |
|-------|-------|
| Name | `SignalRankAI Premium` |
| Amount | `15,000 NGN` |
| Interval | `Monthly` |

Copy the `PLN_...` code → paste as **`PAYSTACK_PREMIUM_PLAN_CODE`**

### VIP Plan
| Field | Value |
|-------|-------|
| Name | `SignalRankAI VIP` |
| Amount | `30,000 NGN` |
| Interval | `Monthly` |

Copy the `PLN_...` code → paste as **`PAYSTACK_VIP_PLAN_CODE`**

---

## Step 4 — Register the Paystack Webhook

Go to **Paystack Dashboard → Settings → Webhooks → Add Endpoint**

| Field | Value |
|-------|-------|
| URL | `https://your-railway-domain.up.railway.app/webhook/paystack` |
| Events | `charge.success`, `invoice.payment_failed` *(minimum)* |
| Secret | your `PAYSTACK_SECRET_KEY` — Paystack uses this for HMAC automatically |

> **No live domain yet?** Use [ngrok](https://ngrok.com) temporarily:
> ```bash
> ngrok http 8000
> # Use the printed https://xxxx.ngrok.io/webhook/paystack URL in Paystack
> ```

---

## Step 5 — Run the Database Migration

The DDL runs automatically on the first request via `get_session()`, and `start.sh` also runs it on every boot. For a clean production deploy, run it explicitly **before** starting:

```bash
# Activate your environment first
.venv\Scripts\Activate.ps1          # Windows
# source .venv/bin/activate         # Linux / Railway shell

python -m alembic upgrade head
```

To verify it worked:
```bash
python -m alembic current
# Should print the latest revision hash followed by (head)
```

If new columns were added outside of Alembic (manually or via `db/session.py`), generate a migration to sync:
```bash
python -m alembic revision --autogenerate -m "enterprise_columns"
python -m alembic upgrade head
```

---

## Step 6 — Generate a Fernet Key

Required for encrypting MT5 broker credentials at rest.

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Copy the output → paste as **`FERNET_KEY`** in your `.env`.

> **Important:** If you lose this key, all stored broker credentials become unreadable.
> Back it up securely (e.g. a password manager).

---

## Step 7 — Deploy to Railway

1. Push your code to GitHub
2. Go to [railway.app](https://railway.app) → **New Project → Deploy from GitHub repo**
3. Add a **PostgreSQL** plugin to the project — Railway injects `DATABASE_URL` automatically
4. In **Variables**, add every key from your `.env`
   *(Railway has a bulk-paste option: paste the whole `.env` file content at once)*
5. The `start.sh` script already runs `alembic upgrade head` before boot — nothing extra needed

### Running multiple processes separately (recommended for production)

Create **three Railway services** from the same repo, each with a different `RUN_MODE` environment variable:

| Service name | `RUN_MODE` value |
|--------------|-----------------|
| `web` | `web` |
| `bot` | `bot` |
| `engine` | `engine` |

All three share the same PostgreSQL plugin and environment variables.

---

## Step 8 — Test the Paystack Webhook

After deploying, send a test event from the Paystack dashboard:

1. **Dashboard → Settings → Webhooks → Send Test Event**
2. Choose `charge.success` → click **Send**
3. Check Railway logs — you should see:
   ```
   [webhook] charge.success processed
   ```
4. If you see `401 Invalid signature`:
   - Confirm `PAYSTACK_WEBHOOK_SECRET` equals `PAYSTACK_SECRET_KEY` exactly
   - No leading/trailing spaces, no surrounding quotes

---

## Step 9 — Run the Test Suite (locally)

```bash
.venv\Scripts\Activate.ps1

# Enterprise feature tests only (no live DB needed — all mocked)
pytest tests/test_enterprise_features.py -v

# Full suite
pytest -v
```

All 16 test classes should pass.

---

## Step 10 — Seed Your Owner Account

After the first deploy, set your Telegram account to `owner` tier so you have access to
`/unlock`, `/owner_users`, `/owner_revenue`, etc.

Run this SQL in your PostgreSQL console
*(Railway → PostgreSQL plugin → **Connect** tab → **psql** or **Query** tab)*:

```sql
UPDATE users
SET tier = 'owner'
WHERE telegram_user_id = YOUR_TELEGRAM_ID;
```

Replace `YOUR_TELEGRAM_ID` with your numeric Telegram user ID.
*(Don't know it? Message [@userinfobot](https://t.me/userinfobot) on Telegram.)*

---

## Quick Reference — All Environment Variables

| Variable | Required | Description |
|----------|:--------:|-------------|
| `TELEGRAM_BOT_TOKEN` | ✅ | Token from BotFather |
| `DATABASE_URL` | ✅ | `postgresql+asyncpg://…` |
| `PAYSTACK_SECRET_KEY` | ✅ | Paystack secret key |
| `PAYSTACK_WEBHOOK_SECRET` | ✅ | Same as `PAYSTACK_SECRET_KEY` |
| `PAYSTACK_PREMIUM_PLAN_CODE` | ✅ | `PLN_…` for Premium recurring plan |
| `PAYSTACK_VIP_PLAN_CODE` | ✅ | `PLN_…` for VIP recurring plan |
| `PAYSTACK_CALLBACK_URL` | ✅ | Post-checkout redirect URL |
| `VIP_SEAT_LIMIT` | ✅ | Max concurrent VIP subscribers |
| `PREMIUM_PRICE_NGN` | ✅ | Premium price in kobo (NGN × 100) |
| `VIP_PRICE_NGN` | ✅ | VIP price in kobo (NGN × 100) |
| `FINNHUB_API_KEY` | ⚠️ | Economic calendar / news provider |
| `REFERRAL_BONUS_DAYS` | ⚠️ | Bonus days for referrer (default: `7`) |
| `FERNET_KEY` | ⚠️ | Encryption key for broker credentials |
| `METAAPI_TOKEN` | ⚠️ | MetaAPI cloud token for MT5 execution |
| `RAILWAY_HEALTH_BASIC` | ⚠️ | Basic-auth for `/health` endpoint |
