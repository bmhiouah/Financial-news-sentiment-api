"""Side-by-side comparison of the sentiment strategy against a benchmark.

`StrategyComparator` runs two strategies over **one** loaded price/sentiment
DataFrame, so both see exactly the same bars, the same close prices and the
same date window.  Every other assumption is shared too:

* both start from the same `initial_capital`,
* both open positions at the close of the day their signal fires on,
* both are marked to market with `Portfolio.virtual_capital`,
* both are fully liquidated on the final bar by `Backtester`.

The only intentional difference is *when* they trade.  The benchmark is a
buy-and-hold: it invests 100% of the capital in a single long on the first bar
and never touches it again, so it is a pure "did the sentiment strategy beat
just owning the stock?" reference.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

import pandas as pd

from .backtester import Backtester, MIN_SIGNALS
from .data import DataLoader
from .metrics import compute_metrics
from .portfolio import Portfolio
from .strategy import BuyAndHoldStrategy, SentimentThresholdStrategy


SIMPLE_KEY = "simple"
BENCHMARK_KEY = "benchmark"

SIMPLE_NAME = "Simple Strategy"
BENCHMARK_NAME = "Benchmark (Buy & Hold)"

SIMPLE_DESCRIPTION = (
    "Sentiment-threshold strategy: opens a long/short of `trade_size` whenever the "
    "daily FinBERT score crosses the buy/sell threshold, with stop-loss / stop-win "
    "exits. Capital sits in cash between signals."
)
BENCHMARK_DESCRIPTION = (
    "Buys the equity once with 100% of the capital on the first bar and holds it "
    "until the last bar. No sentiment, no stops, no timing."
)


@dataclass
class StrategyRun:
    """One strategy's outcome: metrics + the daily equity curve."""

    key: str
    name: str
    description: str
    metrics: dict                 # {"total_return": .., "cagr": .., ...}
    initial_capital: float
    final_capital: float
    n_trades: int
    dates: List[str]
    curve: List[float]            # portfolio value per trading day


@dataclass
class ComparisonResult:
    """Both strategies evaluated on the same data and the same window."""

    symbol: str
    start: str
    end: str
    n_days: int                   # number of trading days in the window
    runs: List[StrategyRun]


class StrategyComparator:
    """Runs the sentiment strategy and the buy-and-hold benchmark together."""

    def __init__(self, loader: Optional[DataLoader] = None) -> None:
        self.loader = loader or DataLoader()

    # ---- public ----

    def compare(
        self,
        symbol: str,
        initial_capital: float = 100.0,
        trade_size: float = 20.0,
        stop_loss: float = -0.05,
        stop_win: float = 0.10,
        buy_threshold: float = 0.2,
        sell_threshold: float = -0.2,
    ) -> ComparisonResult:
        """Run both strategies on `symbol` and return their metrics + curves.

        Raises `InsufficientSignalsError` when the sentiment strategy would
        produce fewer than `MIN_SIGNALS` trades (unchanged from `Backtester`).
        """
        # Loaded once and handed to both backtests -> identical data, always.
        df = self.loader.load(symbol)
        dates = [_as_date_str(d) for d in df["date"]]
        days = _calendar_days(dates)

        simple_df, simple_portfolio = self._run_simple(
            df, symbol, initial_capital, trade_size,
            stop_loss, stop_win, buy_threshold, sell_threshold,
        )
        benchmark_df, benchmark_portfolio = self._run_benchmark(df, symbol, initial_capital)

        return ComparisonResult(
            symbol=symbol,
            start=dates[0] if dates else "",
            end=dates[-1] if dates else "",
            n_days=len(dates),
            runs=[
                _to_run(SIMPLE_KEY, SIMPLE_NAME, SIMPLE_DESCRIPTION,
                        simple_df, simple_portfolio, initial_capital, days),
                _to_run(BENCHMARK_KEY, BENCHMARK_NAME, BENCHMARK_DESCRIPTION,
                        benchmark_df, benchmark_portfolio, initial_capital, days),
            ],
        )

    # ---- internals ----

    def _run_simple(self, df: pd.DataFrame, symbol: str, initial_capital: float,
                    trade_size: float, stop_loss: float, stop_win: float,
                    buy_threshold: float, sell_threshold: float):
        portfolio = Portfolio(
            initial_capital=initial_capital,
            trade_size=trade_size,
            stop_loss=stop_loss,
            stop_win=stop_win,
        )
        strategy = SentimentThresholdStrategy(
            buy_threshold=buy_threshold,
            sell_threshold=sell_threshold,
        )
        result = Backtester(portfolio, strategy, loader=self.loader,
                            min_signals=MIN_SIGNALS).run(symbol, df=df)
        return result, portfolio

    def _run_benchmark(self, df: pd.DataFrame, symbol: str, initial_capital: float):
        # One long position funded with the whole capital, stops disabled so the
        # position is never exited early, and min_signals=1 because buy & hold
        # produces exactly one entry by construction.
        portfolio = Portfolio(
            initial_capital=initial_capital,
            trade_size=initial_capital,
            stop_loss=float("-inf"),
            stop_win=float("inf"),
        )
        result = Backtester(portfolio, BuyAndHoldStrategy(), loader=self.loader,
                            min_signals=1).run(symbol, df=df)
        return result, portfolio


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _as_date_str(value) -> str:
    return value.strftime("%Y-%m-%d") if hasattr(value, "strftime") else str(value)


def _calendar_days(dates: List[str]) -> float:
    """Calendar length of the window, used to annualise the CAGR."""
    if len(dates) < 2:
        return 0.0
    try:
        first = datetime.strptime(dates[0], "%Y-%m-%d")
        last = datetime.strptime(dates[-1], "%Y-%m-%d")
    except ValueError:
        first = last = None  # type: ignore[assignment]
    if first is None or last is None or last <= first:
        # Fall back to an estimate from the trading-day count.
        return len(dates) / 252.0 * 365.25
    return float((last - first).days)


def _to_run(key: str, name: str, description: str, df: pd.DataFrame,
            portfolio: Portfolio, initial_capital: float, days: float) -> StrategyRun:
    """Build a `StrategyRun` from an enriched backtest DataFrame.

    The equity curve is `virtual_capital` for both strategies: cash plus the
    liquidation value of every open position at that day's close.
    """
    curve = [float(v) for v in df["virtual_capital"]]
    return StrategyRun(
        key=key,
        name=name,
        description=description,
        metrics=compute_metrics(curve, days),
        initial_capital=float(initial_capital),
        final_capital=curve[-1] if curve else float(initial_capital),
        n_trades=len(portfolio.closed_trades),
        dates=[_as_date_str(d) for d in df["date"]],
        curve=curve,
    )
