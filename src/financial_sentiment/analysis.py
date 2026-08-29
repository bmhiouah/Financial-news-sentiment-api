"""Sentiment / return correlation analysis."""
from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple

from .domain import NewsItem, PriceBar
from .repository import Repository


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _is_valid_number(x) -> bool:
    return x is not None and not (isinstance(x, float) and math.isnan(x))


def pearson(x: List[float], y: List[float]) -> Optional[float]:
    """Pearson correlation, returns None on degenerate input."""
    n = len(x)
    if n < 2 or len(y) != n:
        return None
    mean_x = sum(x) / n
    mean_y = sum(y) / n
    num = sum((xi - mean_x) * (yi - mean_y) for xi, yi in zip(x, y))
    den_x = math.sqrt(sum((xi - mean_x) ** 2 for xi in x))
    den_y = math.sqrt(sum((yi - mean_y) ** 2 for yi in y))
    if den_x == 0 or den_y == 0:
        return None
    return num / (den_x * den_y)


def daily_mean_sentiment(news: Iterable[NewsItem]) -> Dict[Tuple[str, str], float]:
    """Average FinBERT score per (symbol, date), ignoring items with score 0."""
    grouped: Dict[Tuple[str, str], List[float]] = defaultdict(list)
    for item in news:
        if item.finbert_score is not None and item.finbert_score != 0:
            grouped[(item.symbol, item.date)].append(item.finbert_score)
    return {k: sum(v) / len(v) for k, v in grouped.items()}


# --------------------------------------------------------------------------- #
# Analyzer
# --------------------------------------------------------------------------- #

@dataclass
class CorrelationRow:
    symbol: str
    daily: Optional[float]
    weekly: Optional[float]
    monthly: Optional[float]
    n: int


class CorrelationAnalyzer:
    """Correlates daily sentiment with price returns per symbol."""

    RETURN_FIELDS = ("daily_return", "weekly_return", "monthly_return")

    def __init__(self, repository: Repository) -> None:
        self.repository = repository

    def run(self) -> List[CorrelationRow]:
        news = self.repository.fetch_news(with_sentiment_only=True)
        prices = self.repository.fetch_prices()
        if not news or not prices:
            return []

        sentiment = daily_mean_sentiment(news)
        prices_by_symbol: Dict[str, List[PriceBar]] = defaultdict(list)
        for p in prices:
            prices_by_symbol[p.symbol].append(p)

        results: List[CorrelationRow] = []
        for symbol, bars in prices_by_symbol.items():
            bars.sort(key=lambda b: b.date)
            xs: Dict[str, List[float]] = {f: [] for f in self.RETURN_FIELDS}
            ys: Dict[str, List[float]] = {f: [] for f in self.RETURN_FIELDS}
            n = 0
            for bar in bars:
                score = sentiment.get((symbol, bar.date))
                if score is None:
                    continue
                for field in self.RETURN_FIELDS:
                    v = getattr(bar, field)
                    if _is_valid_number(v):
                        xs[field].append(score)
                        ys[field].append(v)
                n += 1
            results.append(CorrelationRow(
                symbol=symbol,
                daily=pearson(xs["daily_return"], ys["daily_return"]),
                weekly=pearson(xs["weekly_return"], ys["weekly_return"]),
                monthly=pearson(xs["monthly_return"], ys["monthly_return"]),
                n=n,
            ))
        return results

    def print_table(self, rows: Optional[List[CorrelationRow]] = None) -> None:
        rows = rows if rows is not None else self.run()
        print("Correlation by symbol (ignoring sentiment_score == 0):")
        print(f"{'Symbol':<8} {'Daily':>10} {'Weekly':>10} {'Monthly':>10} {'N':>5}")
        print("-" * 45)
        for row in sorted(rows, key=lambda r: r.symbol):
            def fmt(v: Optional[float]) -> str:
                return f"{v:>10.3f}" if v is not None else "N/A"
            print(f"{row.symbol:<8} {fmt(row.daily):>10} {fmt(row.weekly):>10} "
                  f"{fmt(row.monthly):>10} {row.n:>5}")


def main() -> None:
    """Console entry: `python -m financial_sentiment.analysis`."""
    CorrelationAnalyzer(Repository()).print_table()
