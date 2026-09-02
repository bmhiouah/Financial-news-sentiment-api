"""Strategy logic: maps sentiment scores to trade-opening signals."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import pandas as pd

from .trade import Side


@dataclass
class SentimentThresholdStrategy:
    """Open a long/short when the sentiment score crosses a threshold.

    * `sentiment_score >= buy_threshold`  -> open long
    * `sentiment_score <= sell_threshold` -> open short
    """

    buy_threshold: float = 0.5
    sell_threshold: float = -0.5

    def signal(self, sentiment_score: float) -> Optional[Side]:
        if sentiment_score >= self.buy_threshold:
            return Side.LONG
        if sentiment_score <= self.sell_threshold:
            return Side.SHORT
        return None

    def signal_series(self, scores: pd.Series) -> pd.Series:
        """Vectorized: a Series of 'long' / 'short' / None, aligned to `scores`."""
        out = pd.Series([None] * len(scores), index=scores.index, dtype=object)
        out[scores >= self.buy_threshold] = Side.LONG.value
        out[scores <= self.sell_threshold] = Side.SHORT.value
        return out


@dataclass
class BuyAndHoldStrategy:
    """Benchmark strategy: buy once on the first tick and hold until the end.

    It ignores sentiment completely and looks at nothing but the position of a
    day in the series, so it cannot peek at future prices or future news.  It is
    meant to be run with the same `Portfolio` machinery as
    `SentimentThresholdStrategy` (see `StrategyComparator`) so both share every
    execution assumption: same data, same close prices, same liquidation on the
    final day.
    """

    _entered: bool = field(default=False, repr=False)

    def signal(self, sentiment_score: float) -> Optional[Side]:
        if self._entered:
            return None
        self._entered = True
        return Side.LONG

    def signal_series(self, scores: pd.Series) -> pd.Series:
        """Vectorized: a single 'long' on the first row, None afterwards."""
        out = pd.Series([None] * len(scores), index=scores.index, dtype=object)
        if len(out):
            out.iloc[0] = Side.LONG.value
        return out
