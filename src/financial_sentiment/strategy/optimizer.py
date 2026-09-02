"""Strategy parameter optimizer.

Searches the (stop_loss, stop_win, buy_threshold, sell_threshold) space in two
stages: a coarse grid over every combination, then a tighter grid around each
of the top-K coarse candidates. The objective is total P&L
(`final_capital - initial_capital`) on the requested window.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from itertools import product
from typing import Dict, List, Optional

from .backtester import Backtester, MIN_SIGNALS
from .data import DataLoader
from .portfolio import Portfolio
from .strategy import SentimentThresholdStrategy

PARAM_NAMES = ("stop_loss", "stop_win", "buy_threshold", "sell_threshold")

DEFAULT_COARSE_GRID: Dict[str, List[float]] = {
    "stop_loss":     [-0.10, -0.05, -0.03],
    "stop_win":      [ 0.05,  0.10,  0.20],
    "buy_threshold": [ 0.10,  0.20,  0.30],
    "sell_threshold":[-0.10, -0.20, -0.30],
}


@dataclass
class TrialResult:
    """Outcome of one (params -> backtest) evaluation."""

    stop_loss: float
    stop_win: float
    buy_threshold: float
    sell_threshold: float
    pnl: float
    final_capital: float
    n_signals: int
    n_trades: int

    @property
    def params(self) -> Dict[str, float]:
        return {name: getattr(self, name) for name in PARAM_NAMES}


@dataclass
class OptimizationResult:
    """Top-level result returned by `StrategyOptimizer.optimize()`."""

    symbol: str
    start: str
    end: str
    best: TrialResult
    all_trials: List[TrialResult]


class StrategyOptimizer:
    """Coarse-then-refine grid search over the four strategy parameters."""

    def __init__(self,
                 coarse_grid: Optional[Dict[str, List[float]]] = None,
                 refine_factor: float = 0.5,
                 refine_step_count: int = 2,
                 top_k: int = 3,
                 min_signals: int = MIN_SIGNALS,
                 initial_capital: float = 100.0,
                 trade_size: float = 20.0,
                 loader: Optional[DataLoader] = None) -> None:
        self.coarse_grid = coarse_grid or DEFAULT_COARSE_GRID
        if not 0 < refine_factor < 1:
            raise ValueError("refine_factor must be in (0, 1)")
        self.refine_factor = refine_factor
        self.refine_step_count = refine_step_count
        self.top_k = top_k
        self.min_signals = min_signals
        self.initial_capital = initial_capital
        self.trade_size = trade_size
        self.loader = loader or DataLoader()

    def optimize(self, symbol: str, start: datetime, end: datetime) -> OptimizationResult:
        """Return the best parameter set found on the (start, end) window."""
        coarse_trials = self._grid_search(symbol, start, end, self.coarse_grid)
        if not coarse_trials:
            raise RuntimeError(
                f"No valid trial found on the coarse grid for {symbol!r} "
                f"in [{start.date()} -> {end.date()}]. "
                "Loosen the min_signals requirement or change the grid."
            )

        coarse_trials.sort(key=lambda t: t.pnl, reverse=True)
        all_trials = list(coarse_trials)
        for seed in coarse_trials[: self.top_k]:
            all_trials.extend(
                self._grid_search(symbol, start, end,
                                  self._refined_grid(seed, self.coarse_grid))
            )

        all_trials.sort(key=lambda t: t.pnl, reverse=True)
        return OptimizationResult(
            symbol=symbol,
            start=start.strftime("%Y-%m-%d"),
            end=end.strftime("%Y-%m-%d"),
            best=all_trials[0],
            all_trials=all_trials,
        )

    # ---- internals ----

    def _grid_search(self, symbol: str, start: datetime, end: datetime,
                     grid: Dict[str, List[float]]) -> List[TrialResult]:
        missing = [name for name in PARAM_NAMES if name not in grid]
        if missing:
            raise ValueError(f"grid is missing required key(s): {missing}")
        trials: List[TrialResult] = []
        for combo in product(*(grid[name] for name in PARAM_NAMES)):
            trial = self._evaluate(symbol, start, end, dict(zip(PARAM_NAMES, combo)))
            if trial is not None:
                trials.append(trial)
        return trials

    def _evaluate(self, symbol: str, start: datetime, end: datetime,
                  params: Dict[str, float]) -> Optional[TrialResult]:
        """Run a single backtest; return None if it produces too few signals."""
        portfolio = Portfolio(
            initial_capital=self.initial_capital,
            trade_size=self.trade_size,
            stop_loss=params["stop_loss"],
            stop_win=params["stop_win"],
        )
        strategy = SentimentThresholdStrategy(
            buy_threshold=params["buy_threshold"],
            sell_threshold=params["sell_threshold"],
        )
        backtester = Backtester(portfolio, strategy, loader=self.loader,
                                min_signals=self.min_signals)
        try:
            n_signals = backtester.count_signals(symbol)
            if n_signals < self.min_signals:
                return None
            backtester.run(symbol)
        except Exception:
            return None
        return TrialResult(
            pnl=portfolio.capital - self.initial_capital,
            final_capital=portfolio.capital,
            n_signals=n_signals,
            n_trades=len(portfolio.closed_trades),
            **params,
        )

    def _refined_grid(self, seed: TrialResult,
                      coarse: Dict[str, List[float]]) -> Dict[str, List[float]]:
        """Build a finer grid centred on `seed`, with step = factor * coarse step."""
        refined: Dict[str, List[float]] = {}
        for name, values in coarse.items():
            if len(values) < 2:
                refined[name] = list(values)
                continue
            fine_step = abs(values[1] - values[0]) * self.refine_factor
            center = getattr(seed, name)
            offsets = [i * fine_step
                       for i in range(-self.refine_step_count,
                                      self.refine_step_count + 1)]
            refined[name] = sorted({round(center + offset, 6) for offset in offsets})
        return refined
