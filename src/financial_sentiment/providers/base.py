"""Abstract base classes for news and price providers."""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import List, Optional

from ..domain import NewsItem, PriceBar


class NewsProvider(ABC):
    """Fetches `NewsItem`s for a list of symbols within a date range."""

    name: str = "abstract"

    @abstractmethod
    def fetch(self, symbols: List[str], start: datetime, end: datetime,
              sources: Optional[List[str]] = None) -> List[NewsItem]:
        ...


class PriceProvider(ABC):
    """Fetches daily `PriceBar`s for one symbol within a date range."""

    name: str = "abstract"

    @abstractmethod
    def fetch(self, symbol: str, start: datetime, end: datetime) -> List[PriceBar]:
        ...
