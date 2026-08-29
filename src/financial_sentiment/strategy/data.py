"""Market data types and loaders for the backtester."""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

import pandas as pd

from ..domain import NewsItem
from ..repository import Repository


@dataclass(frozen=True)
class MarketDataPoint:
    """A single daily observation used by the backtester."""

    date: str
    price: float
    sentiment_score: float  # NaN-safe float; 0.0 means "no news today"

    @classmethod
    def from_inputs(cls, date: str, price: float, sentiment: Optional[float]) -> "MarketDataPoint":
        return cls(date=date, price=price, sentiment_score=sentiment if sentiment is not None else 0.0)


class DataLoader:
    """Loads aligned (price, sentiment) series for one symbol from the database.

    Prices come from the `prices` table; daily sentiment is the mean FinBERT
    score across all news items for that (symbol, date). Days without news
    receive a sentiment score of 0.0 (the FinBERT neutral default).
    """

    def __init__(self, repository: Optional[Repository] = None) -> None:
        self.repository = repository or Repository()

    def load(self, equity: str) -> pd.DataFrame:
        """Return a price DataFrame with columns:

            date, open, high, low, close, volume, sentiment_score

        One row per trading day, sorted by date. Days without news have
        sentiment_score == 0.0. Days without a close price are dropped.
        """
        prices = [p for p in self.repository.fetch_prices() if p.symbol == equity]
        news = [n for n in self.repository.fetch_news(with_sentiment_only=False)
                if n.symbol == equity]
        if not prices:
            raise ValueError(f"No price data for symbol {equity!r}")

        daily_sentiment: dict = {}
        for item in news:
            score = item.finbert_score
            if score is None:
                continue
            daily_sentiment.setdefault(item.date, []).append(score)

        rows = []
        for bar in sorted(prices, key=lambda p: p.date):
            if bar.close is None:
                continue
            scores = daily_sentiment.get(bar.date, [])
            sentiment = float(sum(scores) / len(scores)) if scores else 0.0
            rows.append({
                "date": bar.date,
                "open": bar.open,
                "high": bar.high,
                "low": bar.low,
                "close": bar.close,
                "volume": bar.volume,
                "sentiment_score": sentiment,
            })
        df = pd.DataFrame(rows)
        df["date"] = pd.to_datetime(df["date"], format="mixed", utc=True, errors="coerce").dt.tz_localize(None)
        df = df.dropna(subset=["date"]).reset_index(drop=True)
        return df

    def to_points(self, df: pd.DataFrame) -> List[MarketDataPoint]:
        """Convert a loaded DataFrame into the lightweight point list."""
        return [
            MarketDataPoint(
                date=row["date"].strftime("%Y-%m-%d") if hasattr(row["date"], "strftime") else str(row["date"]),
                price=float(row["close"]),
                sentiment_score=float(row["sentiment_score"]),
            )
            for _, row in df.iterrows()
        ]
