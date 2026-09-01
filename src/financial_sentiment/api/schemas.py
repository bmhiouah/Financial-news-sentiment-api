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
    finnhub_sources: List[str] = Field(default=["CNBC"])
    force_refresh: bool = False
    analyze: bool = True


class ProviderStats(BaseModel):
    requested: int = 0
    fetched: int = 0
    scored: int = 0
    saved: int = 0
    promoted: int = 0
    skipped: int = 0


class PipelineRunResponse(BaseModel):
    results: dict[str, ProviderStats]
    summary: str


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
