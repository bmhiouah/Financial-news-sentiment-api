"""PostgreSQL persistence: schema + typed access to news, prices and equities.

This is the only module that talks SQL. Everything above it works with the
domain objects from `financial_sentiment.domain`.
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Iterable, Iterator, List, Optional, Sequence, Set, Tuple

import psycopg

from .config import SETTINGS
from .domain import Coverage, Equity, NewsItem, PriceBar

NEWS_TABLE = "news"
FINNHUB_TABLE = "finnhub_news"
PRICES_TABLE = "prices"
EQUITIES_TABLE = "equities"

_NEWS_COLUMNS = (
    "symbol", "date", "headline", "text", "source", "url",
    "sentiment_label", "confidence", "finbert_score",
    "llm_label", "llm_positive", "llm_negative", "llm_neutral", "llm_score",
)
_PRICES_COLUMNS = (
    "symbol", "date", "open", "high", "low", "close", "volume",
    "daily_return", "weekly_return", "monthly_return",
)
_EQUITY_COLUMNS = ("symbol", "name", "exchange", "sector", "industry", "market_cap")

# `news` and `finnhub_news` are deliberately identical: Finnhub rows land in a
# staging table and are promoted into `news` once scored.
_NEWS_SCHEMA = """
CREATE TABLE IF NOT EXISTS {table} (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    symbol TEXT,
    date TEXT,
    headline TEXT,
    text TEXT,
    source TEXT,
    url TEXT NOT NULL DEFAULT '',
    sentiment_label TEXT,
    confidence DOUBLE PRECISION,
    finbert_score DOUBLE PRECISION,
    llm_label TEXT,
    llm_positive DOUBLE PRECISION,
    llm_negative DOUBLE PRECISION,
    llm_neutral DOUBLE PRECISION,
    llm_score DOUBLE PRECISION
)
"""

_PRICES_SCHEMA = """
CREATE TABLE IF NOT EXISTS prices (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    symbol TEXT NOT NULL,
    date TEXT,
    open DOUBLE PRECISION,
    high DOUBLE PRECISION,
    low DOUBLE PRECISION,
    close DOUBLE PRECISION,
    volume DOUBLE PRECISION,
    daily_return DOUBLE PRECISION,
    weekly_return DOUBLE PRECISION,
    monthly_return DOUBLE PRECISION
)
"""

_EQUITIES_SCHEMA = """
CREATE TABLE IF NOT EXISTS equities (
    symbol TEXT PRIMARY KEY,
    name TEXT,
    exchange TEXT,
    sector TEXT,
    industry TEXT,
    market_cap DOUBLE PRECISION
)
"""


def _sql_columns(columns: Sequence[str], prefix: str = "") -> str:
    return ", ".join(f"{prefix}{c}" for c in columns)


class Repository:
    """Thin psycopg wrapper exposing typed methods over the domain objects."""

    def __init__(self, database_url: Optional[str] = None) -> None:
        self.database_url = database_url or SETTINGS.database_url

    @contextmanager
    def connection(self) -> Iterator[psycopg.Connection]:
        with psycopg.connect(self.database_url) as conn:
            yield conn

    # ---- schema ----

    def init(self) -> None:
        """Create tables and indexes. Idempotent, safe to call on every start."""
        with self.connection() as conn:
            cur = conn.cursor()
            for table in (NEWS_TABLE, FINNHUB_TABLE):
                cur.execute(_NEWS_SCHEMA.format(table=table))
                cur.execute(
                    f"CREATE UNIQUE INDEX IF NOT EXISTS idx_{table}_symbol_url "
                    f"ON {table}(symbol, url)"
                )
            cur.execute(_PRICES_SCHEMA)
            cur.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_prices_symbol_date "
                "ON prices(symbol, date)"
            )
            cur.execute(_EQUITIES_SCHEMA)
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_equities_exchange "
                "ON equities(exchange)"
            )

    # ---- news ----

    def save_news(self, items: Iterable[NewsItem],
                  table: str = NEWS_TABLE) -> int:
        """Insert articles, skipping ones already stored for their symbol."""
        rows = [
            (
                i.symbol, i.date, i.headline, i.text, i.source, i.url,
                i.sentiment_label, i.confidence, i.finbert_score,
                i.llm_label, i.llm_positive, i.llm_negative, i.llm_neutral,
                i.llm_score,
            )
            for i in items
        ]
        if not rows:
            return 0
        sql = (
            f"INSERT INTO {table} ({_sql_columns(_NEWS_COLUMNS)}) "
            f"VALUES ({', '.join(['%s'] * len(_NEWS_COLUMNS))}) "
            f"ON CONFLICT (symbol, url) DO NOTHING"
        )
        with self.connection() as conn:
            cur = conn.cursor()
            cur.executemany(sql, rows)
            return cur.rowcount

    def existing_urls(self, symbol: str, table: str, urls: Sequence[str]) -> Set[str]:
        """Subset of `urls` already stored for `symbol`.

        Lets the pipeline skip re-scoring articles it already has, which keeps
        re-fetching the same window cheap.
        """
        urls = [u for u in urls if u]
        if not urls:
            return set()
        found: Set[str] = set()
        with self.connection() as conn:
            cur = conn.cursor()
            for start in range(0, len(urls), 400):
                chunk = urls[start:start + 400]
                placeholders = ", ".join(["%s"] * len(chunk))
                rows = cur.execute(
                    f"SELECT url FROM {table} "
                    f"WHERE symbol = %s AND url IN ({placeholders})",
                    (symbol, *chunk),
                ).fetchall()
                found.update(row[0] for row in rows)
        return found

    def fetch_news(self, with_sentiment_only: bool = True,
                   table: str = NEWS_TABLE) -> List[NewsItem]:
        sql = f"SELECT {_sql_columns(_NEWS_COLUMNS)} FROM {table}"
        if with_sentiment_only:
            sql += " WHERE finbert_score IS NOT NULL"
        with self.connection() as conn:
            return [NewsItem(*row) for row in conn.cursor().execute(sql).fetchall()]

    def fetch_unscored_news(self, table: str = NEWS_TABLE) -> List[NewsItem]:
        """Rows that have a headline but no FinBERT score yet."""
        sql = (
            f"SELECT {_sql_columns(_NEWS_COLUMNS)} FROM {table} "
            f"WHERE finbert_score IS NULL AND headline IS NOT NULL AND headline != ''"
        )
        with self.connection() as conn:
            return [NewsItem(*row) for row in conn.cursor().execute(sql).fetchall()]

    def fetch_pending_llm(self, table: str = NEWS_TABLE) -> List[NewsItem]:
        """Rows that have a headline but no LLM score yet."""
        sql = (
            f"SELECT {_sql_columns(_NEWS_COLUMNS)} FROM {table} "
            f"WHERE llm_score IS NULL AND headline IS NOT NULL AND headline != ''"
        )
        with self.connection() as conn:
            return [NewsItem(*row) for row in conn.cursor().execute(sql).fetchall()]

    def update_sentiment(self, items: List[NewsItem],
                         table: str = FINNHUB_TABLE) -> int:
        """Bulk-update FinBERT columns by URL."""
        return self._executemany(
            f"UPDATE {table} SET sentiment_label=%s, confidence=%s, finbert_score=%s "
            f"WHERE url=%s",
            [(i.sentiment_label, i.confidence, i.finbert_score, i.url) for i in items],
        )

    def update_llm_scores(self, items: List[NewsItem],
                          table: str = NEWS_TABLE) -> int:
        """Bulk-update the llm_* columns by URL."""
        return self._executemany(
            f"UPDATE {table} SET llm_label=%s, llm_positive=%s, llm_negative=%s, "
            f"llm_neutral=%s, llm_score=%s WHERE url=%s",
            [
                (i.llm_label, i.llm_positive, i.llm_negative, i.llm_neutral,
                 i.llm_score, i.url)
                for i in items
            ],
        )

    def promote_finnhub_to_news(self) -> int:
        """Copy Finnhub rows into `news` and backfill sentiment on duplicates."""
        columns = _sql_columns(_NEWS_COLUMNS)
        staged = _sql_columns(_NEWS_COLUMNS, prefix="f.")
        insert = (
            f"INSERT INTO {NEWS_TABLE} ({columns}) "
            f"SELECT {staged} FROM {FINNHUB_TABLE} f "
            f"ON CONFLICT (symbol, url) DO NOTHING"
        )
        # Rows promoted before they were scored keep NULL sentiment; fill those in
        # without overwriting anything the main table already has.
        backfill = f"""
            UPDATE {NEWS_TABLE} n
            SET sentiment_label = f.sentiment_label,
                confidence = f.confidence,
                finbert_score = f.finbert_score,
                llm_label = COALESCE(n.llm_label, f.llm_label),
                llm_positive = COALESCE(n.llm_positive, f.llm_positive),
                llm_negative = COALESCE(n.llm_negative, f.llm_negative),
                llm_neutral = COALESCE(n.llm_neutral, f.llm_neutral),
                llm_score = COALESCE(n.llm_score, f.llm_score)
            FROM {FINNHUB_TABLE} f
            WHERE f.symbol = n.symbol AND f.url = n.url AND f.finbert_score IS NOT NULL
        """
        with self.connection() as conn:
            cur = conn.cursor()
            cur.execute(insert)
            inserted = cur.rowcount
            cur.execute(backfill)
            return inserted + cur.rowcount

    # ---- prices ----

    def save_prices(self, bars: Iterable[PriceBar]) -> int:
        rows = [
            (
                b.symbol, b.date, b.open, b.high, b.low, b.close, b.volume,
                b.daily_return, b.weekly_return, b.monthly_return,
            )
            for b in bars
        ]
        if not rows:
            return 0
        sql = (
            f"INSERT INTO {PRICES_TABLE} ({_sql_columns(_PRICES_COLUMNS)}) "
            f"VALUES ({', '.join(['%s'] * len(_PRICES_COLUMNS))}) "
            f"ON CONFLICT (symbol, date) DO NOTHING"
        )
        with self.connection() as conn:
            cur = conn.cursor()
            cur.executemany(sql, rows)
            return cur.rowcount

    def fetch_prices(self, symbol: Optional[str] = None) -> List[PriceBar]:
        sql = f"SELECT {_sql_columns(_PRICES_COLUMNS)} FROM {PRICES_TABLE}"
        params: tuple = ()
        if symbol:
            sql += " WHERE symbol = %s"
            params = (symbol,)
        with self.connection() as conn:
            rows = conn.cursor().execute(sql + " ORDER BY symbol, date",
                                         params).fetchall()
        return [PriceBar(*row) for row in rows]

    # ---- coverage ----

    def coverage(self, symbol: str, table: str,
                 start: Optional[str] = None,
                 end: Optional[str] = None) -> Coverage:
        """Row count and date span stored for `symbol` in `table`.

        For news tables `start`/`end` narrow the count to that window; prices are
        always summarised over their full history so the caller can tell whether
        the stored range covers the requested one.
        """
        with self.connection() as conn:
            cur = conn.cursor()
            row = cur.execute(
                f"SELECT COUNT(*), MIN(date), MAX(date) FROM {table} "
                f"WHERE symbol = %s AND date IS NOT NULL",
                (symbol,),
            ).fetchone()
        coverage = Coverage(symbol=symbol, table=table, n_rows=row[0] or 0,
                            min_date=row[1], max_date=row[2])
        if start and end and table != PRICES_TABLE:
            with self.connection() as conn:
                coverage.n_rows = conn.cursor().execute(
                    f"SELECT COUNT(*) FROM {table} "
                    f"WHERE symbol = %s AND date BETWEEN %s AND %s",
                    (symbol, start, end),
                ).fetchone()[0]
        return coverage

    # ---- equities ----

    def save_equities(self, items: Iterable[Equity]) -> int:
        rows = [
            (i.symbol, i.name, i.exchange, i.sector, i.industry, i.market_cap)
            for i in items
        ]
        if not rows:
            return 0
        sql = (
            f"INSERT INTO {EQUITIES_TABLE} ({_sql_columns(_EQUITY_COLUMNS)}) "
            f"VALUES ({', '.join(['%s'] * len(_EQUITY_COLUMNS))}) "
            f"ON CONFLICT (symbol) DO NOTHING"
        )
        with self.connection() as conn:
            cur = conn.cursor()
            cur.executemany(sql, rows)
            return cur.rowcount

    def fetch_equities(self, query: Optional[str] = None, limit: Optional[int] = None,
                       offset: int = 0) -> Tuple[int, List[Equity]]:
        """Page through the universe; `query` matches symbol or name.

        Returns the total number of matches along with the requested page, so the
        caller can paginate without loading every row.
        """
        where, params = "", ()
        if query:
            where = "WHERE symbol ILIKE %s OR name ILIKE %s"
            params = (f"%{query}%", f"%{query}%")

        with self.connection() as conn:
            cur = conn.cursor()
            total = cur.execute(
                f"SELECT COUNT(*) FROM {EQUITIES_TABLE} {where}", params
            ).fetchone()[0]
            sql = (f"SELECT {_sql_columns(_EQUITY_COLUMNS)} FROM {EQUITIES_TABLE} "
                   f"{where} ORDER BY symbol")
            if limit is not None:
                sql += " LIMIT %s OFFSET %s"
                params += (limit, offset)
            rows = cur.execute(sql, params).fetchall()

        equities = [
            Equity(symbol, name or "", exchange or "", sector or "", industry or "", cap)
            for symbol, name, exchange, sector, industry, cap in rows
        ]
        return total, equities

    def equity_count(self) -> int:
        with self.connection() as conn:
            return conn.cursor().execute(
                f"SELECT COUNT(*) FROM {EQUITIES_TABLE}"
            ).fetchone()[0]

    def clear_equities(self) -> None:
        with self.connection() as conn:
            conn.cursor().execute(f"DELETE FROM {EQUITIES_TABLE}")

    # ---- internals ----

    def _executemany(self, sql: str, rows: List[tuple]) -> int:
        if not rows:
            return 0
        with self.connection() as conn:
            conn.cursor().executemany(sql, rows)
        return len(rows)
