"""Strategy parameter optimizer.

Searches the (stop_loss, stop_win, buy_threshold, sell_threshold) space
in two stages:

  1. coarse grid search: every combination of the user-supplied grid,
  2. refinement: for each of the `top_k` best coarse candidates, build a
     tighter grid around it and re-search.

The objective is total P&L = final capital - initial capital, computed
on the requested (start, end) window.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from itertools import product
from typing import Dict, Iterable, List, Optional, Tuple

from .backtester import Backtester, MIN_SIGNALS
from .data import DataLoader
from .portfolio import Portfolio
from .strategy import SentimentThresholdStrategy


# --------------------------------------------------------------------------- #
# Default coarse grids
# --------------------------------------------------------------------------- #

DEFAULT_COARSE_GRID: Dict[str, List[float]] = {
    "stop_loss":     [-0.10, -0.05, -0.03],
    "stop_win":      [ 0.05,  0.10,  0.20],
    "buy_threshold": [ 0.10,  0.20,  0.30],
    "sell_threshold":[-0.10, -0.20, -0.30],
}


# --------------------------------------------------------------------------- #
# Result types
# --------------------------------------------------------------------------- #

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
        return {
            "stop_loss": self.stop_loss,
            "stop_win": self.stop_win,
            "buy_threshold": self.buy_threshold,
            "sell_threshold": self.sell_threshold,
        }


@dataclass
class OptimizationResult:
    """Top-level result returned by StrategyOptimizer.optimize()."""
    equity: str
    start: str
    end: str
    best: TrialResult
    top_k: List[TrialResult] = field(default_factory=list)
    all_trials: List[TrialResult] = field(default_factory=list)


# --------------------------------------------------------------------------- #
# Optimizer
# --------------------------------------------------------------------------- #

class StrategyOptimizer:
    """Coarse-then-refine grid search over the four strategy parameters."""

    def __init__(
        self,
        coarse_grid: Optional[Dict[str, List[float]]] = None,
        refine_factor: float = 0.5,
        refine_step_count: int = 2,
        top_k: int = 3,
        min_signals: int = MIN_SIGNALS,
        initial_capital: float = 100.0,
        trade_size: float = 20.0,
        loader: Optional[DataLoader] = None,
    ) -> None:
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

    # ---- public ----

    def optimize(self, equity: str, start: datetime, end: datetime,
                 objective: str = "pnl") -> OptimizationResult:
        """Return the best parameter set found on the (start, end) window."""
        # Stage 1: coarse grid
        coarse_trials = self._grid_search(equity, start, end, self.coarse_grid)
        if not coarse_trials:
            raise RuntimeError(
                f"No valid trial found on the coarse grid for {equity!r} "
                f"in [{start.date()} -> {end.date()}]. "
                "Loosen the min_signals requirement or change the grid."
            )

        coarse_trials.sort(key=lambda t: _objective(t, objective), reverse=True)
        seeds = coarse_trials[: self.top_k]

        # Stage 2: refine around each of the top-K seeds
        refined: List[TrialResult] = []
        for seed in seeds:
            fine_grid = self._refined_grid(seed, self.coarse_grid)
            refined.extend(self._grid_search(equity, start, end, fine_grid))

        # Combine coarse + refined and pick the best
        all_trials = coarse_trials + refined
        all_trials.sort(key=lambda t: _objective(t, objective), reverse=True)
        best = all_trials[0]

        return OptimizationResult(
            equity=equity,
            start=start.strftime("%Y-%m-%d"),
            end=end.strftime("%Y-%m-%d"),
            best=best,
            top_k=seeds,
            all_trials=all_trials,
        )

    # ---- internals ----

    def _grid_search(self, equity: str, start: datetime, end: datetime,
                     grid: Dict[str, List[float]]) -> List[TrialResult]:
        """Evaluate every combination in `grid`. Skips combos with too few signals."""
        keys = ("stop_loss", "stop_win", "buy_threshold", "sell_threshold")
        for k in keys:
            if k not in grid:
                raise ValueError(f"grid is missing required key {k!r}")
        trials: List[TrialResult] = []
        for combo in product(*(grid[k] for k in keys)):
            params = dict(zip(keys, combo))
            trial = self._evaluate(equity, start, end, params)
            if trial is not None:
                trials.append(trial)
        return trials

    def _evaluate(self, equity: str, start: datetime, end: datetime,
                  params: Dict[str, float]) -> Optional[TrialResult]:
        """Run a single backtest; return None if signals are below the threshold."""
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
            n_signals = backtester.count_signals(equity)
        except Exception:
            return None
        if n_signals < self.min_signals:
            return None
        try:
            backtester.run(equity)
        except Exception:
            return None
        return TrialResult(
            stop_loss=params["stop_loss"],
            stop_win=params["stop_win"],
            buy_threshold=params["buy_threshold"],
            sell_threshold=params["sell_threshold"],
            pnl=portfolio.capital - self.initial_capital,
            final_capital=portfolio.capital,
            n_signals=n_signals,
            n_trades=len(portfolio.closed_trades),
        )

    def _refined_grid(self, seed: TrialResult,
                      coarse: Dict[str, List[float]]) -> Dict[str, List[float]]:
        """Build a finer grid centred on `seed`, with step = factor * coarse step."""
        out: Dict[str, List[float]] = {}
        for name, values in coarse.items():
            if len(values) < 2:
                out[name] = list(values)
                continue
            coarse_step = abs(values[1] - values[0])
            fine_step = coarse_step * self.refine_factor
            center = getattr(seed, name)
            # Build coarse_step-sized neighbourhood in each direction.
            offsets = [(-i) * fine_step for i in range(self.refine_step_count, 0, -1)] + \
                      [0.0] + \
                      [(i) * fine_step for i in range(1, self.refine_step_count + 1)]
            out[name] = sorted({round(center + d, 6) for d in offsets})
        return out


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _objective(trial: TrialResult, objective: str) -> float:
    if objective == "pnl":
        return trial.pnl
    if objective == "final_capital":
        return trial.final_capital
    raise ValueError(f"Unknown objective: {objective!r}")
