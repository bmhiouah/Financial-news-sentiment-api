"""Backtest router: run sentiment-threshold strategy + parameter optimization."""
from __future__ import annotations

import math
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException

from ..deps import get_repository
from ..schemas import (
    BacktestParams,
    BacktestPoint,
    BacktestRequest,
    BacktestResult,
    CompareRequest,
    ComparisonResponse,
    CurvePoint,
    OptimiseRequest,
    OptimiseResponse,
    StrategyComparisonRow,
    TrialResultOut,
)
from ...repository import Repository
from ...strategy.backtester import Backtester, InsufficientSignalsError
from ...strategy.comparison import StrategyComparator
from ...strategy.metrics import METRIC_KEYS, METRIC_LABELS
from ...strategy.optimizer import StrategyOptimizer
from ...strategy.portfolio import Portfolio
from ...strategy.strategy import SentimentThresholdStrategy


router = APIRouter(prefix="/backtest", tags=["backtest"])


# --------------------------------------------------------------------------- #
# Backtest
# --------------------------------------------------------------------------- #

@router.post("/run", response_model=BacktestResult)
def run_backtest(request: BacktestRequest, repo: Repository = Depends(get_repository)) -> BacktestResult:
    """Run a single backtest with the given symbol + parameters."""
    p = request.params
    portfolio = Portfolio(
        initial_capital=p.initial_capital,
        trade_size=p.trade_size,
        stop_loss=p.stop_loss,
        stop_win=p.stop_win,
    )
    strategy = SentimentThresholdStrategy(
        buy_threshold=p.buy_threshold,
        sell_threshold=p.sell_threshold,
    )
    backtester = Backtester(portfolio, strategy)
    try:
        signals = backtester.count_signals(request.symbol)
        if signals < 5:
            raise HTTPException(
                status_code=400,
                detail=f"Strategy on {request.symbol!r} produces only {signals} signal(s); need at least 5.",
            )
        df = backtester.run(request.symbol)
    except InsufficientSignalsError as e:
        raise HTTPException(status_code=400, detail=str(e))

    points: List[BacktestPoint] = []
    for _, row in df.iterrows():
        d = row["date"]
        d_str = d.strftime("%Y-%m-%d") if hasattr(d, "strftime") else str(d)
        points.append(BacktestPoint(
            date=d_str,
            close=float(row["close"]),
            sentiment_score=float(row["sentiment_score"]),
            capital=float(row["capital"]),
            virtual_capital=float(row["virtual_capital"]),
            open_long=int(row["open_long"]),
            open_short=int(row["open_short"]),
        ))
    return BacktestResult(
        symbol=request.symbol,
        signals=signals,
        closed_trades=len(portfolio.closed_trades),
        final_capital=portfolio.capital,
        initial_capital=p.initial_capital,
        pnl=portfolio.capital - p.initial_capital,
        points=points,
    )


# --------------------------------------------------------------------------- #
# Strategy comparison: Simple (sentiment) vs Benchmark (buy & hold)
# --------------------------------------------------------------------------- #

@router.post("/compare", response_model=ComparisonResponse)
def run_comparison(request: CompareRequest,
                   repo: Repository = Depends(get_repository)) -> ComparisonResponse:
    """Run both strategies on the same equity, data and window.

    The comparator loads the price/sentiment series once and passes it to both
    backtests, so the two runs can never diverge on data or assumptions.
    """
    p = request.params
    try:
        result = StrategyComparator().compare(
            request.symbol,
            initial_capital=p.initial_capital,
            trade_size=p.trade_size,
            stop_loss=p.stop_loss,
            stop_win=p.stop_win,
            buy_threshold=p.buy_threshold,
            sell_threshold=p.sell_threshold,
        )
    except InsufficientSignalsError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ValueError as e:
        # e.g. DataLoader: "No price data for symbol ..."
        raise HTTPException(status_code=404, detail=str(e))

    strategies = [
        StrategyComparisonRow(
            key=run.key,
            name=run.name,
            description=run.description,
            metrics=run.metrics,
            initial_capital=run.initial_capital,
            final_capital=run.final_capital,
            n_trades=run.n_trades,
            curve=[CurvePoint(date=d, value=v) for d, v in zip(run.dates, run.curve)],
        )
        for run in result.runs
    ]
    return ComparisonResponse(
        symbol=result.symbol,
        start=result.start,
        end=result.end,
        n_days=result.n_days,
        metric_keys=list(METRIC_KEYS),
        metric_labels=[METRIC_LABELS[k] for k in METRIC_KEYS],
        strategies=strategies,
    )


# --------------------------------------------------------------------------- #
# Optimisation
# --------------------------------------------------------------------------- #

@router.post("/optimize", response_model=OptimiseResponse)
def run_optimize(request: OptimiseRequest, repo: Repository = Depends(get_repository)) -> OptimiseResponse:
    """Run the coarse-then-refine grid search on the OLDEST `train_days` of data.

    The optimizer trains on the first window of available prices (chronologically
    oldest) so the resulting "best params" can then be validated by /backtest/run
    on the full dataset.
    """
    from datetime import datetime, timedelta

    prices = [p for p in repo.fetch_prices() if p.symbol == request.symbol]
    if not prices:
        raise HTTPException(status_code=404, detail=f"No price data for symbol {request.symbol!r}")
    prices.sort(key=lambda p: p.date)
    first_dt = datetime.strptime(prices[0].date, "%Y-%m-%d")
    last_dt = datetime.strptime(prices[-1].date, "%Y-%m-%d")
    total_days = (last_dt - first_dt).days
    train_days = min(request.train_days, total_days)
    # Train on the OLDEST `train_days` of available data
    start_dt = first_dt
    end_dt = first_dt + timedelta(days=train_days)

    optimizer = StrategyOptimizer(
        coarse_grid=request.coarse_grid,
        refine_factor=request.refine_factor,
        refine_step_count=request.refine_step_count,
        top_k=request.top_k,
        initial_capital=request.initial_capital,
        trade_size=request.trade_size,
    )
    try:
        result = optimizer.optimize(request.symbol, start_dt, end_dt)
    except InsufficientSignalsError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))

    def to_out(t):
        return TrialResultOut(
            stop_loss=t.stop_loss, stop_win=t.stop_win,
            buy_threshold=t.buy_threshold, sell_threshold=t.sell_threshold,
            pnl=t.pnl, final_capital=t.final_capital,
            n_signals=t.n_signals, n_trades=t.n_trades,
        )

    best = result.best
    sl_vals = sorted({t.stop_loss for t in result.all_trials})
    sw_vals = sorted({t.stop_win for t in result.all_trials})
    grid: List[List[Optional[float]]] = [
        [None for _ in sw_vals] for _ in sl_vals
    ]
    for t in result.all_trials:
        if t.buy_threshold == best.buy_threshold and t.sell_threshold == best.sell_threshold:
            i = sl_vals.index(t.stop_loss)
            j = sw_vals.index(t.stop_win)
            grid[i][j] = t.pnl

    return OptimiseResponse(
        symbol=result.equity,
        start=result.start,
        end=result.end,
        full_data_start=first_dt.strftime("%Y-%m-%d"),
        full_data_end=last_dt.strftime("%Y-%m-%d"),
        best=to_out(best),
        top_trials=[to_out(t) for t in result.all_trials[:10]],
        all_trials=[to_out(t) for t in result.all_trials],
        pnl_grid_x=sw_vals,
        pnl_grid_y=sl_vals,
        pnl_grid_z=grid,
    )
