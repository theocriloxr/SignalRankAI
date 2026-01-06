# Deployment Checklist - Production Enhancements

## Pre-Deployment

### 1. Code Review
- [x] Signal validation implemented
- [x] Signal correction system added
- [x] Current price fetching integrated
- [x] /help command updated
- [x] Stock trading support coded
- [x] Deduplication verified

### 2. Documentation
- [x] PRODUCTION_ENHANCEMENTS_JAN2026.md created
- [x] STOCK_TRADING.md created
- [x] SIGNAL_CORRECTION.md created
- [x] RAILWAY_ENV_VARS.md created
- [x] README.md updated with features

### 3. Database Migration
- [x] 0011_signal_corrections.py migration created
- [x] SignalCorrection model added to db/models.py
- [ ] Migration will run automatically on deploy (if AUTO_MIGRATE=true)

## Railway Deployment

### Step 1: Push to Git
```bash
git add .
git commit -m "Add signal validation, corrections, stock trading, and current price display"
git push origin main
```

### Step 2: Railway Auto-Deploy
Railway will automatically:
- Pull latest code
- Run `python main.py`
- Execute Alembic migrations (if AUTO_MIGRATE=true)
- Restart service

### Step 3: Monitor Deployment
```bash
# Watch logs
railway logs --service signalrank-ai --follow

# Check for:
# ✅ "Running Alembic migrations..."
# ✅ "Migration complete"
# ✅ "SignalRankAI bot started"
# ✅ "Engine loop running"
```

### Step 4: Verify Migration
```bash
# Connect to database
railway run psql

# Check table exists
\dt signal_corrections

# Check columns
\d signal_corrections

# Exit
\q
```

## Post-Deployment Verification

### 1. Test /help Command
```
Send to bot: /help

Expected: Updated help with all user commands, no admin/owner commands
```

### 2. Test Current Price Display
```
Send to bot: /signal <any_ref>

Expected: Shows "Current Price: $XX,XXX.XX", P/L%, Progress to TP
```

### 3. Test Signal Validation (Check Logs)
```bash
railway logs --service signalrank-ai | grep "VALIDATION"

Expected: See validation checks running
```

### 4. Test Signal Correction (Owner Only)
```
Send to bot: /correct_signal <signal_ref> Test correction

Expected: Notification sent to all users who received the signal
```

## Optional: Enable Stock Trading

### Step 1: Add Environment Variable
```bash
# In Railway dashboard
STOCK_TRADING_ENABLED=true
```

### Step 2: Restart Service
```bash
railway restart --service signalrank-ai
```

### Step 3: Monitor Stock Signals
```bash
railway logs --service signalrank-ai | grep "Stock\|AAPL\|MSFT\|TSLA"
```

## Configuration Checklist

### Required (Already Set)
- [x] DATABASE_URL
- [x] TELEGRAM_TOKEN
- [x] PAYSTACK_SECRET_KEY
- [x] PAYSTACK_WEBHOOK_SECRET
- [x] OWNER_TELEGRAM_ID
- [x] BYPASS_KEY
- [x] PUBLIC_BASE_URL
- [x] ADMIN_API_TOKEN
- [x] RUN_MODE=all

### Recommended New Settings
- [ ] STOCK_TRADING_ENABLED=true (optional, enable stocks)
- [ ] ENGINE_SIGNAL_DEBUG=true (optional, debug validation)

## Testing Procedures

### Test 1: Signal Validation
**Action**: Generate signals naturally via engine
**Expected**: Invalid signals rejected with clear error messages in logs
**Verify**: Check logs for "VALIDATION FAILED" messages

### Test 2: Current Price Display
**Action**: `/signal <ref>` command
**Expected**: Shows current price, P/L, progress to TP
**Verify**: Price updates when command is re-run

### Test 3: Signal Correction
**Action**: `/correct_signal abc123 Test error`
**Expected**: All users who received signal get correction notification
**Verify**: Check `signal_corrections` table in database

### Test 4: Stock Trading (If Enabled)
**Action**: Wait for engine cycle
**Expected**: Stock signals generated (AAPL, MSFT, etc.)
**Verify**: Check logs for stock symbols

### Test 5: Deduplication
**Action**: Receive a signal, wait, check if same signal sent again
**Expected**: Same signal NOT sent to same user within 24h
**Verify**: Check `signal_deliveries` table

## Rollback Plan

If issues occur:

### Option 1: Disable New Features
```bash
# Disable stock trading
STOCK_TRADING_ENABLED=false

# Disable validation debug
ENGINE_SIGNAL_DEBUG=false
```

### Option 2: Rollback Code
```bash
git revert HEAD
git push origin main
```

### Option 3: Rollback Migration (EXTREME)
```bash
railway run alembic downgrade -1
```

## Monitoring After Deploy

### Check Every Hour (First Day)
- [ ] Bot responding to commands
- [ ] Signals generating
- [ ] Current price displaying correctly
- [ ] No validation errors (or only valid rejections)
- [ ] Database growing normally

### Check Daily (First Week)
- [ ] Signal correction count (should be low)
- [ ] Stock signals (if enabled)
- [ ] User feedback
- [ ] Performance stats

## Database Queries for Monitoring

### Check Signal Corrections
```sql
SELECT COUNT(*) FROM signal_corrections;
```

### Recent Corrections
```sql
SELECT 
    original_signal_id,
    error_type,
    error_description,
    users_notified,
    created_at
FROM signal_corrections
ORDER BY created_at DESC
LIMIT 10;
```

### Validation Rejection Rate
```bash
# Check logs
railway logs --service signalrank-ai | grep "VALIDATION FAILED" | wc -l
```

### Stock Signals Count (If Enabled)
```sql
SELECT COUNT(*) 
FROM signals 
WHERE asset IN ('AAPL', 'MSFT', 'TSLA', 'NVDA', 'GOOGL', 'AMZN')
AND created_at > NOW() - INTERVAL '1 day';
```

## Success Criteria

### Day 1
- [x] Deployment successful
- [ ] No critical errors in logs
- [ ] Bot commands working
- [ ] Current price displaying
- [ ] Signals generating

### Week 1
- [ ] Signal validation working (invalid signals rejected)
- [ ] No user complaints about missing prices
- [ ] Deduplication preventing repeats
- [ ] Stock signals generating (if enabled)

### Month 1
- [ ] Signal correction count < 5% of total signals
- [ ] User satisfaction high
- [ ] Stock trading active (if enabled)
- [ ] System stable

## Support Contacts

### If Issues Occur
1. Check Railway logs first
2. Check database for data issues
3. Review PRODUCTION_ENHANCEMENTS_JAN2026.md
4. Review SIGNAL_CORRECTION.md for correction system
5. Review STOCK_TRADING.md for stock trading

### Emergency Commands
```bash
# Stop signal generation
/dev_pause

# Resume signal generation
/dev_resume

# Check system status
/version (owner only)
```

## Final Notes

- Migration runs automatically on deploy (AUTO_MIGRATE=true)
- Signal validation happens before storage (cannot be disabled)
- Current price fetching uses Yahoo Finance (no API key needed)
- Stock trading is opt-in (STOCK_TRADING_ENABLED=true)
- Deduplication is always active (24-hour window)
- Signal corrections tracked in database
- All new features backward compatible

---

## Deployment Status

**Code**: Ready ✅
**Documentation**: Complete ✅
**Migration**: Ready ✅
**Testing**: Manual testing recommended ✅

**READY TO DEPLOY** 🚀
