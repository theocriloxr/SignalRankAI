# SignalRankAI - Quick Start Guide

## 📋 Pre-Deployment Checklist

Before deploying to production, verify these requirements:

### 1. ✅ Core Requirements
- [ ] PostgreSQL database created and accessible
- [ ] Telegram token obtained from @BotFather
- [ ] Bot owner Telegram ID obtained
- [ ] `.env` file created with at least these variables:
  ```
  DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/db
  TELEGRAM_BOT_TOKEN=<from_botfather>
  OWNER_TELEGRAM_ID=<your_id>
  ```

### 2. ✅ API Keys (Free Tier Available)
- [ ] News API key (newsapi.org) - Free: 100 req/day
- [ ] Alpha Vantage key (alphavantage.co) - Free: 5 req/min
- [ ] (Optional) Binance API - Free
- [ ] (Optional) OANDA token - Free demo account

### 3. ✅ Database Schema
- [ ] Run migrations: `python -m alembic upgrade head`
- [ ] Or set `AUTO_MIGRATE=1` for automatic setup
- [ ] Verify migrations completed: `SELECT version_num FROM alembic_version;`

### 4. ✅ System Configuration
- [ ] Set `RUN_MODE=all` for monolith
- [ ] Set `RUN_ENGINE_LOOP=1` for signal generation
- [ ] Set `RUN_WORKER_LOOP=1` for outcome tracking
- [ ] Set `STARTUP_STRICT_SCHEMA_READY=1` for Railway

### 5. ✅ Verify Functionality
Run verification script:
```bash
python verify_system.py
```

Expected output:
```
Total Checks: 25
Passed: 25 ✅
Failed: 0 ❌
Success Rate: 100.0%

✅ All critical systems operational!
```

---

## 🚀 Local Development Start

### 1. Setup Environment
```bash
# Clone repository
git clone <repo-url>
cd SignalRankAI

# Create Python venv
python3.11 -m venv venv
source venv/bin/activate  # or: venv\Scripts\activate on Windows

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure Database
```bash
# Create PostgreSQL database
createdb signalrank_ai

# Copy env template
cp .env.complete .env

# Edit .env with your values
nano .env  # Edit DATABASE_URL, TELEGRAM_BOT_TOKEN, OWNER_TELEGRAM_ID

# Run migrations
python -m alembic upgrade head
```

### 3. Start Bot (3 Options)

**Option A: Engine Only** (signal generation)
```bash
python main.py
# Uses RUN_MODE from config, defaults to engine
```

**Option B: All Services in One** (Recommended for local)
```bash
uvicorn railway_main:app --reload --port 8000
# Runs FastAPI + Engine + Worker + Bot in single process
```

**Option C: By Service** (Development)
```bash
# Terminal 1: Engine
RUN_MODE=engine python main.py

# Terminal 2: Worker
RUN_MODE=worker python main.py

# Terminal 3: Telegram Bot
RUN_MODE=bot python main.py

# Terminal 4: Web API
RUN_MODE=web python main.py
```

### 4. Test in Telegram

Send commands to bot:
```
/start          # Begin using bot
/help           # Command menu
/signals        # View active signals
/account        # Your account info
/status         # Current stats
/myid           # Your user ID (useful for OWNER_TELEGRAM_ID)
```

### 5. Verify in Logs

Expected logs every 30 seconds:
```
[engine] heartbeat: cycle=1 running
[engine] batch=5 wakeup=1 classes={'crypto': 3, 'fx': 2}
[engine] pipeline: starting asset=BTCUSD
[engine] batch_complete ... dispatched=2
```

---

## ☁️ Railway Deployment

### 1. Setup Railway Project
```bash
# Install Railway CLI
npm i -g @railway/cli

# Login
railway login

# Link to existing project
railway link

# Or create new
railway init
```

### 2. Add Services
```bash
# Add PostgreSQL
railway add --plugin postgres

# Add Redis (optional but recommended)
railway add --plugin redis
```

### 3. Configure Environment
```bash
# Set critical variables
railway env add DATABASE_URL <from-postgres-plugin>
railway env add TELEGRAM_BOT_TOKEN <your-token>
railway env add OWNER_TELEGRAM_ID <your-id>
railway env add NEWS_API_KEY <from-newsapi.org>
railway env add ALPHAVANTAGE_API_KEY <from-alphavantage>

# Set optimizations for Railway
railway env add STARTUP_STRICT_SCHEMA_READY 1
railway env add AUTO_MIGRATE 1
railway env add DB_POOL_SIZE 5
railway env add XGB_NTHREAD 1
```

### 4. Deploy
```bash
# Deploy app
railway up

# Watch logs
railway logs -f

# Expected on first deploy:
# [startup] DB startup ops begin
# [startup] DB startup ops end
# [startup] Engine loop task created
# [startup] Worker loop task created
# [engine] heartbeat: cycle=1 running
```

### 5. Test Webhook
```bash
# Get your Railway domain
railway open telegram.app  # Shows public domain

# Send test command to bot
/ops_health

# Should show webhook URL registered
```

---

## 🔧 Common Configuration Patterns

### Development (Local SQLite Fallback)
```bash
DATABASE_URL=sqlite:///./signalrank.db
REDIS_URL=
RUN_MODE=all
AUTO_MIGRATE=1
STARTUP_STRICT_SCHEMA_READY=0
LOG_LEVEL=DEBUG
```

### Production (Railway)
```bash
DATABASE_URL=postgresql://...
REDIS_URL=redis://...
RUN_MODE=all
AUTO_MIGRATE=1
STARTUP_STRICT_SCHEMA_READY=1
STARTUP_OPS_TIMEOUT_SECONDS=180
LOG_LEVEL=INFO
```

### Testing
```bash
DATABASE_URL=postgresql://test:test@localhost/test_db
DRY_RUN=true
PAPER_MODE=true
ENGINE_CYCLE_SLEEP_SECONDS=5
OUTCOME_CHECK_INTERVAL_SECONDS=2
```

### Memory-Constrained (Railway free tier)
```bash
DB_POOL_SIZE=1
DB_MAX_OVERFLOW=0
XGB_NTHREAD=1
CRYPTO_WS_ENABLED=false
ML_TRAIN_ENABLED=false
ENABLE_NEWS=false
CYCLE_BATCH_SIZE=5
ENGINE_UNIVERSE_CAP=5
```

---

## 📊 Monitoring & Debugging

### View Logs
```bash
# Local
tail -f logs/app.log | grep engine

# Railway
railway logs -f | grep engine
railway logs -f | grep webhook
railway logs -f | grep error
```

### Check Database
```bash
# Local
psql signalrank_ai

# Railway
railway conn postgres

# Query examples
SELECT COUNT(*) FROM signals;
SELECT COUNT(*) FROM users;
SELECT COUNT(*) FROM outcomes WHERE closes_at IS NOT NULL;
SELECT * FROM signals ORDER BY created_at DESC LIMIT 5;
```

### Check Bot Status
Send `/ops_health` command to bot, should show:
```
🤖 System Health Report
├─ Web API: ✅ Running
├─ Engine: ✅ Running (cycle=123)
├─ Worker: ✅ Running
├─ Telegram Bot: ✅ Connected
├─ Database: ✅ Connected
├─ Redis: ✅ Connected (or ⚠️ Unavailable)
├─ Telegram Webhook: ✅ Registered
└─ Signals: 156 generated today
```

---

## 🐛 Troubleshooting

### "signals not generating"
1. Check `/ops_health` command
2. Look for `[engine] heartbeat:` in logs
3. Verify `RUN_ENGINE_LOOP=1`
4. Check database connection: `/selfcheck`
5. Restart: `railway redeploy`

### "webhook not receiving updates"
1. Check Telegram webhook URL in `/ops_health`
2. Should match your Railway domain
3. If not registered, restart: `railway redeploy`
4. Try fallback polling: `WEBHOOK_QUEUE_USE_REDIS=0`

### "out of memory / OOMKilled"
1. Reduce: `CYCLE_BATCH_SIZE=5`
2. Disable ML: `ML_TRAIN_ENABLED=false`
3. Disable websocker: `CRYPTO_WS_ENABLED=false`
4. Reduce model threads: `XGB_NTHREAD=1`
5. Upgrade Railway tier

### "database connection errors"
1. Check `DATABASE_URL` is correct
2. Verify PostgreSQL is running
3. Try: `DB_POOL_SIZE=1 DB_MAX_OVERFLOW=0`
4. Check logs: `railway logs | grep -i database`

---

## ✨ Next Steps After Deployment

### 1. Customize Asset List
Set which assets to trade:
```bash
railway env add TRADABLE_ASSETS "BTCUSD,EURUSD,AAPL"
railway env add FX_PAIRS "EURUSD,GBPUSD"
```

### 2. Configure Signal Thresholds
```bash
railway env add MIN_SCORE_FREE 80
railway env add MIN_SCORE_PREMIUM 70
railway env add MIN_SCORE_VIP 75
```

### 3. Enable Payments (Optional)
```bash
railway env add PAYMENTS_ENABLED true
railway env add PAYSTACK_SECRET_KEY <key>
```

### 4. Enable AI Analysis (Optional)
```bash
railway env add GEMINI_API_KEY <key>
railway env add GEMINI_ANALYSIS_ENABLED true
```

### 5. Setup Monitoring (Optional)
```bash
railway env add SENTRY_DSN <from-sentry.io>
```

---

## 📚 Full Documentation

See [SYSTEM_DOCUMENTATION.md](./SYSTEM_DOCUMENTATION.md) for:
- Complete command reference
- Database schema details
- Configuration options
- Feature matrix
- API endpoints
- Advanced troubleshooting

---

## 🆘 Getting Help

### Common Resources
- Bot `/help` command - Command list
- Bot `/faq` command - Common questions
- Bot `/support` command - Contact support
- This file - Quick start guide
- SYSTEM_DOCUMENTATION.md - Complete reference

### Where to Check
1. **Error logs**: `railway logs`
2. **System health**: `/ops_health` command
3. **Database**: `railway conn postgres`
4. **Redis**: Check if REDIS_URL is set

---

## ✅ Success Indicators

You've done it right if:

- ✅ `/help` responds instantly in Telegram
- ✅ `/signals` shows recent signals (or "no signals yet")
- ✅ `[engine] heartbeat:` appears every 30s in logs
- ✅ `/status` shows correct stats
- ✅ `/ops_health` shows all systems ✅
- ✅ No ERROR logs in `railway logs`
- ✅ Daily signal count > 0 (after 1 hour)

Good luck! 🚀
