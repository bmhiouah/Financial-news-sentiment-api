"""Backfill forward returns (daily/weekly/monthly) on the prices table.

Run as:
    python scripts/backfill_returns.py
"""
import sys
from pathlib import Path
from typing import List

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from financial_sentiment.repository import Repository


def _is_close_valid(x) -> bool:
    return x is not None and x > 0


def backfill() -> int:
    repo = Repository()
    rows = repo.all_price_rows()
    by_symbol: dict = {}
    for r in rows:
        by_symbol.setdefault(r["symbol"], []).append(r)

    updates: List[tuple] = []
    for symbol, items in by_symbol.items():
        items.sort(key=lambda x: x["date"])
        closes = [r["close"] for r in items if _is_close_valid(r["close"])]
        for r in items:
            close = r["close"]
            daily = weekly = monthly = None
            if _is_close_valid(close) and close in closes:
                ci = closes.index(close)
                if ci > 0 and _is_close_valid(closes[ci - 1]):
                    daily = (closes[ci] - closes[ci - 1]) / closes[ci - 1]
                if ci >= 7 and _is_close_valid(closes[ci - 7]):
                    weekly = (closes[ci] - closes[ci - 7]) / closes[ci - 7]
                if ci >= 30 and _is_close_valid(closes[ci - 30]):
                    monthly = (closes[ci] - closes[ci - 30]) / closes[ci - 30]
            updates.append((daily, weekly, monthly, r["id"]))

    with repo._conn() as conn:  # noqa: SLF001 - controlled internal use
        conn.executemany(
            "UPDATE prices SET daily_return=?, weekly_return=?, monthly_return=? "
            "WHERE id=?",
            updates,
        )
    return len(updates)


if __name__ == "__main__":
    n = backfill()
    print(f"Backfilled {n} price rows.")
