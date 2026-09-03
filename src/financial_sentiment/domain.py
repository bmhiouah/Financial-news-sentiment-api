"""Domain models shared by the pipeline, the repository and the API."""
from __future__ import annotations

from bisect import bisect_left
from dataclasses import dataclass
from datetime import date, timedelta
from typing import List, Optional

POSITIVE = "positive"
NEGATIVE = "negative"
NEUTRAL = "neutral"

SOURCE_OPENBB = "OpenBB"
SOURCE_FINNHUB = "Finnhub"


@dataclass
class NewsItem:
    """A single news article with its sentiment scores."""

    symbol: str
    date: str  # ISO "YYYY-MM-DD"
    headline: str
    text: str = ""
    source: str = SOURCE_OPENBB
    url: str = ""
    sentiment_label: Optional[str] = None
    confidence: Optional[float] = None
    finbert_score: Optional[float] = None  # -1..+1 (positive - negative)
    llm_label: Optional[str] = None
    llm_positive: Optional[float] = None
    llm_negative: Optional[float] = None
    llm_neutral: Optional[float] = None
    llm_score: Optional[float] = None  # -1..+1 (positive - negative)


@dataclass
class PriceBar:
    """One trading-day price bar with forward returns."""

    symbol: str
    date: str
    open: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    close: Optional[float] = None
    volume: Optional[float] = None
    daily_return: Optional[float] = None
    weekly_return: Optional[float] = None
    monthly_return: Optional[float] = None


@dataclass
class SentimentResult:
    """Output of a sentiment scorer."""

    score: float  # -1..+1
    label: str  # "positive" / "negative" / "neutral"
    confidence: float  # |score|


@dataclass
class Coverage:
    """Existing data coverage for a (symbol, table) pair."""

    symbol: str
    table: str
    n_rows: int
    min_date: Optional[str] = None
    max_date: Optional[str] = None

    @property
    def is_empty(self) -> bool:
        return self.n_rows == 0


@dataclass
class Equity:
    """A tradable security, used as the reference universe."""

    symbol: str
    name: str = ""
    exchange: str = ""
    sector: str = ""
    industry: str = ""
    market_cap: Optional[float] = None


def news_key(item: NewsItem) -> str:
    """Stable identity for an article, used for de-duplication.

    The URL is the natural key, but not every provider returns one, so fall back
    to date + headline rather than dropping those articles.
    """
    if item.url:
        return item.url
    return f"{item.date}|{item.headline.strip().lower()}"


def coerce_date(value) -> str:
    """Accept date, datetime, pandas.Timestamp, or ISO string -> 'YYYY-MM-DD'."""
    if value is None:
        return ""
    if hasattr(value, "date") and callable(value.date):
        try:
            value = value.date()
        except Exception:
            pass
    if isinstance(value, date):
        return value.strftime("%Y-%m-%d")
    return str(value)[:10]


#: Forward-return horizons, in calendar days.
RETURN_HORIZONS = {"daily_return": 1, "weekly_return": 7, "monthly_return": 30}


def add_forward_returns(bars: List[PriceBar]) -> List[PriceBar]:
    """Fill the return columns with **forward** (future) returns.

    A return answers "what happened *after* this date?":

        return[t] = (close[t + h] - close[t]) / close[t]

    with ``h`` = 1, 7 and 30 calendar days for the daily, weekly and monthly
    columns. ``t + h`` resolves to the first bar on or after that calendar date,
    so weekends, holidays and gaps in coverage land on the next trading day.

    Bars with no bar far enough in the future (the tail of the series) are left
    as NULL: their future return is genuinely unknown, and inventing one would
    be look-ahead bias. This is the whole point of the columns - they exist so
    sentiment on date ``t`` can be compared against what the market did *next*.

    `bars` is sorted by date first, so it may be passed in any order. Returns
    are always cleared before being recomputed, so stale values never survive.
    """
    for bar in bars:
        bar.daily_return = bar.weekly_return = bar.monthly_return = None

    usable = sorted(
        (b for b in bars if b.date and b.close), key=lambda b: b.date
    )
    dates = [b.date[:10] for b in usable]
    closes = [b.close for b in usable]

    for index, bar in enumerate(usable):
        for field, days in RETURN_HORIZONS.items():
            target = (date.fromisoformat(dates[index]) + timedelta(days=days)).isoformat()
            future = bisect_left(dates, target)
            if future < len(usable):
                setattr(bar, field, (closes[future] - bar.close) / bar.close)
    return bars
