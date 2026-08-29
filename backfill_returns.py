import sqlite3
from datetime import datetime
from collections import defaultdict

DB_PATH = "data/news.db"


def backfill():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT id, symbol, date, close FROM prices ORDER BY symbol, date").fetchall()
    conn.close()

    by_symbol = defaultdict(list)
    for r in rows:
        by_symbol[r["symbol"]].append(r)

    updates = []
    for symbol, items in by_symbol.items():
        items.sort(key=lambda x: x["date"])
        closes = [r["close"] for r in items if r["close"] is not None]
        dates = [r["date"] for r in items if r["close"] is not None]
        for idx, r in enumerate(items):
            d = r["date"]
            daily = weekly = monthly = None
            if r["close"] is not None:
                ci = closes.index(r["close"]) if r["close"] in closes else idx
                if ci > 0 and closes[ci - 1]:
                    daily = (closes[ci] - closes[ci - 1]) / closes[ci - 1]
                if ci >= 7 and closes[ci - 7]:
                    weekly = (closes[ci] - closes[ci - 7]) / closes[ci - 7]
                if ci >= 30 and closes[ci - 30]:
                    monthly = (closes[ci] - closes[ci - 30]) / closes[ci - 30]
            updates.append((daily, weekly, monthly, r["id"]))

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.executemany(
        "UPDATE prices SET daily_return=?, weekly_return=?, monthly_return=? WHERE id=?",
        updates,
    )
    conn.commit()
    conn.close()
    print(f"Backfilled {len(updates)} price rows.")


if __name__ == "__main__":
    backfill()
