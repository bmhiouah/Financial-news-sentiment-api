"""Sentiment / return correlation analysis."""
from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple

from .repository import Repository

RETURN_FIELDS = ("daily_return", "weekly_return", "monthly_return")


def _is_number(value) -> bool:
    return value is not None and not (isinstance(value, float) and math.isnan(value))


def pearson(x: List[float], y: List[float]) -> Optional[float]:
    """Pearson correlation, None on degenerate input."""
    n = len(x)
    if n < 2 or len(y) != n:
        return None
    mean_x, mean_y = sum(x) / n, sum(y) / n
    numerator = sum((a - mean_x) * (b - mean_y) for a, b in zip(x, y))
    den_x = math.sqrt(sum((a - mean_x) ** 2 for a in x))
    den_y = math.sqrt(sum((b - mean_y) ** 2 for b in y))
    if den_x == 0 or den_y == 0:
        return None
    return numerator / (den_x * den_y)


def daily_mean_sentiment(news: Iterable) -> Dict[Tuple[str, str], float]:
    """Average FinBERT score per (symbol, date), ignoring unscored items."""
    grouped: Dict[Tuple[str, str], List[float]] = defaultdict(list)
    for item in news:
        if item.finbert_score is not None and item.finbert_score != 0:
            grouped[(item.symbol, item.date)].append(item.finbert_score)
    return {key: sum(v) / len(v) for key, v in grouped.items()}


@dataclass
class CorrelationRow:
    symbol: str
    daily: Optional[float]
    weekly: Optional[float]
    monthly: Optional[float]
    n: int


class CorrelationAnalyzer:
    """Correlates daily mean sentiment with price returns, per symbol."""

    def __init__(self, repository: Repository) -> None:
        self.repository = repository

    def run(self, symbol: Optional[str] = None) -> List[CorrelationRow]:
        news = self.repository.fetch_news(with_sentiment_only=True)
        prices = self.repository.fetch_prices(symbol=symbol)
        if not news or not prices:
            return []

        sentiment = daily_mean_sentiment(news)
        prices_by_symbol: Dict[str, List] = defaultdict(list)
        for bar in prices:
            prices_by_symbol[bar.symbol].append(bar)

        rows: List[CorrelationRow] = []
        for sym, bars in sorted(prices_by_symbol.items()):
            bars.sort(key=lambda b: b.date)
            xs: Dict[str, List[float]] = {f: [] for f in RETURN_FIELDS}
            ys: Dict[str, List[float]] = {f: [] for f in RETURN_FIELDS}
            n = 0
            for bar in bars:
                score = sentiment.get((sym, bar.date))
                if score is None:
                    continue
                for field in RETURN_FIELDS:
                    value = getattr(bar, field)
                    if _is_number(value):
                        xs[field].append(score)
                        ys[field].append(value)
                n += 1
            rows.append(CorrelationRow(
                symbol=sym,
                daily=pearson(xs["daily_return"], ys["daily_return"]),
                weekly=pearson(xs["weekly_return"], ys["weekly_return"]),
                monthly=pearson(xs["monthly_return"], ys["monthly_return"]),
                n=n,
            ))
        return rows

    def print_table(self, rows: Optional[List[CorrelationRow]] = None) -> None:
        rows = rows if rows is not None else self.run()
        print("Correlation by symbol (ignoring finbert_score == 0):")
        print(f"{'Symbol':<8} {'Daily':>10} {'Weekly':>10} {'Monthly':>10} {'N':>5}")
        print("-" * 45)
        for row in rows:
            cells = " ".join(
                f"{value:>10.3f}" if value is not None else f"{'N/A':>10}"
                for value in (row.daily, row.weekly, row.monthly)
            )
            print(f"{row.symbol:<8} {cells} {row.n:>5}")


def main() -> None:
    """Console entry: `python -m financial_sentiment.analysis`."""
    CorrelationAnalyzer(Repository()).print_table()


if __name__ == "__main__":
    main()
