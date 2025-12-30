from datetime import datetime, timedelta
import sqlite3
from payments.models import Subscription

DURATIONS = {
    "PREMIUM": 30,
    "VIP": 30
}

DB_PATH = "db/subscriptions.db"

# Ensure table exists
conn = sqlite3.connect(DB_PATH)
c = conn.cursor()
c.execute("""
CREATE TABLE IF NOT EXISTS subscriptions (
    user_id INTEGER PRIMARY KEY,
    tier TEXT NOT NULL,
    expires_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")
conn.commit()
conn.close()

def upsert_subscription(user_id, tier, expires_at):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
    INSERT INTO subscriptions (user_id, tier, expires_at, updated_at)
    VALUES (?, ?, ?, CURRENT_TIMESTAMP)
    ON CONFLICT(user_id) DO UPDATE SET tier=excluded.tier, expires_at=excluded.expires_at, updated_at=CURRENT_TIMESTAMP
    """, (user_id, tier, expires_at))
    conn.commit()
    conn.close()

def get_subscription(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT user_id, tier, expires_at FROM subscriptions WHERE user_id=?", (user_id,))
    row = c.fetchone()
    conn.close()
    if row:
        return Subscription(row[0], row[1], datetime.fromisoformat(row[2]))
    return None

def activate_subscription(user_id, tier):
    expires = datetime.utcnow() + timedelta(days=DURATIONS[tier])
    upsert_subscription(user_id, tier, expires.isoformat())
