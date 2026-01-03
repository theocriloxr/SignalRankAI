-- Manual Migration SQL for 0010_referral_enhancements
-- Run this directly in Railway Postgres if you need immediate fix

-- Add referral_count column to users table
ALTER TABLE users 
ADD COLUMN referral_count INTEGER NOT NULL DEFAULT 0;

-- Add referrer_notified_at column to referrals table
ALTER TABLE referrals 
ADD COLUMN referrer_notified_at TIMESTAMP NULL;

-- Verify columns were added
SELECT column_name, data_type, is_nullable 
FROM information_schema.columns 
WHERE table_name = 'users' AND column_name = 'referral_count';

SELECT column_name, data_type, is_nullable 
FROM information_schema.columns 
WHERE table_name = 'referrals' AND column_name = 'referrer_notified_at';

-- You should see:
-- referral_count | integer | NO
-- referrer_notified_at | timestamp without time zone | YES
