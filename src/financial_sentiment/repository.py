"""SQLite-backed repository for news and prices.

The repository owns connection management and exposes typed methods on
domain objects. All raw SQL lives here.
"""
from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterable, Iterator, List, Optional

from .config import SETTINGS
from .domain import NewsItem, PriceBar, Coverage


# --------------------------------------------------------------------------- #
# Schema
# --------------------------------------------------------------------------- #

_NEWS_SCHEMA = """
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
"""

_FINNHUB_SCHEMA = """
CREATE TABLE IF NOT EXISTS finnhub_news (
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
"""

_PRICES_SCHEMA = """
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
"""

_NEWS_COLUMNS = (
    "symbol", "date", "headline", "text", "source", "url",
    "sentiment_label", "confidence", "finbert_score",
    "llm_label", "llm_positive", "llm_negative", "llm_neutral", "llm_score",
)
_PRICES_COLUMNS = (
    "symbol", "date", "open", "high", "low", "close", "volume",
    "daily_return", "weekly_return", "monthly_return",
)
_LLM_COLUMNS = ("llm_label", "llm_positive", "llm_negative", "llm_neutral", "llm_score")


# --------------------------------------------------------------------------- #
# Repository
# --------------------------------------------------------------------------- #

class Repository:
    """Thin wrapper around sqlite3 with typed methods on domain objects."""

    def __init__(self, db_path: Optional[str] = None) -> None:
        self.db_path = db_path or str(SETTINGS.db_path)
        os.makedirs(Path(self.db_path).parent, exist_ok=True)

    # ---- connection management ----

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path)
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    # ---- schema ----

    def init(self) -> None:
        with self._conn() as conn:
            cur = conn.cursor()
            cur.execute(_NEWS_SCHEMA)
            cur.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_news_symbol_url "
                "ON news(symbol, url)"
            )
            cur.execute(_FINNHUB_SCHEMA)
            cur.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_finnhub_news_symbol_url "
                "ON finnhub_news(symbol, url)"
            )
            cur.execute(_PRICES_SCHEMA)
            cur.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_prices_symbol_date "
                "ON prices(symbol, date)"
            )
            # Backfill returns columns on legacy DBs
            cols = {r[1] for r in cur.execute("PRAGMA table_info(prices)").fetchall()}
            for col in ("daily_return", "weekly_return", "monthly_return"):
                if col not in cols:
                    cur.execute(f"ALTER TABLE prices ADD COLUMN {col} REAL")
            # Backfill LLM sentiment columns on news / finnhub_news
            for table in ("news", "finnhub_news"):
                existing = {
                    r[1] for r in cur.execute(f"PRAGMA table_info({table})").fetchall()
                }
                for col, decl in (
                    ("llm_label",     "TEXT"),
                    ("llm_positive",  "REAL"),
                    ("llm_negative",  "REAL"),
                    ("llm_neutral",   "REAL"),
                    ("llm_score",     "REAL"),
                ):
                    if col not in existing:
                        cur.execute(f"ALTER TABLE {table} ADD COLUMN {col} {decl}")

    # ---- news ----

    def save_news(self, items: Iterable[NewsItem], table: str = "news") -> int:
        sql = (
            f"INSERT OR IGNORE INTO {table} "
            f"({', '.join(_NEWS_COLUMNS)}) VALUES ({', '.join(['?'] * len(_NEWS_COLUMNS))})"
        )
        rows = [
            (
                i.symbol, i.date, i.headline, i.text, i.source, i.url,
                i.sentiment_label, i.confidence, i.finbert_score,
                i.llm_label, i.llm_positive, i.llm_negative, i.llm_neutral, i.llm_score,
            )
            for i in items
        ]
        with self._conn() as conn:
            cur = conn.cursor()
            cur.executemany(sql, rows)
            return cur.rowcount

    def update_sentiment(self, url: str, label: Optional[str],
                         score: Optional[float],
                         confidence: Optional[float] = None,
                         table: str = "news") -> None:
        with self._conn() as conn:
            conn.execute(
                f"UPDATE {table} SET sentiment_label=?, confidence=?, finbert_score=? "
                f"WHERE url=?",
                (label, confidence, score, url),
            )

    def update_llm_score(self, url: str, label: Optional[str],
                         positive: Optional[float], negative: Optional[float],
                         neutral: Optional[float], score: Optional[float],
                         table: str = "news") -> None:
        with self._conn() as conn:
            conn.execute(
                f"UPDATE {table} SET llm_label=?, llm_positive=?, llm_negative=?, "
                f"llm_neutral=?, llm_score=? WHERE url=?",
                (label, positive, negative, neutral, score, url),
            )

    def update_llm_scores_bulk(self, items: List[NewsItem], table: str = "news") -> int:
        """Bulk-update llm_* columns by URL."""
        if not items:
            return 0
        rows = [
            (i.llm_label, i.llm_positive, i.llm_negative, i.llm_neutral, i.llm_score, i.url)
            for i in items
        ]
        with self._conn() as conn:
            conn.executemany(
                f"UPDATE {table} SET llm_label=?, llm_positive=?, llm_negative=?, "
                f"llm_neutral=?, llm_score=? WHERE url=?",
                rows,
            )
        return len(rows)

    def fetch_news(self, with_sentiment_only: bool = True) -> List[NewsItem]:
        sql = f"SELECT {_csv(_NEWS_COLUMNS)} FROM news"
        if with_sentiment_only:
            sql += " WHERE finbert_score IS NOT NULL"
        with self._conn() as conn:
            rows = conn.execute(sql).fetchall()
        return [_row_to_news(r) for r in rows]

    def fetch_pending_llm(self, table: str = "news") -> List[NewsItem]:
        """Rows that have a FinBERT score but no LLM score yet."""
        with self._conn() as conn:
            rows = conn.execute(
                f"SELECT {_csv(_NEWS_COLUMNS)} FROM {table} "
                f"WHERE (llm_score IS NULL) "
                f"AND headline IS NOT NULL AND headline != ''"
            ).fetchall()
        return [_row_to_news(r) for r in rows]

    def promote_finnhub_to_news(self, symbol: Optional[str] = None) -> int:
        """Copy Finnhub rows into `news`, also backfilling sentiment on duplicates."""
        if symbol:
            scope = " AND f.symbol = ?"
            scope_news = " AND symbol = ?"
            params = (symbol, symbol)
        else:
            scope = ""
            scope_news = ""
            params = ()

        with self._conn() as conn:
            cur = conn.cursor()
            cur.execute(
                f"""
                INSERT OR IGNORE INTO news ({_csv(_NEWS_COLUMNS)})
                SELECT {_csv('f.' + c for c in _NEWS_COLUMNS)}
                FROM finnhub_news f
                WHERE 1=1{scope}
                """,
                params[:1] if symbol else (),
            )
            inserted = cur.rowcount

            sql = f"""
                UPDATE news
                SET sentiment_label = (SELECT sentiment_label FROM finnhub_news f
                                        WHERE f.symbol = news.symbol AND f.url = news.url),
                    confidence = (SELECT confidence FROM finnhub_news f
                                    WHERE f.symbol = news.symbol AND f.url = news.url),
                    finbert_score = (SELECT finbert_score FROM finnhub_news f
                                      WHERE f.symbol = news.symbol AND f.url = news.url),
                    llm_label = COALESCE(news.llm_label,
                                          (SELECT llm_label FROM finnhub_news f
                                            WHERE f.symbol = news.symbol AND f.url = news.url)),
                    llm_positive = COALESCE(news.llm_positive,
                                             (SELECT llm_positive FROM finnhub_news f
                                               WHERE f.symbol = news.symbol AND f.url = news.url)),
                    llm_negative = COALESCE(news.llm_negative,
                                             (SELECT llm_negative FROM finnhub_news f
                                               WHERE f.symbol = news.symbol AND f.url = news.url)),
                    llm_neutral = COALESCE(news.llm_neutral,
                                            (SELECT llm_neutral FROM finnhub_news f
                                              WHERE f.symbol = news.symbol AND f.url = news.url)),
                    llm_score = COALESCE(news.llm_score,
                                          (SELECT llm_score FROM finnhub_news f
                                            WHERE f.symbol = news.symbol AND f.url = news.url))
                WHERE EXISTS (SELECT 1 FROM finnhub_news f
                              WHERE f.symbol = news.symbol AND f.url = news.url
                                AND f.finbert_score IS NOT NULL)
                  {scope_news}
            """
            cur.execute(sql, params)
            updated = cur.rowcount
        return inserted + updated

    def score_pending_finnhub(self, items: List[NewsItem]) -> int:
        """Bulk-update FinBERT sentiment on Finnhub rows by URL."""
        if not items:
            return 0
        rows = [
            (i.sentiment_label, i.confidence, i.finbert_score, i.url)
            for i in items
        ]
        with self._conn() as conn:
            conn.executemany(
                "UPDATE finnhub_news SET sentiment_label=?, confidence=?, finbert_score=? "
                "WHERE url=?",
                rows,
            )
        return len(rows)

    def fetch_pending_finnhub(self) -> List[NewsItem]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT " + _csv(_NEWS_COLUMNS) + " FROM finnhub_news "
                "WHERE finbert_score IS NULL AND headline IS NOT NULL AND headline != ''"
            ).fetchall()
        return [_row_to_news(r) for r in rows]

    # ---- prices ----

    def save_prices(self, bars: Iterable[PriceBar]) -> int:
        sql = (
            f"INSERT OR IGNORE INTO prices "
            f"({', '.join(_PRICES_COLUMNS)}) "
            f"VALUES ({', '.join(['?'] * len(_PRICES_COLUMNS))})"
        )
        rows = [
            (
                b.symbol, b.date, b.open, b.high, b.low, b.close, b.volume,
                b.daily_return, b.weekly_return, b.monthly_return,
            )
            for b in bars
        ]
        with self._conn() as conn:
            cur = conn.cursor()
            cur.executemany(sql, rows)
            return cur.rowcount

    def fetch_prices(self) -> List[PriceBar]:
        with self._conn() as conn:
            rows = conn.execute(
                f"SELECT {_csv(_PRICES_COLUMNS)} FROM prices ORDER BY symbol, date"
            ).fetchall()
        return [_row_to_price(r) for r in rows]

    def update_returns(self, bar_id: int, daily=None, weekly=None, monthly=None) -> None:
        with self._conn() as conn:
            conn.execute(
                "UPDATE prices SET daily_return=?, weekly_return=?, monthly_return=? "
                "WHERE id=?",
                (daily, weekly, monthly, bar_id),
            )

    def all_price_rows(self) -> List[dict]:
        with self._conn() as conn:
            conn.row_factory = sqlite3.Row
            return [dict(r) for r in conn.execute(
                "SELECT id, symbol, date, close FROM prices ORDER BY symbol, date"
            ).fetchall()]

    # ---- coverage ----

    def coverage(self, symbol: str, table: str,
                 start: Optional[str] = None, end: Optional[str] = None) -> Coverage:
        with self._conn() as conn:
            row = conn.execute(
                f"SELECT MIN(date), MAX(date), COUNT(*) FROM {table} "
                f"WHERE symbol = ? AND date IS NOT NULL",
                (symbol,),
            ).fetchone()
        cov = Coverage(symbol=symbol, table=table, n_rows=row[2] or 0,
                       min_date=row[0], max_date=row[1])
        if start and end and table != "prices":
            with self._conn() as conn:
                n = conn.execute(
                    f"SELECT COUNT(*) FROM {table} "
                    f"WHERE symbol = ? AND date IS NOT NULL AND date >= ? AND date <= ?",
                    (symbol, start, end),
                ).fetchone()[0]
            cov.n_rows = n
        return cov


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _csv(cols) -> str:
    return ", ".join(cols)


def _row_to_news(row) -> NewsItem:
    return NewsItem(
        symbol=row[0], date=row[1], headline=row[2], text=row[3],
        source=row[4], url=row[5], sentiment_label=row[6],
        confidence=row[7], finbert_score=row[8],
        llm_label=row[9], llm_positive=row[10], llm_negative=row[11],
        llm_neutral=row[12], llm_score=row[13],
    )


def _row_to_price(row) -> PriceBar:
    return PriceBar(
        symbol=row[0], date=row[1], open=row[2], high=row[3],
        low=row[4], close=row[5], volume=row[6],
        daily_return=row[7], weekly_return=row[8], monthly_return=row[9],
    )
