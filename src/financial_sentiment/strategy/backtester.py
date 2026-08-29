"""Backtester: orchestrates the tick loop over market data.

The output of `Backtester.run()` is the original price DataFrame loaded by
`DataLoader`, enriched with three new columns: `capital`, `open_long`,
`open_short`. On the final trading day all open trades are liquidated
back into capital so the final `capital` value represents the complete
portfolio value.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

import pandas as pd

from .data import DataLoader
from .portfolio import Portfolio
from .strategy import SentimentThresholdStrategy


# Minimum number of buy/sell signals required for a strategy to be valid
# against a given equity.
MIN_SIGNALS = 5


class InsufficientSignalsError(ValueError):
    """Raised when the strategy would generate fewer than `MIN_SIGNALS` trades."""


class Backtester:
    """Runs a `SentimentThresholdStrategy` against historical (price, sentiment)."""

    def __init__(
        self,
        portfolio: Portfolio,
        strategy: SentimentThresholdStrategy,
        loader: Optional[DataLoader] = None,
        min_signals: int = MIN_SIGNALS,
    ) -> None:
        self.portfolio = portfolio
        self.strategy = strategy
        self.loader = loader or DataLoader()
        self.min_signals = min_signals

    # ---- preflight ----

    def count_signals(self, equity: str) -> int:
        """Count how many buy/sell signals the strategy would produce for `equity`."""
        df = self.loader.load(equity)
        return int(self.strategy.signal_series(df["sentiment_score"]).notna().sum())

    def validate(self, equity: str) -> int:
        """Raise `InsufficientSignalsError` if the data produces < min_signals signals."""
        n = self.count_signals(equity)
        if n < self.min_signals:
            raise InsufficientSignalsError(
                f"Strategy on {equity!r} produces only {n} signal(s); "
                f"need at least {self.min_signals}. "
                "Try lowering buy_threshold / sell_threshold magnitude or use a different equity."
            )
        return n

    # ---- main loop ----

    def run(self, equity: str) -> pd.DataFrame:
        """Run the strategy and return the enriched price DataFrame.

        Columns added: `capital`, `virtual_capital`, `open_long`, `open_short`.

        - `capital` is the available cash, excluding open trades.
        - `virtual_capital` = `capital` + the liquidation value of all
          open trades at the current price.
        - All open trades are closed on the final tick so the last
          `capital` value equals the final `virtual_capital`.
        """
        df = self.loader.load(equity)
        self.validate(equity)

        capital: List[float] = []
        virtual: List[float] = []
        n_long: List[int] = []
        n_short: List[int] = []

        for i, row in df.iterrows():
            price = float(row["close"])
            date = row["date"]
            date_str = date.strftime("%Y-%m-%d") if hasattr(date, "strftime") else str(date)
            sentiment = float(row["sentiment_score"])

            self.portfolio.mark_to_market(price)
            self.portfolio.close_stops(price, date_str)

            side = self.strategy.signal(sentiment)
            if side is not None:
                self.portfolio.open_trade(side, price, date_str)

            capital.append(self.portfolio.capital)
            virtual.append(self.portfolio.virtual_capital)
            n_long.append(self.portfolio.n_open_long)
            n_short.append(self.portfolio.n_open_short)

        # Liquidate everything on the final day so the last `capital` cell
        # reflects the complete portfolio value (== final `virtual_capital`).
        last_row = df.iloc[-1]
        last_price = float(last_row["close"])
        last_date = last_row["date"]
        last_date_str = last_date.strftime("%Y-%m-%d") if hasattr(last_date, "strftime") else str(last_date)
        self.portfolio.mark_to_market(last_price)
        for trade in list(self.portfolio.open_trades):
            self.portfolio.close_trade(trade, last_price, last_date_str, "end_of_backtest")
        capital[-1] = self.portfolio.capital
        virtual[-1] = self.portfolio.virtual_capital
        n_long[-1] = self.portfolio.n_open_long
        n_short[-1] = self.portfolio.n_open_short

        df = df.copy()
        df["capital"] = capital
        df["virtual_capital"] = virtual
        df["open_long"] = n_long
        df["open_short"] = n_short
        return df
