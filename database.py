import sqlite3
import os
from datetime import datetime


DB_PATH = "data/news.db"


def init_db():
    os.makedirs("data", exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS news (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT,
            date TEXT,
            headline TEXT,
            text TEXT,
            source TEXT,
            url TEXT,
            sentiment_label TEXT,
            confidence REAL,
            finbert_score REAL
        )
    """)
    cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_news_symbol_url ON news(symbol, url)")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS prices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT,
            date TEXT,
            open REAL,
            high REAL,
            low REAL,
            close REAL,
            volume REAL,
            daily_return REAL,
            weekly_return REAL,
            monthly_return REAL
        )
    """)
    cols = [r[1] for r in cur.execute("PRAGMA table_info(prices)").fetchall()]
    if "daily_return" not in cols:
        cur.execute("ALTER TABLE prices ADD COLUMN daily_return REAL")
    if "weekly_return" not in cols:
        cur.execute("ALTER TABLE prices ADD COLUMN weekly_return REAL")
    if "monthly_return" not in cols:
        cur.execute("ALTER TABLE prices ADD COLUMN monthly_return REAL")
    conn.commit()
    conn.close()
