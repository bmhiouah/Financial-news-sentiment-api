"""Market data loader for the backtester."""
from __future__ import annotations

from typing import Optional

import pandas as pd

from ..repository import Repository


class DataLoader:
    """Loads the aligned (price, sentiment) series for one symbol.

    Prices come from the `prices` table; daily sentiment is the mean FinBERT
    score across all news items for that (symbol, date). Days without news
    receive a sentiment score of 0.0 (the FinBERT neutral default).
    """

    def __init__(self, repository: Optional[Repository] = None) -> None:
        self.repository = repository or Repository()

    def load(self, symbol: str) -> pd.DataFrame:
        """One row per trading day, sorted by date, with columns:

            date, open, high, low, close, volume, sentiment_score

        Days without a close price are dropped.
        """
        prices = self.repository.fetch_prices(symbol=symbol)
        if not prices:
            raise ValueError(f"No price data for symbol {symbol!r}")

        news = self.repository.fetch_news(with_sentiment_only=False)
        scores_by_date: dict = {}
        for item in news:
            if item.symbol == symbol and item.finbert_score is not None:
                scores_by_date.setdefault(item.date, []).append(item.finbert_score)

        rows = []
        for bar in sorted(prices, key=lambda p: p.date):
            if bar.close is None:
                continue
            scores = scores_by_date.get(bar.date, [])
            rows.append({
                "date": bar.date,
                "open": bar.open,
                "high": bar.high,
                "low": bar.low,
                "close": bar.close,
                "volume": bar.volume,
                "sentiment_score": sum(scores) / len(scores) if scores else 0.0,
            })

        df = pd.DataFrame(rows)
        df["date"] = pd.to_datetime(df["date"], format="mixed", utc=True,
                                    errors="coerce").dt.tz_localize(None)
        return df.dropna(subset=["date"]).reset_index(drop=True)
