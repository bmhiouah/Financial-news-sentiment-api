"""Domain models used across the pipeline."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Optional, Tuple

# Sentiment labels
POSITIVE = "positive"
NEGATIVE = "negative"
NEUTRAL = "neutral"

# News source kinds
SOURCE_OPENBB = "OpenBB"
SOURCE_FINNHUB = "Finnhub"


@dataclass
class NewsItem:
    """A single news headline with optional sentiment scores."""

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

    @property
    def has_sentiment(self) -> bool:
        return self.finbert_score is not None

    @property
    def has_llm_score(self) -> bool:
        return self.llm_score is not None

    @classmethod
    def from_dict(cls, d: dict) -> "NewsItem":
        return cls(
            symbol=d.get("symbol", ""),
            date=_coerce_date(d.get("date")),
            headline=d.get("headline", "") or "",
            text=d.get("text", "") or "",
            source=d.get("source", SOURCE_OPENBB),
            url=d.get("url", "") or "",
            sentiment_label=d.get("sentiment_label"),
            confidence=d.get("confidence"),
            finbert_score=d.get("finbert_score"),
            llm_label=d.get("llm_label"),
            llm_positive=d.get("llm_positive"),
            llm_negative=d.get("llm_negative"),
            llm_neutral=d.get("llm_neutral"),
            llm_score=d.get("llm_score"),
        )


@dataclass
class PriceBar:
    """One trading-day price bar with optional forward returns."""

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

    @classmethod
    def from_dict(cls, d: dict) -> "PriceBar":
        return cls(
            symbol=d.get("symbol", ""),
            date=_coerce_date(d.get("date")),
            open=d.get("open"),
            high=d.get("high"),
            low=d.get("low"),
            close=d.get("close"),
            volume=d.get("volume"),
            daily_return=d.get("daily_return"),
            weekly_return=d.get("weekly_return"),
            monthly_return=d.get("monthly_return"),
        )


@dataclass
class SentimentResult:
    """Output of a sentiment scorer."""

    score: float  # -1..+1
    label: str  # "positive" / "negative" / "neutral"
    confidence: float  # |score|

    def to_row(self) -> Tuple[Optional[str], Optional[float], Optional[float]]:
        return (self.label, self.confidence, self.score)


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

    @property
    def is_full(self) -> bool:
        return self.min_date is not None and self.max_date is not None


def _coerce_date(value) -> str:
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
    s = str(value)[:10]
    return s
