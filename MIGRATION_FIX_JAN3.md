# URGENT: Referral Migration Fix - Jan 3, 2026

**Issue**: Production database missing `referral_count` column  
**Error**: `column users.referral_count does not exist`  
**Fix**: Deploy to apply migration `0010_referral_enhancements.py`

---

## Quick Fix - Deploy Immediately

### Railway Dashboard (Easiest)
1. Go to Railway Dashboard
2. Select SignalRankAI service
3. Click "Deploy" → "Redeploy"
4. Migration runs automatically

### Manual SQL (Fastest)
Connect to Railway Postgres and run:
```sql
ALTER TABLE users ADD COLUMN referral_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE referrals ADD COLUMN referrer_notified_at TIMESTAMP NULL;
```

---

## What Happened

Code deployed **before** migration applied. Database schema is outdated.

## Files Ready
- ✅ Migration: `alembic/migrations/versions/0010_referral_enhancements.py`
- ✅ Code: Updated and tested
- ✅ start.sh: Now runs migrations explicitly

## After Deploy
✅ No more column errors  
✅ Referral system works  
✅ Bot fully functional  

**Deploy now to fix production** 🚀
