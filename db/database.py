import sqlite3
from contextlib import closing

DB_PATH = 'signals.db'

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
