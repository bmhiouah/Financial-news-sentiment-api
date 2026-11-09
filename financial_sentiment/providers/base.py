"""Abstract base classes for news and price providers."""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import List, Optional, Sequence

from ..domain import NewsItem, PriceBar
from ..repository import NEWS_TABLE


class NewsProvider(ABC):
    """Fetches `NewsItem`s for a list of symbols within a date range.

    Subclasses declare where their rows land: providers that need a staging
    step (Finnhub rows are scored before joining the main table) override
    `table` with their own.
    """

    name: str = "abstract"
    table: str = NEWS_TABLE

    @abstractmethod
    def fetch(self, symbols: List[str], start: datetime, end: datetime,
              publishers: Optional[Sequence[str]] = None) -> List[NewsItem]:
        """Fetch news. `publishers` restricts by outlet; not every provider uses it."""


class PriceProvider(ABC):
    """Fetches daily `PriceBar`s for one symbol within a date range."""

    name: str = "abstract"

    @abstractmethod
    def fetch(self, symbol: str, start: datetime, end: datetime) -> List[PriceBar]:
        ...
