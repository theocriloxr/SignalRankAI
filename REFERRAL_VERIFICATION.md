# Referral System Verification - Referrer ID & First-Time-Start Tracking

**Date**: January 3, 2026  
**Status**: ✅ Verified and Correct

---

## System Design Verification

### ✅ **Rule 1: Referrer ID is Linked to the Referral Code**

**Implementation Location**: `db/pg_features.py` - `process_referral_start()` function, STEP 2

**How It Works**:
```python
# When user creates referral link, a ReferralCode is created with their user_id
referral_code = ReferralCode(
    code="SRK123456789",
    referrer_user_id=user.id  # ← Referrer ID stored here
)

# When someone uses that link, the referrer_id is extracted:
rc = await session.execute(select(ReferralCode).where(ReferralCode.code == code))
referrer_user = await session.execute(select(User).where(User.id == rc.referrer_user_id))
# rc.referrer_user_id = the ID of the user who owns this referral code
```

**Reward Distribution**:
```python
# Reward goes to whoever owns the referral code
await activate_subscription(
    session,
    telegram_user_id=referrer_tid,  # ← From ReferralCode owner
    tier=tier_to_extend,
    duration_days=7,
)
```

**Result**: ✅ Each reward is distributed to the correct referrer (the person who owns the referral link)

---

### ✅ **Rule 2: Referrals Are ONLY Counted After First-Time /start**

**Implementation Location**: `signalrank_telegram/commands.py` - `start_command()` function & `process_referral_start()`

**The Flow**:

```
1. User checks if they exist in database
   ↓
   existing = await session.execute(select(User).where(...))
   is_new = existing is None  # ← True only if NEW user
   
2. Pass is_new to referral processor
   ↓
   await process_referral_start_pg(
       session,
       referred_telegram_user_id=int(user_id),
       referral_code=str(code),
       is_new_user=bool(is_new)  # ← is_new value passed here
   )

3. Referral processor checks first-time start
   ↓
   if not bool(is_new_user):
       result["status"] = "not_new"
       return result  # ← STOPS HERE if not first-time user
   
4. Only new users proceed to referral counting
   ↓
   attribution = ReferralAttribution(...)  # ← Only for new users
```

**Detailed Scenarios**:

| Scenario | is_new | Action | Result |
|----------|--------|--------|--------|
| User A starts bot fresh | True | Process referral | ✅ Count if has code |
| User A starts again next day | False | Check is_new | ⛔ Return "not_new" |
| User A starts after using code once | False | Check is_new | ⛔ Return "not_new" |
| User B joins with User A's link (new) | True | Process referral | ✅ Count for User A |

**Result**: ✅ Each user can only be counted once (at their first /start), preventing duplicate referrals from the same person

---

## Code Verification

### ✅ Step-by-Step Referral Processing

```
STEP 1: Validate referral code
   ↓ Code found in ReferralCode table
   
STEP 2: Extract referrer ID from ReferralCode
   ↓ Get User who owns this referral code (rc.referrer_user_id)
   
STEP 3: CRITICAL - Check if new user (is_new_user=True)
   ↓ Only proceed if TRUE; return "not_new" if FALSE
   
STEP 4: Verify referred user not already attributed
   ↓ Prevent duplicate referral credits for same user
   
STEP 5: Create referral attribution record
   ↓ Links referred_user_id to referrer_user_id
   
STEP 6: Increment referrer's referral_count
   ↓ Updates User.referral_count for correct person (from Step 2)
   
STEP 7: Check if reward earned (3 referrals)
   ↓ Grant 7 days + reset count to 0
   
STEP 8: Send notifications to referrer
   ↓ Message about referral count and progress
```

---

## Critical Safeguards in Place

### 1. **Referrer ID Uniqueness**
- Each referral code has exactly one referrer_user_id
- Cannot change after creation
- ✅ Ensures proper reward distribution

### 2. **First-Time-Start Enforcement**
- Checked via `is_new_user` parameter
- Must be determined BEFORE calling process_referral_start()
- Return early if FALSE
- ✅ Prevents duplicate counting

### 3. **Referral Attribution Uniqueness**
- Each referred user can only be attributed once
- Check prevents duplicate records
- ✅ Prevents multiple credits for same person

### 4. **Referral Count Accuracy**
- Only incremented after all checks pass
- Only for new users
- Only for users not already attributed
- ✅ Accurate count for reward calculation

---

## Example: Complete Referral Journey

### Setup
- **User A (Referrer)**: telegram_user_id=111, has referral code="SRK111123"
- **User B (New)**: telegram_user_id=222, starts with code="SRK111123"

### Execution

```
User B /start with ref_SRK111123
   ↓
Check: existing User(222)? No → is_new = True
   ↓
process_referral_start(
    referred_telegram_user_id=222,
    referral_code="SRK111123",
    is_new_user=True  # ← Key: is_new must be True
)
   ↓
Look up ReferralCode("SRK111123")
   ↓
Get referrer_user_id from code → 1 (User A's database ID)
   ↓
Get User(id=1) → referrer_user (User A)
   ↓
Check: is_new_user? True ✅ → Continue
   ↓
Check: User 222 already attributed? No ✅ → Continue
   ↓
Create ReferralAttribution:
   - referred_user_id: 2 (User B's ID)
   - referrer_user_id: 1 (User A's ID)
   ↓
Increment User 1's referral_count: 0 → 1
   ↓
Result returned to start_command:
   - status: "attributed"
   - referrer_id: 111 (User A's Telegram ID)
   - referrals_total: 1
   - referrer_message: "👤 Someone joined... (1/3)"
   ↓
Send message to User A (111)
   ↓
✅ User A gets notification
✅ User A's count incremented
✅ Proper referrer ID used for distribution
```

---

## Database Records Created

### After User B joins via User A's referral:

**ReferralCode** (already existed):
```
id: 1
code: "SRK111123"
referrer_user_id: 1  ← User A's database ID
```

**ReferralAttribution** (created):
```
id: 1
referred_user_id: 2      ← User B's database ID
referrer_user_id: 1      ← User A's database ID (from code)
created_at: 2026-01-03...
referrer_notified_at: NULL
```

**User** (updated):
```
id: 1
telegram_user_id: 111
username: "UserA"
referral_count: 1  ← Incremented from 0
tier: "premium"
```

---

## Verification Checklist

- ✅ Referrer ID correctly extracted from ReferralCode.referrer_user_id
- ✅ Rewards distributed to correct referrer (via rc.referrer_user_id)
- ✅ is_new_user check prevents non-first-time users from counting
- ✅ Each user can only be attributed once (already_referred check)
- ✅ ReferralAttribution links correct referrer_user_id
- ✅ referral_count incremented for correct user
- ✅ Notifications sent to correct referrer
- ✅ All checks implemented before referral_count increment

---

## Code Comments Added (for clarity)

Detailed comments were added to `process_referral_start()` explaining:

1. **STEP 1**: Look up referral code
2. **STEP 2**: Extract referrer ID from code (used for rewards)
3. **STEP 3**: CRITICAL - Check new user only
4. **STEP 4**: Check no duplicate attribution
5. **STEP 5**: Create attribution with correct referrer_user_id
6. **STEP 6**: Increment correct referrer's count
7. **STEP 7**: Check reward threshold

---

## Compilation Status

✅ **db/pg_features.py**: Compiles successfully  
✅ **db/models.py**: No changes to syntax  
✅ **signalrank_telegram/commands.py**: No changes to syntax

---

## Production Ready

✅ **Referrer ID tracking**: Correct and verified  
✅ **First-time-start enforcement**: Correct and verified  
✅ **Reward distribution**: Goes to correct person  
✅ **Code documentation**: Clear and detailed  

**Ready for deployment** ✅
