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

load_dotenv()
DB_PATH = 'signals.db'
OWNER_TELEGRAM_ID = int(os.getenv('OWNER_TELEGRAM_ID', '123456789'))
BYPASS_KEY = os.getenv('BYPASS_KEY', 'SRK-OWNER-ONLY-948372')
OWNER_IDS = [int(x) for x in os.getenv('OWNER_IDS', str(OWNER_TELEGRAM_ID)).split(',')]

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
        conn.commit()
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
    sub = get_subscription(user_id)
    if sub is None or sub.get('expired', True):
        return "FREE"
    if sub.get('bypass_key_used'):
        return "OWNER"
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
    start = datetime.now()
    expiry = start + timedelta(days=duration_days)
    with closing(sqlite3.connect(DB_PATH)) as conn:
        c = conn.cursor()
        c.execute('''REPLACE INTO subscriptions (user_id, tier, start_date, expiry_date, payment_ref, bypass_key_used)
            VALUES (?, ?, ?, ?, ?, ?)''',
            (user_id, tier, start.isoformat(), expiry.isoformat(), payment_ref, int(bypass_key_used)))
        conn.commit()

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
