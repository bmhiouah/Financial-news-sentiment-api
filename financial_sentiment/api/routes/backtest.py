"""Backtest router: run the sentiment strategy, compare it and tune it."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException

from ..deps import get_repository
from ..schemas import (
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
from ...strategy import (
    Backtester,
    InsufficientSignalsError,
    METRIC_KEYS,
    METRIC_LABELS,
    Portfolio,
    SentimentThresholdStrategy,
    StrategyComparator,
    StrategyOptimizer,
)

router = APIRouter(prefix="/backtest", tags=["backtest"])


def _date_str(value) -> str:
    return value.strftime("%Y-%m-%d") if hasattr(value, "strftime") else str(value)


# --------------------------------------------------------------------------- #
# Backtest
# --------------------------------------------------------------------------- #

@router.post("/run", response_model=BacktestResult)
def run_backtest(request: BacktestRequest) -> BacktestResult:
    """Run a single backtest with the given symbol + parameters."""
    params = request.params
    portfolio = Portfolio(
        initial_capital=params.initial_capital,
        trade_size=params.trade_size,
        stop_loss=params.stop_loss,
        stop_win=params.stop_win,
    )
    strategy = SentimentThresholdStrategy(
        buy_threshold=params.buy_threshold,
        sell_threshold=params.sell_threshold,
    )
    backtester = Backtester(portfolio, strategy)
    try:
        signals = backtester.count_signals(request.symbol)
        if signals < 5:
            raise HTTPException(
                status_code=400,
                detail=f"Strategy on {request.symbol!r} produces only {signals} "
                       f"signal(s); need at least 5.",
            )
        df = backtester.run(request.symbol)
    except InsufficientSignalsError as e:
        raise HTTPException(status_code=400, detail=str(e))

    points = [
        BacktestPoint(
            date=_date_str(row["date"]),
            close=float(row["close"]),
            sentiment_score=float(row["sentiment_score"]),
            capital=float(row["capital"]),
            virtual_capital=float(row["virtual_capital"]),
            open_long=int(row["open_long"]),
            open_short=int(row["open_short"]),
        )
        for _, row in df.iterrows()
    ]
    return BacktestResult(
        symbol=request.symbol,
        signals=signals,
        closed_trades=len(portfolio.closed_trades),
        final_capital=portfolio.capital,
        initial_capital=params.initial_capital,
        pnl=portfolio.capital - params.initial_capital,
        points=points,
    )


# --------------------------------------------------------------------------- #
# Strategy comparison: Simple (sentiment) vs Benchmark (buy & hold)
# --------------------------------------------------------------------------- #

@router.post("/compare", response_model=ComparisonResponse)
def run_comparison(request: CompareRequest) -> ComparisonResponse:
    """Run both strategies on the same symbol, data and window.

    The comparator loads the price/sentiment series once and passes it to both
    backtests, so the two runs can never diverge on data or assumptions.
    """
    params = request.params
    try:
        result = StrategyComparator().compare(
            request.symbol,
            initial_capital=params.initial_capital,
            trade_size=params.trade_size,
            stop_loss=params.stop_loss,
            stop_win=params.stop_win,
            buy_threshold=params.buy_threshold,
            sell_threshold=params.sell_threshold,
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
            curve=[CurvePoint(date=date, value=value)
                   for date, value in zip(run.dates, run.curve)],
        )
        for run in result.runs
    ]
    return ComparisonResponse(
        symbol=result.symbol,
        start=result.start,
        end=result.end,
        n_days=result.n_days,
        metric_keys=list(METRIC_KEYS),
        metric_labels=[METRIC_LABELS[key] for key in METRIC_KEYS],
        strategies=strategies,
    )


# --------------------------------------------------------------------------- #
# Optimisation
# --------------------------------------------------------------------------- #

@router.post("/optimize", response_model=OptimiseResponse)
def run_optimize(request: OptimiseRequest,
                 repo: Repository = Depends(get_repository)) -> OptimiseResponse:
    """Run the coarse-then-refine grid search on the OLDEST `train_days` of data.

    Training on the oldest window means the resulting parameters can be
    validated by `/backtest/run` against the full dataset.
    """
    prices = repo.fetch_prices(symbol=request.symbol)
    if not prices:
        raise HTTPException(status_code=404,
                            detail=f"No price data for symbol {request.symbol!r}")
    prices.sort(key=lambda p: p.date)
    first = datetime.strptime(prices[0].date, "%Y-%m-%d")
    last = datetime.strptime(prices[-1].date, "%Y-%m-%d")
    train_days = min(request.train_days, (last - first).days)

    optimizer = StrategyOptimizer(
        coarse_grid=request.coarse_grid,
        refine_factor=request.refine_factor,
        refine_step_count=request.refine_step_count,
        top_k=request.top_k,
        initial_capital=request.initial_capital,
        trade_size=request.trade_size,
    )
    try:
        result = optimizer.optimize(request.symbol, first,
                                    first + timedelta(days=train_days))
    except (InsufficientSignalsError, RuntimeError) as e:
        raise HTTPException(status_code=400, detail=str(e))

    def to_out(trial) -> TrialResultOut:
        return TrialResultOut(**trial.__dict__)

    best = result.best
    stop_losses = sorted({t.stop_loss for t in result.all_trials})
    stop_wins = sorted({t.stop_win for t in result.all_trials})
    # P&L surface over (stop_loss, stop_win) at the best sentiment thresholds.
    grid: List[List[Optional[float]]] = [[None] * len(stop_wins)
                                         for _ in stop_losses]
    for trial in result.all_trials:
        if (trial.buy_threshold == best.buy_threshold
                and trial.sell_threshold == best.sell_threshold):
            grid[stop_losses.index(trial.stop_loss)][stop_wins.index(trial.stop_win)] = trial.pnl

    return OptimiseResponse(
        symbol=result.symbol,
        start=result.start,
        end=result.end,
        full_data_start=first.strftime("%Y-%m-%d"),
        full_data_end=last.strftime("%Y-%m-%d"),
        best=to_out(best),
        top_trials=[to_out(t) for t in result.all_trials[:10]],
        all_trials=[to_out(t) for t in result.all_trials],
        pnl_grid_x=stop_wins,
        pnl_grid_y=stop_losses,
        pnl_grid_z=grid,
    )
