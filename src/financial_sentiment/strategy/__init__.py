"""Sentiment-driven trading strategy and backtester.

Quick start::

    from financial_sentiment import (
        Backtester, Portfolio, SentimentThresholdStrategy, InsufficientSignalsError,
        StrategyOptimizer, OptimizationResult, TrialResult,
    )

    portfolio = Portfolio(initial_capital=100, trade_size=20,
                          stop_loss=-0.05, stop_win=0.10)
    strategy = SentimentThresholdStrategy(buy_threshold=0.2, sell_threshold=-0.2)
    enriched = Backtester(portfolio, strategy).run(equity="AAPL")
    # `enriched` is the original price DataFrame plus
    # columns: capital, virtual_capital, open_long, open_short

    # Hyperparameter search on a 1-month window
    from datetime import datetime
    result = StrategyOptimizer().optimize("AAPL", datetime(2026, 7, 1), datetime(2026, 8, 1))
    print(result.best.params, result.best.pnl)
"""
from .backtester import Backtester, InsufficientSignalsError, MIN_SIGNALS
from .comparison import (
    BENCHMARK_KEY,
    BENCHMARK_NAME,
    SIMPLE_KEY,
    SIMPLE_NAME,
    ComparisonResult,
    StrategyComparator,
    StrategyRun,
)
from .data import DataLoader, MarketDataPoint
from .metrics import (
    METRIC_KEYS,
    METRIC_LABELS,
    cagr,
    compute_metrics,
    max_drawdown,
    sharpe_ratio,
    total_return,
)
from .optimizer import (
    DEFAULT_COARSE_GRID,
    OptimizationResult,
    StrategyOptimizer,
    TrialResult,
)
from .portfolio import Portfolio
from .strategy import BuyAndHoldStrategy, SentimentThresholdStrategy
from .trade import Side, Trade

__all__ = [
    "Side", "Trade",
    "Portfolio",
    "SentimentThresholdStrategy", "BuyAndHoldStrategy",
    "DataLoader", "MarketDataPoint",
    "Backtester", "InsufficientSignalsError", "MIN_SIGNALS",
    "StrategyComparator", "ComparisonResult", "StrategyRun",
    "SIMPLE_KEY", "BENCHMARK_KEY", "SIMPLE_NAME", "BENCHMARK_NAME",
    "METRIC_KEYS", "METRIC_LABELS",
    "compute_metrics", "total_return", "cagr", "sharpe_ratio", "max_drawdown",
    "StrategyOptimizer", "OptimizationResult", "TrialResult", "DEFAULT_COARSE_GRID",
]
