"""Trade objects managed by the Portfolio."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class Side(str, Enum):
    LONG = "long"
    SHORT = "short"


@dataclass
class Trade:
    """One open position.

    `cumulative_return` is the running return since entry, signed so that
    positive always means profit regardless of side:

      * LONG:  (current_price - entry_price) / entry_price
      * SHORT: (entry_price - current_price) / entry_price
    """

    side: Side
    entry_price: float
    size: float  # notional capital allocated, e.g. 20.0
    entry_date: str
    cumulative_return: float = 0.0
    exit_price: Optional[float] = None
    exit_date: Optional[str] = None
    exit_reason: Optional[str] = None

    def update(self, current_price: float) -> None:
        """Mark-to-market the running return for the given price."""
        if self.entry_price <= 0:
            self.cumulative_return = 0.0
            return
        delta = (current_price - self.entry_price) / self.entry_price
        if self.side is Side.SHORT:
            delta = -delta
        self.cumulative_return = delta

    def close(self, current_price: float, date: str, reason: str) -> None:
        self.update(current_price)
        self.exit_price = current_price
        self.exit_date = date
        self.exit_reason = reason

    @property
    def is_open(self) -> bool:
        return self.exit_date is None