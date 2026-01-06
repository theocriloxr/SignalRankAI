# Railway Environment Variables - Quick Reference

## ✅ Required (All Deployments)

```bash
# Database
DATABASE_URL=postgresql://...  # Provided by Railway Postgres plugin

# Telegram
TELEGRAM_TOKEN=1234567890:ABC...  # From @BotFather

# Payments
PAYSTACK_SECRET_KEY=sk_live_...  # From Paystack dashboard
PAYSTACK_WEBHOOK_SECRET=...  # From Paystack webhook settings

# Owner Access
OWNER_TELEGRAM_ID=123456789  # Your Telegram user ID
BYPASS_KEY=your_secret_key_here  # For /unlock command

# Web Service
PUBLIC_BASE_URL=https://your-app.railway.app  # Your Railway domain
ADMIN_API_TOKEN=your_admin_token  # For /admin/killswitch endpoints
```

## 🎯 Recommended (Production)

```bash
# Auto-migrations
AUTO_MIGRATE=true  # Runs Alembic migrations on boot (default: true)

# VIP Seats
VIP_SEAT_LIMIT=15  # Maximum VIP subscribers (default: 15)

# Crypto Trading
CRYPTO_TRENDING_TOP_N=10  # Top N trending crypto pairs (default: 10)

# Signal Quality
PREMIUM_SCORE_THRESHOLD=70  # Minimum score for signal storage (default: 70)
ULTRA_QUALITY_ENABLED=false  # Enable ultra-strict filter (default: false)
```

## 🆕 New Features (Optional)

```bash
# Stock Trading (New!)
STOCK_TRADING_ENABLED=true  # Enable stock signals (default: false)
TRADABLE_ASSETS=AAPL,MSFT,TSLA,NVDA  # Optional: specific stocks only

# Signal Validation (New!)
ENGINE_SIGNAL_DEBUG=true  # Log validation failures (default: false)

# Deduplication
DELIVERY_DEDUPE_HOURS=24  # Deduplication window hours (default: 24)
```

## 📊 Data Providers

### Yahoo Finance (Free, No API Key)
```bash
# No configuration needed - works out of the box
# Used for: Crypto + Stocks
# Works in: Nigeria (not geo-blocked)
```

### AlphaVantage (Optional, FX Trading)
```bash
ALPHAVANTAGE_API_KEY=your_key_here  # From alphavantage.co (free tier: 5 calls/min)
FX_PAIRS=EUR/USD,GBP/USD  # Comma-separated FX pairs
FX_MAX_PAIRS=3  # Limit to avoid rate limits (free tier)
FX_TIMEFRAMES=1d  # Comma-separated timeframes (1d recommended for free tier)
ALPHAVANTAGE_MIN_SECONDS_BETWEEN_CALLS=15  # Rate limit protection
```

### CryptoCompare (Optional, Backup)
```bash
CRYPTOCOMPARE_API_KEY=your_key_here  # From cryptocompare.com (optional)
```

## 🔧 Development & Testing

```bash
# Dry Run (No Signal Storage/Dispatch)
DRY_RUN=true  # Test mode - signals printed but not stored

# Payments Testing
PAYMENTS_ENABLED=false  # Disable real payments for testing

# Fresh Database Start (DANGEROUS!)
FRESH_START=true  # Wipes all Postgres data on next boot (use once, then remove)
```

## 📦 Paystack Plans

```bash
# Create these plans in Paystack dashboard first
PAYSTACK_PLAN_CODE_PREMIUM_MONTHLY=PLN_xxx
PAYSTACK_PLAN_CODE_PREMIUM_QUARTERLY=PLN_xxx
PAYSTACK_PLAN_CODE_PREMIUM_SEMIANNUAL=PLN_xxx
PAYSTACK_PLAN_CODE_VIP_MONTHLY=PLN_xxx
```

## 🚀 Single-Service Railway Deployment

### Start Command
```bash
python main.py
```

### Environment Variables (Same as above, plus)
```bash
RUN_MODE=all  # Run all components in one container
PORT=8000  # Railway provides this automatically
```

## 📝 Multi-Service Railway Deployment

### 4 Services (web, bot, engine, worker)

Each service uses: `python main.py`

Set different `RUN_MODE` for each:

#### Service 1: Web
```bash
RUN_MODE=web
```

#### Service 2: Bot
```bash
RUN_MODE=bot
```

#### Service 3: Engine
```bash
RUN_MODE=engine
```

#### Service 4: Worker
```bash
RUN_MODE=worker
```

All services share the same environment variables (DATABASE_URL, TELEGRAM_TOKEN, etc.)

## 🎛️ Advanced Configuration

### ML Training
```bash
ML_TRAIN_INTERVAL_SECONDS=86400  # Daily retrain (default: 86400 = 24h)
```

### Signal Scoring
```bash
VIP_SCORE_THRESHOLD=72  # VIP tier score minimum (default: 72)
PREMIUM_SCORE_THRESHOLD=70  # Premium tier score minimum (default: 70)
```

### Engine Tuning
```bash
ENGINE_CYCLE_LOG=true  # Log each engine cycle stats (default: true)
ENGINE_SIGNAL_DEBUG=false  # Verbose signal debugging (default: false)
STORE_SIGNAL_TRACE=false  # Show stack trace on store failures (default: false)
```

### Position Sizing
```bash
ACCOUNT_EQUITY=10000  # Virtual account size for position sizing (default: 10000)
```

## 🔒 Security Best Practices

1. **Never commit secrets** to git (use Railway dashboard)
2. **Rotate BYPASS_KEY** monthly
3. **Use ADMIN_API_TOKEN** for kill switch endpoints
4. **Keep PAYSTACK_WEBHOOK_SECRET** secret
5. **Set strong OWNER_TELEGRAM_ID** verification

## 🐛 Debugging

### Check Logs
```bash
railway logs --service signalrank-ai
```

### Enable Debug Logging
```bash
ENGINE_SIGNAL_DEBUG=true
ENGINE_CYCLE_LOG=true
STORE_SIGNAL_TRACE=true
```

### Check Database
```bash
railway run psql
```

## 📊 Monitoring

### Health Check
```
GET https://your-app.railway.app/health
```

### Metrics
```
GET https://your-app.railway.app/metrics
```

### Paystack Webhook
```
POST https://your-app.railway.app/webhooks/paystack
```

## 🎯 Quick Start Checklist

### Minimum Required (Railway Single Service)
- [ ] `DATABASE_URL` (from Railway Postgres plugin)
- [ ] `TELEGRAM_TOKEN` (from @BotFather)
- [ ] `PAYSTACK_SECRET_KEY` (from Paystack)
- [ ] `PAYSTACK_WEBHOOK_SECRET` (from Paystack)
- [ ] `OWNER_TELEGRAM_ID` (your Telegram ID)
- [ ] `BYPASS_KEY` (create a strong random string)
- [ ] `PUBLIC_BASE_URL` (your Railway domain)
- [ ] `ADMIN_API_TOKEN` (create a strong random string)
- [ ] `RUN_MODE=all` (single-service mode)

### Optional But Recommended
- [ ] `STOCK_TRADING_ENABLED=true` (enable stocks)
- [ ] `AUTO_MIGRATE=true` (auto-run migrations)
- [ ] `VIP_SEAT_LIMIT=15` (limit VIP seats)
- [ ] `PREMIUM_SCORE_THRESHOLD=70` (signal quality)

### Test Your Deployment
- [ ] Visit `/health` endpoint
- [ ] Send `/start` to your bot
- [ ] Check Railway logs for errors
- [ ] Test Paystack webhook with test payment

---

**Need Help?**
- Check logs: `railway logs --service signalrank-ai`
- Restart service: `railway restart --service signalrank-ai`
- Check environment: `railway vars list --service signalrank-ai`
