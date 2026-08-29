"""Abstract base class for sentiment scorers."""
from __future__ import annotations

from abc import ABC, abstractmethod

from ..domain import SentimentResult


class SentimentScorer(ABC):
    """Returns a `SentimentResult` for a piece of text."""

    name: str = "abstract"

    @abstractmethod
    def score(self, text: str) -> SentimentResult:
        ...
