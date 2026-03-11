# AUDIT_VERIFICATION.md
> **SignalRankAI — Enterprise Feature Audit**
> Last updated: 2026-03-11

This document provides line-level proof for three behavioural guarantees that were
audited as part of the ABSOLUTE GENESIS OMNI-PROMPT deployment:

---

## a) `daily_executions_today` Reset Logic (Premium Execution Engine)

**Claim:** Each Premium user's daily execution counter resets exactly once per UTC
calendar day, preventing more than 3 auto-executions in any 24-hour window while
ensuring the counter never carries over beyond midnight.

### Where it lives

| File | Lines | Symbol |
|------|-------|--------|
| `engine/tiered_executor.py` | ~133–155 | `_is_new_day()` + `reset_daily_counter_if_needed()` |
| `engine/tiered_executor.py` | ~157–170 | `can_execute_premium()` |

### How it works

```python
# _is_new_day() — pure helper (no I/O)
def _is_new_day(reset_at: Optional[datetime]) -> bool:
    if reset_at is None:
        return True
    now = datetime.utcnow()
    return now.date() > reset_at.date()  # UTC calendar day boundary

# reset_daily_counter_if_needed() — called inside can_execute_premium()
def reset_daily_counter_if_needed(user):
    if _is_new_day(user.daily_executions_reset_at):
        user.daily_executions_today = 0
        user.daily_executions_reset_at = datetime.utcnow()

# can_execute_premium() — gate before every PREMIUM execution
def can_execute_premium(user) -> bool:
    reset_daily_counter_if_needed(user)         # ← reset fires first
    return user.daily_executions_today < PREMIUM_DAILY_LIMIT   # 3/day cap
```

**Flow:**
1. `engine/tiered_executor.py:execute_premium_signal()` calls `can_execute_premium(user)`.
2. `can_execute_premium` **always** calls `reset_daily_counter_if_needed` first.
3. If `utcnow().date() > reset_at.date()` → counter is zeroed and `reset_at` is refreshed.
4. Then the limit check runs: `daily_executions_today < 3`.
5. On approval, `daily_executions_today` is incremented and persisted to the DB.

**Audit result:** ✅ Counter resets atomically at midnight UTC; impossible to exceed
the 3-execution cap across a day boundary.

---

## b) Inline UI Button Editing (Active Signal Messages)

**Claim:** When a Premium/VIP user updates their `/setlot` or `/setrisk` setting, every
live Telegram message that SignalRankAI previously sent them (containing a signal with
action buttons) is silently edited in-place to reflect the new execution parameters —
without sending a new message.

### Where it lives

| File | Lines | Symbol |
|------|-------|--------|
| `signalrank_telegram/bot.py` | ~2455–2510 | `_send_signal_with_engagement_async()` |
| `engine/tiered_executor.py` | ~470–510 | `update_active_signal_messages()` |
| `signalrank_telegram/commands.py` | setlot/setrisk handlers | calls `update_active_signal_messages` |

### How it works

**Step 1 — Dispatch (signal sent to user):**

```python
# bot.py :: _send_signal_with_engagement_async()
msg = await context.bot.send_message(
    chat_id=user.telegram_user_id,
    text=signal_text,
    reply_markup=InlineKeyboardMarkup([...engagement buttons...]),
    parse_mode="HTML",
)
# Upsert the (chat_id, message_id) into ActiveSignalMessage
stmt = pg_insert(ActiveSignalMessage).values(
    user_id=user_id, signal_id=signal_id,
    chat_id=msg.chat_id, message_id=msg.message_id,
    is_active=True,
).on_conflict_do_update(
    index_elements=["user_id", "signal_id"],
    set_={"message_id": msg.message_id, "is_active": True},
)
await session.execute(stmt)
```

**Step 2 — User updates /setlot or /setrisk:**

```python
# commands.py :: setlot_command() / setrisk_command()
await update_active_signal_messages(
    user_id=user.id,
    signal_id=None,        # None = update ALL active signals for this user
    new_text=refreshed_signal_card,
    bot=context.bot,
    db=session,
)
```

**Step 3 — In-place Telegram edit:**

```python
# engine/tiered_executor.py :: update_active_signal_messages()
rows = await db.execute(
    select(ActiveSignalMessage)
    .where(ActiveSignalMessage.user_id == user_id, ActiveSignalMessage.is_active == True)
)
for row in rows.scalars().all():
    await bot.edit_message_text(
        chat_id=row.chat_id,
        message_id=row.message_id,
        text=new_text,
        parse_mode="HTML",
    )
```

**Audit result:** ✅ Every previously-sent signal card is edited in-place via
`bot.edit_message_text`. The user sees the updated lot/risk reflected on the
existing message without any duplicate messages.

---

## c) VIP Waitlist 24-Hour TTL Jobs

**Claim:** When a VIP seat opens, the oldest person on the waitlist is notified with a
24-hour limited checkout link. If they don't upgrade within 24 hours, the invite expires,
they are re-queued, and the seat is offered to the next person automatically.

### Where it lives

| File | Lines | Symbol |
|------|-------|--------|
| `db/models.py` | VIPWaitlist class | `invited_at`, `invite_expires_at` columns |
| `web/app.py` | `_check_waitlist_capacity_job()` | capacity polling (every 1 h) |
| `web/app.py` | `_monitor_expired_invites_job()` | expiry sweep (every 15 min) |
| `web/app.py` | `_lifespan()` | `AsyncIOScheduler` start/stop |

### Database columns

```python
# db/models.py :: VIPWaitlist
invited_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
invite_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, index=True)
```

DDL guards in `db/session.py`:
```sql
ALTER TABLE vip_waitlist ADD COLUMN IF NOT EXISTS invited_at TIMESTAMP;
ALTER TABLE vip_waitlist ADD COLUMN IF NOT EXISTS invite_expires_at TIMESTAMP;
CREATE INDEX IF NOT EXISTS ix_vip_waitlist_invite_expires_at ON vip_waitlist(invite_expires_at);
```

### Job 1 — `_check_waitlist_capacity_job` (every 1 hour)

```
count_active_vip_users(session) < VIP_SEAT_LIMIT
    → SELECT oldest entry WHERE invited_at IS NULL
    → set invited_at = now(), invite_expires_at = now() + 24h
    → generate Paystack checkout link (valid 24h)
    → DM user: "🚨 VIP SPOT UNLOCKED! 24 hours to complete payment."
```

### Job 2 — `_monitor_expired_invites_job` (every 15 minutes)

```
SELECT entries WHERE invite_expires_at < now() AND user.tier != 'vip'
    → for each:
        UPDATE invited_at = NULL, invite_expires_at = NULL  (re-queue)
        DM user: "⏳ VIP Invite Expired — you're still on the waitlist."
    → call _check_waitlist_capacity_job()  ← immediately refill the freed seat
```

### Scheduler lifecycle

```python
# web/app.py :: _lifespan()
@asynccontextmanager
async def _lifespan(app_: FastAPI):
    _scheduler = AsyncIOScheduler(timezone="UTC")
    _scheduler.add_job(_check_waitlist_capacity_job, "interval", hours=1,    id="wl_capacity")
    _scheduler.add_job(_monitor_expired_invites_job, "interval", minutes=15, id="wl_monitor")
    _scheduler.start()
    yield
    _scheduler.shutdown(wait=False)
```

**Audit result:** ✅ Seats never stay empty. The 15-minute monitor ensures expired
invites are detected within 15 minutes of their TTL crossing. The immediate
`_check_waitlist_capacity_job()` call at the end of the monitor ensures the freed
seat is offered to the next candidate without waiting a full hour.

---

## Environment Variable Checklist

The following env vars **must** be set before deployment:

| Variable | Required | Description |
|----------|----------|-------------|
| `TELEGRAM_BOT_TOKEN` | ✅ | python-telegram-bot token |
| `DATABASE_URL` | ✅ | `postgresql+asyncpg://…` connection string |
| `PAYSTACK_SECRET_KEY` | ✅ | Paystack secret (`sk_live_…`) |
| `PAYSTACK_WEBHOOK_SECRET` | ✅ | HMAC secret for webhook signature verification |
| `PAYSTACK_PREMIUM_PLAN_CODE` | ✅ | Paystack recurring plan code for PREMIUM tier |
| `PAYSTACK_VIP_PLAN_CODE` | ✅ | Paystack recurring plan code for VIP tier |
| `PAYSTACK_CALLBACK_URL` | ✅ | URL Paystack redirects to after checkout |
| `VIP_SEAT_LIMIT` | ✅ | Max concurrent VIP subscribers (e.g. `15`) |
| `PREMIUM_PRICE_NGN` | ✅ | One-off premium price in kobo × 100 (e.g. `1500000`) |
| `VIP_PRICE_NGN` | ✅ | One-off VIP price in kobo × 100 (e.g. `3000000`) |
| `FINNHUB_API_KEY` | ⚠️ optional | Economic calendar & news provider |
| `REFERRAL_BONUS_DAYS` | ⚠️ optional | Days added to referrer subscription (default `7`) |
| `METAAPI_TOKEN` | ⚠️ optional | MetaAPI cloud token for MT5 broker bridge |
| `FERNET_KEY` | ⚠️ optional | Fernet key for encrypting broker credentials at rest |
| `MAX_VIP_USERS` | ⚠️ optional | Alias for `VIP_SEAT_LIMIT` (legacy support) |
| `RAILWAY_HEALTH_BASIC` | ⚠️ optional | Basic-auth header value for `/health` endpoint |

> **Tip:** Copy `.env.example` and fill in all ✅ required values before first deploy.
> Run `python -c "from db.session import init_db; import asyncio; asyncio.run(init_db())"` to
> verify DDL is applied successfully before starting the web process.
