# SignalRankAI Implementation Plan: Missing Features

## Executive Summary

Based on analyzing the codebase, the following 14 tables/components need implementation:

| # | Table/Feature | Status | Priority | Implementation Notes |
|---|--------------|--------|----------|----------------------|
| 1 | free_signal_queue | PARTIAL | CRITICAL | Model exists, NO APScheduler job |
| 2 | api_tokens | EXISTS | DONE | /api_key command already exists |
| 3 | user_webhooks | MODEL | HIGH | No /webhook command |
| 4 | mt5_credentials | MODEL | HIGH | No /connect_broker command |
| 5 | mt5_executions | MODEL | HIGH | No execution logging job |
| 6 | trades | MODEL | HIGH | No trade recording job |
| 7 | managed_assets | MODEL | HIGH | No startup seed job |
| 8 | economic_events | MODEL | HIGH | No scraper job |
| 9 | proxy_nodes | MODEL | MEDIUM | No proxy management |
| 10 | asset_live_metrics | MODEL | MEDIUM | No live updates |
| 11 | strategy_live_metrics | MODEL | MEDIUM | No live updates |
| 12 | rate_limit_tokens | LIKELY EXISTS | LOW | Check rate_limit.py |
| 13 | signal_corrections | MODEL | LOW | No correction tracking |
| 14 | market_candles | WARNING | NOT RECOMMENDED | Don't store 1-min candles |

---

## Priority Implementation Plan

### STEP 1 (CRITICAL): Add Free Signal Queue Distribution Job

**Current State:**
- `FreeSignalQueue` model exists in `db/models.py`
- `distribute_random_signals_to_free_users_job()` function exists in `signalrank_telegram/bot.py`
- **Problem:** Job NOT registered with APScheduler in `railway_main.py` or `bot.py`

**Implementation Required:**

1. **File: signalrank_telegram/signal_distribution.py**
   - Add `distribute_random_signals_to_free_users_job()` function
   - This function should query free users who haven't received signals today
   - Randomly select signals from the global pool
   - Distribute within daily limits (3 signals/day for FREE tier)

2. **Registration Locations (choose ONE):**
   - Option A: Register in `signalrank_telegram/bot.py` run_bot() scheduler
   - Option B: Register in `railway_main.py` _build_scheduler()

**Code to Add in signal_distribution.py:**

```python
def distribute_random_signals_to_free_users_job():
    """APScheduler job: distribute random signals to FREE users from global pool."""
    from utils.async_runner import run_sync
    from db.session import get_session
    from db.pg_features import queue_random_free_signals_for_all_users
    
    logger.info("🎲 Distributing random signals to FREE users...")
    
    async def _do_distribute():
        async with get_session() as session:
            count = await queue_random_free_signals_for_all_users(session)
            if count > 0:
                logger.info(f"📬 Queued signals for {count} FREE user(s)")
                await session.commit()
            else:
                logger.info("✅ All FREE users have reached daily limit or no new signals")
    
    try:
        run_sync(_do_distribute())
    except Exception as e:
        logger.error(f"❌ Error distributing signals to FREE users: {e}")
```

**Registration Code (add to bot.py run_bot()):**

```python
# In the BackgroundScheduler setup section, add:
scheduler.add_job(
    distribute_random_signals_to_free_users_job,
    "interval",
    minutes=30,  # Run every 30 minutes
    id="free_signal_distribution",
    replace_existing=True,
)
```

---

### STEP 2: Add Missing Telegram Commands

#### 2A. /webhook Command (UserWebhook)

**File:** `signalrank_telegram/commands.py`

```python
async def webhook_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Set or view your webhook URL for real-time signals.
    
    Usage:
      /webhook set <url> - Set webhook URL
      /webhook remove - Remove webhook
      /webhook (shows current)
    """
    if update.effective_user is None or update.message is None:
        return
    
    user_id = update.effective_user.id
    args = context.args or []
    
    if not args:
        # Show current webhook
        async with get_session() as session:
            wh = await get_user_webhook(session, user_id)
        if wh:
            await update.message.reply_text(
                f"🔗 Your webhook:\n{wh.webhook_url}\n"
                f"Active: {wh.is_active}\n"
                f"Use /webhook remove to delete."
            )
        else:
            await update.message.reply_text(
                "No webhook set.\n"
                "Usage: /webhook set <url>"
            )
        return
    
    cmd = args[0].lower()
    
    if cmd == "set" and len(args) >= 2:
        url = " ".join(args[1:])
        # Validate URL
        if not url.startswith(("http://", "https://")):
            await update.message.reply_text("⚠️ URL must start with http:// or https://")
            return
        
        async with get_session() as session:
            await set_user_webhook(session, user_id, url)
            await session.commit()
        
        await update.message.reply_text(f"✅ Webhook set: {url}")
    
    elif cmd == "remove":
        async with get_session() as session:
            await remove_user_webhook(session, user_id)
            await session.commit()
        
        await update.message.reply_text("✅ Webhook removed.")
    
    else:
        await update.message.reply_text(
            "Usage:\n"
            "/webhook set <url>\n"
            "/webhook remove\n"
            "/webhook (show current)"
        )
```

#### 2B. /connect_broker Command (MT5Credentials)

**File:** `signalrank_telegram/commands.py`

```python
async def connect_broker_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Connect your MT5 broker account for auto-trading.
    
    Usage:
      /connect_broker <login> <password> <server>
    
    Example:
      /connect_broker 123456 MyPass123 Exness-MT5-Real
    
    Credentials are encrypted with Fernet before storage.
    """
    if update.effective_user is None or update.message is None:
        return
    
    user_id = update.effective_user.id
    tier = _effective_tier(user_id)
    
    # Require PREMIUM or higher
    if tier_rank(tier) < tier_rank("PREMIUM"):
        await update.message.reply_text(
            "🔒 MT5 connection requires Premium or VIP.\n"
            "Use /upgrade to subscribe."
        )
        return
    
    args = context.args or []
    
    if len(args) < 3:
        await update.message.reply_text(
            "⚙️ <b>Connect MT5 Broker</b>\n\n"
            "Usage: <code>/connect_broker <login> <password> <server></code>\n\n"
            "Example:\n"
            "<code>/connect_broker 123456 MyPass123 Exness-MT5-Real</code>\n\n"
            "🔒 Your password is encrypted with AES-256.",
            parse_mode="HTML"
        )
        return
    
    mt5_login = args[0]
    mt5_password = args[1]
    mt5_server = " ".join(args[2:])
    
    # Delete message to prevent credential exposure
    try:
        await update.message.delete()
    except Exception:
        pass
    
    # Process connection
    try:
        from services.mt5_client import link_mt5_account
        result = await link_mt5_account(
            telegram_user_id=user_id,
            mt5_login=mt5_login,
            mt5_password=mt5_password,
            mt5_server=mt5_server,
        )
        
        if result.get("success"):
            await update.message.reply_text(
                f"✅ Broker Connected!\n\n"
                f"Server: {mt5_server}\n"
                f"Login: {mt5_login}"
            )
        else:
            await update.message.reply_text(
                f"❌ Connection failed: {result.get('error')}"
            )
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")
```

---

### STEP 3: Add Missing Scheduled Jobs

#### 3A. Managed Assets Seed Job

**File:** `signalrank_telegram/bot.py` (or new file)

```python
def seed_managed_assets_job():
    """Startup job: seed managed_assets table with default crypto/forex pairs."""
    from utils.async_runner import run_sync
    from db.session import get_session
    from db.pg_features import add_managed_asset
    from data.fetcher import get_asset_type
    
    DEFAULT_ASSETS = [
        # Crypto
        ("BTCUSDT", "crypto"),
        ("ETHUSDT", "crypto"),
        ("BNBUSDT", "crypto"),
        ("SOLUSDT", "crypto"),
        ("XRPUSDT", "crypto"),
        ("ADAUSDT", "crypto"),
        ("DOGEUSDT", "crypto"),
        # Forex
        ("EURUSD", "forex"),
        ("GBPUSD", "forex"),
        ("USDJPY", "forex"),
        ("AUDUSD", "forex"),
        ("USDCAD", "forex"),
    ]
    
    async def _seed():
        async with get_session() as session:
            for symbol, asset_type in DEFAULT_ASSETS:
                try:
                    await add_managed_asset(
                        session,
                        symbol=symbol,
                        asset_type=asset_type,
                        added_by=0,  # System
                    )
                except Exception:
                    pass  # Already exists
            await session.commit()
    
    try:
        run_sync(_seed())
        logger.info("✅ Managed assets seeded")
    except Exception as e:
        logger.error(f"❌ Seed managed assets failed: {e}")
```

#### 3B. Economic Events Scraper Job

**File:** `data/news.py` or new scraper module

```python
def scrape_economic_events_job():
    """Scheduled job: scrape upcoming economic events."""
    # Use existing news.py infrastructure or add new scraper
    # This is a placeholder - implement based on available data sources
    pass
```

#### 3C. Strategy Live Metrics Update Job

```python
def update_strategy_live_metrics_job():
    """Update strategy_live_metrics with real-time expectancy."""
    from utils.async_runner import run_sync
    from db.session import get_session
    from sqlalchemy import update
    from db.models import StrategyLiveMetric, StrategyStat
    
    async def _update():
        async with get_session() as session:
            # Get latest strategy stats
            stats = session.query(StrategyStat).all()
            for stat in stats:
                # Calculate live expectancy
                if stat.trades > 0:
                    expectancy = (stat.win_rate * stat.avg_r) - (1 - stat.win_rate)
                    await session.execute(
                        update(StrategyLiveMetric).where(
                            StrategyLiveMetric.strategy_name == stat.strategy_name
                        ).values(
                            expectancy=expectancy,
                            updated_at=utcnow()
                        )
                    )
            await session.commit()
    
    try:
        run_sync(_update())
        logger.info("✅ Strategy metrics updated")
    except Exception as e:
        logger.error(f"❌ Strategy metrics update failed: {e}")
```

---

## File Modification Summary

| File | Changes Required |
|------|------------------|
| `signalrank_telegram/signal_distribution.py` | Add distribute_random_signals_to_free_users_job() + register with scheduler |
| `signalrank_telegram/commands.py` | Add /webhook and /connect_broker commands |
| `signalrank_telegram/bot.py` | Register new jobs with BackgroundScheduler |
| `db/pg_features.py` | Add helper functions for webhook/MT5 if needed |
| `railway_main.py` | Optionally register jobs here instead of bot.py |

---

## Testing Checklist

- [ ] Verify free_signal_queue distribution runs every 30 minutes
- [ ] Test /webhook command sets and removes webhooks
- [ ] Test /connect_broker command links MT5 accounts
- [ ] Verify managed_assets seeded on startup
- [ ] Verify economic_events scraper runs
- [ ] Verify strategy_live_metrics updates

---

## Implementation Notes

1. **Security:** Always encrypt MT5 passwords before storage (Fernet)
2. **Delete Credentials:** Use message.delete() to prevent credential exposure
3. **Rate Limiting:** Respect tier-based rate limits for all commands
4. **Error Handling:** Graceful degradation if external services fail
