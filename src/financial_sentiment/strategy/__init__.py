"""Sentiment-driven trading strategy and backtester.

Quick start::

    from financial_sentiment import (
        Backtester, Portfolio, SentimentThresholdStrategy, InsufficientSignalsError,
    )

    portfolio = Portfolio(initial_capital=100, trade_size=20,
                          stop_loss=-0.05, stop_win=0.10)
    strategy = SentimentThresholdStrategy(buy_threshold=0.2, sell_threshold=-0.2)
    enriched = Backtester(portfolio, strategy).run(equity="AAPL")
    # `enriched` is the original price DataFrame plus
    # columns: capital, open_long, open_short
"""
from .backtester import Backtester, InsufficientSignalsError, MIN_SIGNALS
from .data import DataLoader, MarketDataPoint
from .portfolio import Portfolio
from .strategy import SentimentThresholdStrategy
from .trade import Side, Trade

__all__ = [
    "Side", "Trade",
    "Portfolio",
    "SentimentThresholdStrategy",
    "DataLoader", "MarketDataPoint",
    "Backtester", "InsufficientSignalsError", "MIN_SIGNALS",
]
