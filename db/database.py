def fetch_user_trades(user_id):
    # Returns all trades (signals) for a user from the signals table
    with closing(sqlite3.connect(DB_PATH)) as conn:
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            asset TEXT,
            timeframe TEXT,
            direction TEXT,
            entry REAL,
            stop_loss REAL,
            take_profit REAL,
            rr_ratio REAL,
            strategy_name TEXT,
            strategy_group TEXT,
            strength REAL,
            score INTEGER,
            risk_profile TEXT,
            released INTEGER DEFAULT 0,
            user_id INTEGER
        )''')
        c.execute('SELECT * FROM signals WHERE user_id=?', (user_id,))
        return c.fetchall()
def get_all_user_ids():
    # Returns a list of all user IDs with a subscription (active or expired)
    with closing(sqlite3.connect(DB_PATH)) as conn:
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS subscriptions (
            user_id INTEGER PRIMARY KEY,
            tier TEXT,
            start_date TEXT,
            expiry_date TEXT,
            payment_ref TEXT,
            bypass_key_used INTEGER DEFAULT 0
        )''')
        c.execute('SELECT user_id FROM subscriptions')
        rows = c.fetchall()
        return [row[0] for row in rows]


def get_vip_seat_limit() -> int:
    try:
        return max(1, int(os.getenv("VIP_SEAT_LIMIT", "15")))
    except Exception:
        return 15


def count_active_vip_seats(limit: int | None = None) -> tuple[int, int, int]:
    """Return (used, remaining, limit) for VIP seats.

    VIP seats count only active VIP subscribers and excludes:
    - owners (OWNER_IDS)
    - bypassed users (bypass_key_used=1)

    Seats naturally free up when `expiry_date` passes.
    """
    if limit is None:
        limit = get_vip_seat_limit()

    now = datetime.now().isoformat()
    with closing(sqlite3.connect(DB_PATH)) as conn:
        c = conn.cursor()
        c.execute(
            '''CREATE TABLE IF NOT EXISTS subscriptions (
                user_id INTEGER PRIMARY KEY,
                tier TEXT,
                start_date TEXT,
                expiry_date TEXT,
                payment_ref TEXT,
                bypass_key_used INTEGER DEFAULT 0
            )'''
        )

        owner_ids = tuple(int(x) for x in OWNER_IDS) if OWNER_IDS else tuple()
        if owner_ids:
            placeholders = ",".join(["?"] * len(owner_ids))
            query = (
                f"SELECT COUNT(*) FROM subscriptions "
                f"WHERE tier LIKE 'VIP%' "
                f"AND bypass_key_used=0 "
                f"AND expiry_date > ? "
                f"AND user_id NOT IN ({placeholders})"
            )
            params = (now, *owner_ids)
            c.execute(query, params)
        else:
            c.execute(
                "SELECT COUNT(*) FROM subscriptions WHERE tier LIKE 'VIP%' AND bypass_key_used=0 AND expiry_date > ?",
                (now,),
            )
        used = int((c.fetchone() or [0])[0])

    remaining = max(0, int(limit) - used)
    return used, remaining, int(limit)
def approve_extra_signals(user_id, count):
    # Admin approves extra signals for a user for today
    with closing(sqlite3.connect(DB_PATH)) as conn:
        c = conn.cursor()
        today = datetime.now().strftime('%Y-%m-%d')
        c.execute('''CREATE TABLE IF NOT EXISTS extra_signal_log (user_id INTEGER, date TEXT, count INTEGER, used INTEGER DEFAULT 0, PRIMARY KEY(user_id, date))''')
        c.execute('REPLACE INTO extra_signal_log (user_id, date, count, used) VALUES (?, ?, ?, 0)', (user_id, today, count))
        conn.commit()

def get_extra_signals_left(user_id):
    # Returns how many extra signals user has left for today
    with closing(sqlite3.connect(DB_PATH)) as conn:
        c = conn.cursor()
        today = datetime.now().strftime('%Y-%m-%d')
        c.execute('''CREATE TABLE IF NOT EXISTS extra_signal_log (user_id INTEGER, date TEXT, count INTEGER, used INTEGER DEFAULT 0, PRIMARY KEY(user_id, date))''')
        c.execute('SELECT count, used FROM extra_signal_log WHERE user_id=? AND date=?', (user_id, today))
        row = c.fetchone()
        if not row:
            return 0
        return max(0, row[0] - row[1])

def increment_extra_signal_count(user_id):
    # Increment used count for extra signals
    with closing(sqlite3.connect(DB_PATH)) as conn:
        c = conn.cursor()
        today = datetime.now().strftime('%Y-%m-%d')
        c.execute('''UPDATE extra_signal_log SET used = used + 1 WHERE user_id=? AND date=?''', (user_id, today))
        conn.commit()
def approve_extra_signals(user_id, count):
    # Admin approves extra signals for a user for today
    with closing(sqlite3.connect(DB_PATH)) as conn:
        c = conn.cursor()
        today = datetime.now().strftime('%Y-%m-%d')
        c.execute('''CREATE TABLE IF NOT EXISTS extra_signal_log (user_id INTEGER, date TEXT, count INTEGER, used INTEGER DEFAULT 0, PRIMARY KEY(user_id, date))''')
        c.execute('REPLACE INTO extra_signal_log (user_id, date, count, used) VALUES (?, ?, ?, 0)', (user_id, today, count))
        conn.commit()

def get_extra_signals_left(user_id):
    # Returns how many extra signals user has left for today
    with closing(sqlite3.connect(DB_PATH)) as conn:
        c = conn.cursor()
        today = datetime.now().strftime('%Y-%m-%d')
        c.execute('''CREATE TABLE IF NOT EXISTS extra_signal_log (user_id INTEGER, date TEXT, count INTEGER, used INTEGER DEFAULT 0, PRIMARY KEY(user_id, date))''')
        c.execute('SELECT count, used FROM extra_signal_log WHERE user_id=? AND date=?', (user_id, today))
        row = c.fetchone()
        if not row:
            return 0
        return max(0, row[0] - row[1])

def increment_extra_signal_count(user_id):
    # Increment used count for extra signals
    with closing(sqlite3.connect(DB_PATH)) as conn:
        c = conn.cursor()
        today = datetime.now().strftime('%Y-%m-%d')
        c.execute('''UPDATE extra_signal_log SET used = used + 1 WHERE user_id=? AND date=?''', (user_id, today))
        conn.commit()
def get_free_signals_sent_today(user_id):
    # Track free signals sent per user per day
    with closing(sqlite3.connect(DB_PATH)) as conn:
        c = conn.cursor()
        today = datetime.now().strftime('%Y-%m-%d')
        c.execute('''CREATE TABLE IF NOT EXISTS free_signal_log (user_id INTEGER, date TEXT, count INTEGER, PRIMARY KEY(user_id, date))''')
        c.execute('SELECT count FROM free_signal_log WHERE user_id=? AND date=?', (user_id, today))
        row = c.fetchone()
        return row[0] if row else 0

def increment_free_signal_count(user_id):
    with closing(sqlite3.connect(DB_PATH)) as conn:
        c = conn.cursor()
        today = datetime.now().strftime('%Y-%m-%d')
        c.execute('''INSERT INTO free_signal_log (user_id, date, count) VALUES (?, ?, 1)
            ON CONFLICT(user_id, date) DO UPDATE SET count = count + 1''', (user_id, today))
        conn.commit()

def unlock_paid_signal_for_user(user_id, signal_id):
    # Track which paid signals have been unlocked by user
    with closing(sqlite3.connect(DB_PATH)) as conn:
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS paid_signal_unlocks (user_id INTEGER, signal_id INTEGER, PRIMARY KEY(user_id, signal_id))''')
        c.execute('INSERT OR IGNORE INTO paid_signal_unlocks (user_id, signal_id) VALUES (?, ?)', (user_id, signal_id))
        conn.commit()
import sqlite3
from contextlib import closing

import os
from datetime import datetime, timedelta
from dotenv import load_dotenv


def _env_bool(name: str, default: bool = False) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "y", "on"}


# Only load local `.env` when explicitly enabled (local dev).
# Railway should rely on injected environment variables.
if _env_bool("ALLOW_DOTENV", False):
    load_dotenv()
DB_PATH = 'signals.db'


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    raw = raw.strip()
    if not raw:
        return default
    try:
        return int(raw)
    except Exception:
        return default


OWNER_TELEGRAM_ID = _env_int('OWNER_TELEGRAM_ID', 123456789)
BYPASS_KEY = (os.getenv('BYPASS_KEY') or '').strip() or None

_owner_ids_raw = (os.getenv('OWNER_IDS') or str(OWNER_TELEGRAM_ID)).strip()
OWNER_IDS = [int(x) for x in _owner_ids_raw.split(',') if x.strip().isdigit()]


def record_user_seen(user_id: int, username: str | None = None) -> bool:
    """Persist user_id for basic analytics/ops.

    This is intentionally minimal (Telegram ID only; no passwords).

    Returns True if this is the first time we've seen the user.
    """
    with closing(sqlite3.connect(DB_PATH)) as conn:
        c = conn.cursor()
        c.execute(
            '''CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_seen TEXT
            )'''
        )
        before = conn.total_changes
        c.execute(
            'INSERT OR IGNORE INTO users (user_id, username, first_seen) VALUES (?, ?, ?)',
            (int(user_id), (username or None), datetime.now().isoformat()),
        )
        # If user already existed, best-effort update username (non-breaking).
        if username:
            c.execute('UPDATE users SET username=? WHERE user_id=?', (str(username)[:64], int(user_id)))
        conn.commit()
        return (conn.total_changes - before) > 0


def get_alert_prefs(user_id: int) -> dict:
    """Return alert preferences for a user.

    Schema: tp_sl_enabled (bool), quiet_start_hour, quiet_end_hour
    """
    with closing(sqlite3.connect(DB_PATH)) as conn:
        c = conn.cursor()
        c.execute(
            '''CREATE TABLE IF NOT EXISTS alert_prefs (
                user_id INTEGER PRIMARY KEY,
                tp_sl_enabled INTEGER DEFAULT 1,
                quiet_start_hour INTEGER,
                quiet_end_hour INTEGER
            )'''
        )
        c.execute('SELECT tp_sl_enabled, quiet_start_hour, quiet_end_hour FROM alert_prefs WHERE user_id=?', (int(user_id),))
        row = c.fetchone()
        if not row:
            return {"tp_sl_enabled": True, "quiet_start_hour": None, "quiet_end_hour": None}
        return {
            "tp_sl_enabled": bool(row[0]),
            "quiet_start_hour": row[1],
            "quiet_end_hour": row[2],
        }


def set_alert_prefs(
    user_id: int,
    tp_sl_enabled: bool | None = None,
    quiet_start_hour: int | None = None,
    quiet_end_hour: int | None = None,
) -> dict:
    current = get_alert_prefs(user_id)
    if tp_sl_enabled is None:
        tp_sl_enabled = bool(current.get("tp_sl_enabled", True))
    if quiet_start_hour is None:
        quiet_start_hour = current.get("quiet_start_hour")
    if quiet_end_hour is None:
        quiet_end_hour = current.get("quiet_end_hour")

    with closing(sqlite3.connect(DB_PATH)) as conn:
        c = conn.cursor()
        c.execute(
            '''REPLACE INTO alert_prefs (user_id, tp_sl_enabled, quiet_start_hour, quiet_end_hour)
               VALUES (?, ?, ?, ?)''',
            (int(user_id), int(bool(tp_sl_enabled)), quiet_start_hour, quiet_end_hour),
        )
        conn.commit()
    return get_alert_prefs(user_id)

def init_db():
    with closing(sqlite3.connect(DB_PATH)) as conn:
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            asset TEXT,
            timeframe TEXT,
            direction TEXT,
            entry REAL,
            stop_loss REAL,
            take_profit REAL,
            rr_ratio REAL,
            strategy_name TEXT,
            strategy_group TEXT,
            strength REAL,
            score INTEGER,
            risk_profile TEXT,
            released INTEGER DEFAULT 0
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS subscriptions (
            user_id INTEGER PRIMARY KEY,
            tier TEXT,
            start_date TEXT,
            expiry_date TEXT,
            payment_ref TEXT,
            bypass_key_used INTEGER DEFAULT 0
        )''')

        # Delayed free signal delivery queue (auto-push summaries)
        c.execute(
            '''CREATE TABLE IF NOT EXISTS free_signal_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                date TEXT,
                asset TEXT,
                timeframe TEXT,
                direction TEXT,
                score INTEGER,
                queued_at TEXT,
                deliver_after TEXT,
                sent_at TEXT,
                status TEXT DEFAULT 'queued'
            )'''
        )
        c.execute('CREATE INDEX IF NOT EXISTS ix_free_signal_queue_user_date ON free_signal_queue (user_id, date)')
        c.execute('CREATE INDEX IF NOT EXISTS ix_free_signal_queue_deliver ON free_signal_queue (deliver_after, status)')

        # Referral tables
        c.execute('''CREATE TABLE IF NOT EXISTS referral_codes (
            code TEXT PRIMARY KEY,
            referrer_id INTEGER,
            created_at TEXT
        )''')
        # Each referred user can be attributed to a single referrer once.
        c.execute('''CREATE TABLE IF NOT EXISTS referrals (
            referred_id INTEGER PRIMARY KEY,
            referrer_id INTEGER,
            created_at TEXT
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS referral_rewards (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            referrer_id INTEGER,
            referred_id INTEGER,
            reward_type TEXT,
            reward_value INTEGER,
            created_at TEXT
        )''')
        conn.commit()


def queue_free_signal_summary(
    user_id: int,
    signal: dict,
    delay_minutes: int | None = None,
    daily_limit: int | None = None,
) -> bool:
    """Queue a delayed summary for a FREE user.

    Enforces a per-user daily cap (default 2). Returns True if queued.
    """
    if delay_minutes is None:
        try:
            delay_minutes = int(os.getenv("FREE_DELAY_MINUTES", "30"))
        except Exception:
            delay_minutes = 30
    if daily_limit is None:
        try:
            daily_limit = int(os.getenv("FREE_DAILY_LIMIT", "2"))
        except Exception:
            daily_limit = 2

    now = datetime.now()
    today = now.strftime('%Y-%m-%d')
    deliver_after = (now + timedelta(minutes=max(0, int(delay_minutes)))).isoformat()

    asset = str(signal.get('asset') or '')[:32]
    timeframe = str(signal.get('timeframe') or '')[:8]
    direction = str(signal.get('direction') or '')[:8]
    try:
        score = int(signal.get('score') or 0)
    except Exception:
        score = 0

    with closing(sqlite3.connect(DB_PATH)) as conn:
        c = conn.cursor()
        c.execute(
            '''CREATE TABLE IF NOT EXISTS free_signal_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                date TEXT,
                asset TEXT,
                timeframe TEXT,
                direction TEXT,
                score INTEGER,
                queued_at TEXT,
                deliver_after TEXT,
                sent_at TEXT,
                status TEXT DEFAULT 'queued'
            )'''
        )

        # Count already queued/sent today (exclude expired)
        c.execute(
            "SELECT COUNT(*) FROM free_signal_queue WHERE user_id=? AND date=? AND status IN ('queued','sent')",
            (int(user_id), today),
        )
        already = int((c.fetchone() or (0,))[0] or 0)
        if already >= int(daily_limit):
            return False

        c.execute(
            '''INSERT INTO free_signal_queue (user_id, date, asset, timeframe, direction, score, queued_at, deliver_after, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'queued')''',
            (int(user_id), today, asset, timeframe, direction, score, now.isoformat(), deliver_after),
        )
        conn.commit()
        return True


def get_due_free_signal_summaries(now_iso: str | None = None) -> dict[int, list[dict]]:
    """Return due queued free summaries grouped by user_id."""
    if now_iso is None:
        now_iso = datetime.now().isoformat()
    with closing(sqlite3.connect(DB_PATH)) as conn:
        c = conn.cursor()
        c.execute(
            '''CREATE TABLE IF NOT EXISTS free_signal_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                date TEXT,
                asset TEXT,
                timeframe TEXT,
                direction TEXT,
                score INTEGER,
                queued_at TEXT,
                deliver_after TEXT,
                sent_at TEXT,
                status TEXT DEFAULT 'queued'
            )'''
        )
        c.execute(
            "SELECT id, user_id, asset, timeframe, direction, score FROM free_signal_queue "
            "WHERE status='queued' AND deliver_after <= ? ORDER BY user_id, score DESC",
            (now_iso,),
        )
        rows = c.fetchall() or []

    grouped: dict[int, list[dict]] = {}
    for row in rows:
        _id, uid, asset, tf, direction, score = row
        grouped.setdefault(int(uid), []).append(
            {
                "id": int(_id),
                "asset": asset,
                "timeframe": tf,
                "direction": direction,
                "score": int(score or 0),
            }
        )
    return grouped


def mark_free_signal_summaries_sent(ids: list[int], status: str = 'sent') -> None:
    if not ids:
        return
    now = datetime.now().isoformat()
    with closing(sqlite3.connect(DB_PATH)) as conn:
        c = conn.cursor()
        placeholders = ",".join(["?"] * len(ids))
        c.execute(
            f"UPDATE free_signal_queue SET sent_at=?, status=? WHERE id IN ({placeholders})",
            (now, status, *[int(x) for x in ids]),
        )
        conn.commit()


def expire_old_free_signal_summaries(max_age_hours: int = 24) -> int:
    """Expire queued free summaries older than max_age_hours. Returns count affected."""
    cutoff = (datetime.now() - timedelta(hours=int(max_age_hours))).isoformat()
    with closing(sqlite3.connect(DB_PATH)) as conn:
        c = conn.cursor()
        c.execute(
            "UPDATE free_signal_queue SET status='expired' WHERE status='queued' AND queued_at < ?",
            (cutoff,),
        )
        conn.commit()
        return int(conn.total_changes or 0)
import random
def generate_referral_code(referrer_id):
    code = f"SRK{referrer_id}{random.randint(1000,9999)}"
    with closing(sqlite3.connect(DB_PATH)) as conn:
        c = conn.cursor()
        c.execute('INSERT OR IGNORE INTO referral_codes (code, referrer_id, created_at) VALUES (?, ?, ?)', (code, referrer_id, datetime.now().isoformat()))
        conn.commit()
    return code

def get_referral_by_code(code):
    with closing(sqlite3.connect(DB_PATH)) as conn:
        c = conn.cursor()
        c.execute('SELECT referrer_id FROM referral_codes WHERE code=?', (code,))
        row = c.fetchone()
        if row:
            return {'referrer_id': row[0]}
        return None

def record_referral_reward(referrer_id, referred_id, reward_type, reward_value):
    with closing(sqlite3.connect(DB_PATH)) as conn:
        c = conn.cursor()
        c.execute('INSERT INTO referral_rewards (referrer_id, referred_id, reward_type, reward_value, created_at) VALUES (?, ?, ?, ?, ?)',
                  (referrer_id, referred_id, reward_type, reward_value, datetime.now().isoformat()))
        conn.commit()

def get_referral_rewards(referrer_id):
    with closing(sqlite3.connect(DB_PATH)) as conn:
        c = conn.cursor()
        c.execute('SELECT * FROM referral_rewards WHERE referrer_id=?', (referrer_id,))
        return c.fetchall()


def record_referral_signup(referrer_id: int, referred_id: int) -> bool:
    """Record a unique referral attribution.

    Returns True if recorded; False if the referred user was already attributed.
    """
    with closing(sqlite3.connect(DB_PATH)) as conn:
        c = conn.cursor()
        c.execute(
            '''CREATE TABLE IF NOT EXISTS referrals (
                referred_id INTEGER PRIMARY KEY,
                referrer_id INTEGER,
                created_at TEXT
            )'''
        )
        before = conn.total_changes
        c.execute(
            'INSERT OR IGNORE INTO referrals (referred_id, referrer_id, created_at) VALUES (?, ?, ?)',
            (int(referred_id), int(referrer_id), datetime.now().isoformat()),
        )
        conn.commit()
        return (conn.total_changes - before) > 0


def count_referrals(referrer_id: int) -> int:
    with closing(sqlite3.connect(DB_PATH)) as conn:
        c = conn.cursor()
        c.execute(
            '''CREATE TABLE IF NOT EXISTS referrals (
                referred_id INTEGER PRIMARY KEY,
                referrer_id INTEGER,
                created_at TEXT
            )'''
        )
        c.execute('SELECT COUNT(*) FROM referrals WHERE referrer_id=?', (int(referrer_id),))
        row = c.fetchone() or (0,)
        return int(row[0] or 0)


def get_referral_progress(referrer_id: int) -> dict:
    total = count_referrals(referrer_id)
    toward_next = total % 3
    needed = 3 - toward_next if toward_next else 0
    return {
        "total": total,
        "toward_next": toward_next,
        "needed_for_next": needed,
        "reward_days_per_3": 7,
    }


def _sum_reward_days(referrer_id: int) -> int:
    with closing(sqlite3.connect(DB_PATH)) as conn:
        c = conn.cursor()
        c.execute(
            '''CREATE TABLE IF NOT EXISTS referral_rewards (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                referrer_id INTEGER,
                referred_id INTEGER,
                reward_type TEXT,
                reward_value INTEGER,
                created_at TEXT
            )'''
        )
        c.execute(
            "SELECT COALESCE(SUM(reward_value), 0) FROM referral_rewards WHERE referrer_id=? AND reward_type='premium_days'",
            (int(referrer_id),),
        )
        row = c.fetchone() or (0,)
        return int(row[0] or 0)


def process_referral_start(referred_id: int, referral_code: str, is_new_user: bool) -> dict:
    """Process /start ref_CODE attribution and grant rewards.

    Abuse prevention:
    - Referred must be a new user (first time /start).
    - Each referred can be attributed once.
    - Self-referrals rejected.

    Reward:
    - Every 3 successful referrals => +7 days to referrer's active tier (VIP stays VIP; otherwise Premium).
    """
    result = {
        "status": "ignored",
        "referrer_id": None,
        "referrals_total": 0,
        "days_granted": 0,
    }

    try:
        code_row = get_referral_by_code(referral_code)
    except Exception:
        code_row = None
    if not code_row:
        result["status"] = "invalid_code"
        return result

    referrer_id = int(code_row["referrer_id"])
    result["referrer_id"] = referrer_id

    if int(referred_id) == referrer_id:
        result["status"] = "self_referral"
        return result

    # Must be new user on first /start
    if not bool(is_new_user):
        result["status"] = "not_new"
        return result

    # If the referred already has any subscription record, treat as not eligible.
    try:
        if get_subscription(int(referred_id)) is not None:
            result["status"] = "not_new"
            return result
    except Exception:
        pass

    recorded = record_referral_signup(referrer_id, int(referred_id))
    if not recorded:
        result["status"] = "already_referred"
        return result

    # Audit: record the referral event
    try:
        record_referral_reward(referrer_id, int(referred_id), "referral_signup", 1)
    except Exception:
        pass

    total = count_referrals(referrer_id)
    result["referrals_total"] = total

    expected_days = (total // 3) * 7
    already_days = _sum_reward_days(referrer_id)
    grant_days = max(0, expected_days - already_days)

    if grant_days <= 0:
        result["status"] = "attributed"
        return result

    # Extend referrer subscription (stacking)
    try:
        current_tier = get_user_tier(referrer_id)
    except Exception:
        current_tier = "FREE"
    tier_to_extend = current_tier if str(current_tier).upper().startswith("VIP") else "PREMIUM"
    try:
        set_subscription(referrer_id, tier_to_extend, int(grant_days), payment_ref="REFERRAL", bypass_key_used=False)
    except Exception:
        # If extension fails, don't record reward days.
        result["status"] = "attributed"
        return result

    try:
        record_referral_reward(referrer_id, int(referred_id), "premium_days", int(grant_days))
    except Exception:
        pass

    result["status"] = "reward_granted"
    result["days_granted"] = int(grant_days)
    return result
def has_full_access(user_id, provided_key=None):
    if user_id in OWNER_IDS:
        return True
    if provided_key == BYPASS_KEY:
        return True
    sub = get_subscription(user_id)
    if sub and not sub.get('expired', True):
        return True
    return False

def get_user_tier(user_id):
    if user_id in OWNER_IDS:
        return "OWNER"
    try:
        from core.redis_state import state as _state

        if _state.has_temp_owner_sync(int(user_id)):
            return "OWNER"
    except Exception:
        pass
    sub = get_subscription(user_id)
    if sub is None or sub.get('expired', True):
        return "FREE"
    return sub.get('tier', 'FREE')

def get_subscription(user_id):
    with closing(sqlite3.connect(DB_PATH)) as conn:
        c = conn.cursor()
        c.execute('SELECT * FROM subscriptions WHERE user_id=?', (user_id,))
        row = c.fetchone()
        if not row:
            return None
        keys = [d[0] for d in c.description]
        sub = dict(zip(keys, row))
        sub['expired'] = datetime.now() > datetime.fromisoformat(sub['expiry_date'])
        return sub

def set_subscription(user_id, tier, duration_days, payment_ref, bypass_key_used=False):
    now = datetime.now()
    sub = get_subscription(user_id)
    # Stacking renewals: if same tier is active, extend from expiry.
    # Upgrades: Premium -> VIP extends from Premium expiry.
    base = str(tier or "").upper()
    prior = str(sub.get('tier', '')).upper() if sub else ""
    active = bool(sub and not sub.get('expired', True))

    same_base = False
    if base.startswith('VIP') and prior.startswith('VIP'):
        same_base = True
    if base.startswith('PREMIUM') and prior.startswith('PREMIUM'):
        same_base = True

    if active and same_base:
        start = datetime.fromisoformat(sub['expiry_date'])
        expiry = start + timedelta(days=duration_days)
    elif base.startswith('VIP') and active and prior.startswith('PREMIUM'):
        start = datetime.fromisoformat(sub['expiry_date'])
        expiry = start + timedelta(days=duration_days)
    else:
        start = now
        expiry = start + timedelta(days=duration_days)
    with closing(sqlite3.connect(DB_PATH)) as conn:
        c = conn.cursor()
        c.execute('''REPLACE INTO subscriptions (user_id, tier, start_date, expiry_date, payment_ref, bypass_key_used)
            VALUES (?, ?, ?, ?, ?, ?)''',
            (user_id, tier, start.isoformat(), expiry.isoformat(), payment_ref, int(bypass_key_used)))
        conn.commit()

# Helper: block repeat first-time VIP trial
def has_ever_had_vip(user_id):
    with closing(sqlite3.connect(DB_PATH)) as conn:
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM subscriptions WHERE user_id=? AND tier LIKE 'VIP%'", (user_id,))
        row = c.fetchone()
        return row[0] > 0

def downgrade_to_free(user_id):
    with closing(sqlite3.connect(DB_PATH)) as conn:
        c = conn.cursor()
        c.execute('''UPDATE subscriptions SET tier=?, expiry_date=? WHERE user_id=?''',
            ("FREE", datetime.now().isoformat(), user_id))
        conn.commit()

def auto_expire_subscriptions():
    now = datetime.now().isoformat()
    with closing(sqlite3.connect(DB_PATH)) as conn:
        c = conn.cursor()
        c.execute('''UPDATE subscriptions SET tier='FREE' WHERE expiry_date < ? AND tier != 'FREE' ''', (now,))
        conn.commit()

def store_signal(signal):
    with closing(sqlite3.connect(DB_PATH)) as conn:
        c = conn.cursor()
        c.execute('''INSERT INTO signals (asset, timeframe, direction, entry, stop_loss, take_profit, rr_ratio, strategy_name, strategy_group, strength, score, risk_profile, released)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
            (
                signal['asset'], signal['timeframe'], signal['direction'],
                signal['entry'], signal['stop_loss'], signal['take_profit'],
                signal['rr_ratio'], signal['strategy_name'], signal['strategy_group'],
                signal['strength'], signal.get('score', 0), str(signal.get('risk_profile', {})), 0
            ))
        conn.commit()

def get_unreleased_signals():
    with closing(sqlite3.connect(DB_PATH)) as conn:
        c = conn.cursor()
        c.execute('SELECT * FROM signals WHERE released=0')
        rows = c.fetchall()
        # Convert to dicts
        keys = [d[0] for d in c.description]
        return [dict(zip(keys, row)) for row in rows]

def mark_signals_released(ids):
    with closing(sqlite3.connect(DB_PATH)) as conn:
        c = conn.cursor()
        c.executemany('UPDATE signals SET released=1 WHERE id=?', [(i,) for i in ids])
        conn.commit()

init_db()

# --- STUBS FOR SIGNAL CONTROLLER ---
def get_strategy_stats():
    # Return dummy stats for testing
    return {}

def update_strategy_weight(strat, boost=False, degrade=False):
    # Dummy function for testing
    pass

def disable_strategy(strat):
    # Dummy function for testing
    pass
