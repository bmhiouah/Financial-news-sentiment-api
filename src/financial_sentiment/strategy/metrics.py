"""Performance metrics for a daily equity curve.

Every helper takes a plain chronological list of portfolio values (one per
trading day) and returns a plain float, so the API layer can serialise the
results without any extra dependency.

Conventions used throughout the comparison:

* returns and drawdowns are **fractions** (0.0345 == +3.45%), the UI formats them,
* max drawdown is **negative** (-0.089 == a 8.9% peak-to-trough loss),
* the Sharpe ratio uses a 0% risk-free rate and 252 trading days per year.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Sequence

TRADING_DAYS_PER_YEAR = 252
DAYS_PER_YEAR = 365.25

# Display order used by the Analyse tab heatmap.
METRIC_KEYS: Sequence[str] = ("total_return", "cagr", "max_drawdown", "sharpe_ratio")

METRIC_LABELS: Dict[str, str] = {
    "total_return": "Total Return",
    "cagr": "CAGR (annualised)",
    "max_drawdown": "Max Drawdown",
    "sharpe_ratio": "Sharpe Ratio",
}

# True when a *higher* value means a better strategy.  Max drawdown is stored
# as a negative number, so "higher" (i.e. closer to zero) is also better there.
METRIC_HIGHER_IS_BETTER: Dict[str, bool] = {key: True for key in METRIC_KEYS}


def daily_returns(values: Sequence[float]) -> List[float]:
    """Simple period-over-period returns; skips any zero/None base value."""
    out: List[float] = []
    for previous, current in zip(values, values[1:]):
        if previous:
            out.append(current / previous - 1.0)
    return out


def total_return(values: Sequence[float]) -> float:
    """Final/initial - 1 over the whole window."""
    if len(values) < 2 or not values[0]:
        return 0.0
    return values[-1] / values[0] - 1.0


def cagr(values: Sequence[float], days: float) -> float:
    """Compound annual growth rate; `days` is the calendar length of the window."""
    if len(values) < 2 or days <= 0 or not values[0] or values[-1] <= 0:
        return 0.0
    return (values[-1] / values[0]) ** (DAYS_PER_YEAR / days) - 1.0


def max_drawdown(values: Sequence[float]) -> float:
    """Worst peak-to-trough decline, as a negative fraction (0.0 when never down)."""
    peak: Optional[float] = None
    worst = 0.0
    for v in values:
        peak = v if peak is None else max(peak, v)
        if peak:
            worst = min(worst, v / peak - 1.0)
    return worst


def sharpe_ratio(values: Sequence[float]) -> float:
    """Annualised Sharpe ratio of the daily equity curve (risk-free rate = 0)."""
    returns = daily_returns(values)
    if len(returns) < 2:
        return 0.0
    mean = sum(returns) / len(returns)
    variance = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
    std = variance ** 0.5
    if std == 0:
        return 0.0
    return mean / std * (TRADING_DAYS_PER_YEAR ** 0.5)


def compute_metrics(values: Sequence[float], days: float) -> Dict[str, float]:
    """All four comparison metrics, in `METRIC_KEYS` order."""
    return {
        "total_return": total_return(values),
        "cagr": cagr(values, days),
        "max_drawdown": max_drawdown(values),
        "sharpe_ratio": sharpe_ratio(values),
    }
