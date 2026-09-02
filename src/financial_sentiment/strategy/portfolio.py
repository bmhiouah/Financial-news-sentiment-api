"""Portfolio: capital + open trades + close logic."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from .trade import Side, Trade


@dataclass
class Portfolio:
    """Tracks capital, opens new trades, and closes trades when stops trigger."""

    initial_capital: float = 100.0
    trade_size: float = 20.0
    stop_loss: float = -0.05
    stop_win: float = 0.10
    capital: float = field(init=False)
    open_trades: List[Trade] = field(default_factory=list)
    closed_trades: List[Trade] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.capital = float(self.initial_capital)

    # ---- open / close ----

    def can_open(self) -> bool:
        return self.capital >= self.trade_size

    def open_trade(self, side: Side, price: float, date: str) -> Optional[Trade]:
        if not self.can_open():
            return None
        trade = Trade(side=side, entry_price=price, size=self.trade_size, entry_date=date)
        self.open_trades.append(trade)
        self.capital -= self.trade_size
        return trade

    def mark_to_market(self, price: float) -> None:
        for t in self.open_trades:
            t.update(price)

    def close_trade(self, trade: Trade, price: float, date: str, reason: str) -> None:
        if not trade.is_open:
            return
        trade.close(price, date, reason)
        # Spec: "When closed, add 20 * (1 + cumulative_return) back to capital"
        self.capital += self.trade_size * (1.0 + trade.cumulative_return)
        self.open_trades.remove(trade)
        self.closed_trades.append(trade)

    def close_stops(self, price: float, date: str) -> List[Trade]:
        """Close every open trade whose return has hit stop_loss or stop_win."""
        closed: List[Trade] = []
        for trade in list(self.open_trades):
            r = trade.cumulative_return
            if r <= self.stop_loss:
                self.close_trade(trade, price, date, "stop_loss")
                closed.append(trade)
            elif r >= self.stop_win:
                self.close_trade(trade, price, date, "stop_win")
                closed.append(trade)
        return closed

    # ---- convenience ----

    @property
    def n_open_long(self) -> int:
        return sum(1 for t in self.open_trades if t.side is Side.LONG)

    @property
    def n_open_short(self) -> int:
        return sum(1 for t in self.open_trades if t.side is Side.SHORT)

    @property
    def virtual_capital(self) -> float:
        """Capital + the liquidation value of every open trade at its
        current `cumulative_return`."""
        return self.capital + sum(
            t.size * (1.0 + t.cumulative_return) for t in self.open_trades
        )
