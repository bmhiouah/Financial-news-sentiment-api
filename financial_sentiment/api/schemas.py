"""Pydantic schemas for the API."""
from __future__ import annotations

from datetime import date as _date
from typing import List, Optional

from pydantic import BaseModel, Field


# --------------------------------------------------------------------------- #
# Equities
# --------------------------------------------------------------------------- #

class EquityOut(BaseModel):
    symbol: str
    name: str = ""
    exchange: str = ""
    sector: str = ""
    industry: str = ""
    market_cap: Optional[float] = None

    class Config:
        from_attributes = True


class EquityList(BaseModel):
    total: int
    items: List[EquityOut]


# --------------------------------------------------------------------------- #
# Pipeline
# --------------------------------------------------------------------------- #

class PipelineRunRequest(BaseModel):
    symbols: List[str] = Field(..., min_length=1, max_length=100)
    start_date: _date
    end_date: _date
    sources: List[str] = Field(default=["openbb"], description="openbb, finnhub, or both")
    # None/empty = keep every source. Restricting this (e.g. ["CNBC"]) is what
    # used to silently discard ~90% of the available Finnhub articles.
    finnhub_sources: Optional[List[str]] = Field(
        default=None,
        description="Restrict Finnhub to these publishers; omit for all sources",
    )
    force_refresh: bool = False
    analyze: bool = True


class ProviderStats(BaseModel):
    requested: int = 0
    fetched: int = 0
    new: int = 0
    scored: int = 0
    saved: int = 0
    promoted: int = 0
    skipped: int = 0
    failed: int = 0


class PipelineRunResponse(BaseModel):
    results: dict[str, ProviderStats]
    summary: str
    #: Non-fatal problems (e.g. "ABNB: no price data"), so a run that produced
    #: nothing for a symbol is visible instead of looking like a success.
    warnings: List[str] = []


# --------------------------------------------------------------------------- #
# Analysis
# --------------------------------------------------------------------------- #

class AvailableSymbols(BaseModel):
    symbols: List[str]
    count: int


class DateRange(BaseModel):
    min_date: Optional[str] = None
    max_date: Optional[str] = None


class CorrelationRowOut(BaseModel):
    symbol: str
    daily: Optional[float] = None
    weekly: Optional[float] = None
    monthly: Optional[float] = None
    n: int = 0


class CorrelationTable(BaseModel):
    rows: List[CorrelationRowOut]


class PriceSentimentPoint(BaseModel):
    date: str
    close: float
    sentiment_score: Optional[float] = None
    sentiment_label: Optional[str] = None
    headline: Optional[str] = None


class PriceSentimentSeries(BaseModel):
    symbol: str
    points: List[PriceSentimentPoint]


class FinBertVsLlmPoint(BaseModel):
    symbol: str
    finbert_score: float
    llm_score: float
    finbert_label: Optional[str] = None
    llm_label: Optional[str] = None
    headline: str


class FinBertVsLlmResponse(BaseModel):
    points: List[FinBertVsLlmPoint]
    n: int
    pearson: Optional[float] = None


class NewsItemOut(BaseModel):
    date: str
    headline: str
    text: str = ""
    source: str = ""
    url: str = ""
    sentiment_label: Optional[str] = None
    finbert_score: Optional[float] = None
    llm_label: Optional[str] = None
    llm_score: Optional[float] = None


class NewsForSymbolResponse(BaseModel):
    symbol: str
    items: List[NewsItemOut]


# --------------------------------------------------------------------------- #
# Distribution (2D histogram + correlation bars)
# --------------------------------------------------------------------------- #

class DistributionRow(BaseModel):
    symbol: str
    heatmap_z: List[List[float]]            # 2D percentage matrix (rows = return buckets, cols = score buckets)
    heatmap_x_labels: List[str]             # score bucket labels
    heatmap_y_labels: List[str]             # return bucket labels
    correlation: List[dict]                 # [{"name": "Daily", "value": 0.12}, ...]


class DistributionResponse(BaseModel):
    return_type: str                        # "daily" | "weekly" | "monthly"
    rows: List[DistributionRow]


# --------------------------------------------------------------------------- #
# Backtest
# --------------------------------------------------------------------------- #

class BacktestParams(BaseModel):
    initial_capital: float = 100.0
    trade_size: float = 20.0
    stop_loss: float = -0.05
    stop_win: float = 0.10
    buy_threshold: float = 0.2
    sell_threshold: float = -0.2


class BacktestRequest(BaseModel):
    symbol: str
    params: BacktestParams = BacktestParams()


class BacktestPoint(BaseModel):
    date: str
    close: float
    sentiment_score: float
    capital: float
    virtual_capital: float
    open_long: int
    open_short: int


class BacktestResult(BaseModel):
    symbol: str
    signals: int
    closed_trades: int
    final_capital: float
    initial_capital: float
    pnl: float
    points: List[BacktestPoint]


# --------------------------------------------------------------------------- #
# Strategy comparison (Simple vs Benchmark)
# --------------------------------------------------------------------------- #

class CompareRequest(BaseModel):
    symbol: str
    params: BacktestParams = BacktestParams()


class CurvePoint(BaseModel):
    date: str
    value: float                      # portfolio value (virtual_capital)


class ComparisonMetrics(BaseModel):
    """All values are fractions/ ratios; the UI formats them.

    `max_drawdown` is negative (e.g. -0.089 == an 8.9% peak-to-trough loss).
    """

    total_return: float
    cagr: float
    max_drawdown: float
    sharpe_ratio: float


class StrategyComparisonRow(BaseModel):
    key: str                          # "simple" | "benchmark"
    name: str                         # display name
    description: str
    metrics: ComparisonMetrics
    initial_capital: float
    final_capital: float
    n_trades: int
    curve: List[CurvePoint]


class ComparisonResponse(BaseModel):
    symbol: str
    start: str
    end: str
    n_days: int                       # trading days in the shared window
    metric_keys: List[str]            # row order for the heatmap
    metric_labels: List[str]          # row labels for the heatmap
    strategies: List[StrategyComparisonRow]


# --------------------------------------------------------------------------- #
# Optimisation
# --------------------------------------------------------------------------- #

class TrialResultOut(BaseModel):
    stop_loss: float
    stop_win: float
    buy_threshold: float
    sell_threshold: float
    pnl: float
    final_capital: float
    n_signals: int
    n_trades: int


class OptimiseRequest(BaseModel):
    symbol: str
    train_days: int = Field(default=30, ge=5, le=365)
    coarse_grid: Optional[dict] = None      # override default grid
    top_k: int = Field(default=3, ge=1, le=10)
    refine_factor: float = Field(default=0.5, gt=0, lt=1)
    refine_step_count: int = Field(default=2, ge=1, le=5)
    initial_capital: float = 100.0
    trade_size: float = 20.0


class OptimiseResponse(BaseModel):
    symbol: str
    start: str                            # optimizer training window start
    end: str                              # optimizer training window end
    full_data_start: str                  # first date available for /backtest/run
    full_data_end: str                    # last date available for /backtest/run
    best: TrialResultOut
    top_trials: List[TrialResultOut]
    all_trials: List[TrialResultOut]
    pnl_grid_x: List[float]                 # stop_win values
    pnl_grid_y: List[float]                 # stop_loss values
    pnl_grid_z: List[List[Optional[float]]]  # P&L at (sl, sw) for best buy/sell thresholds
