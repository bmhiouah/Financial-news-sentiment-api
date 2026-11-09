"""FinBERT sentiment scorer (ProsusAI/finbert)."""
from __future__ import annotations

from typing import Optional

from ..config import SETTINGS
from ..domain import NEUTRAL, POSITIVE, NEGATIVE, SentimentResult
from .base import SentimentScorer


class FinBERTScorer(SentimentScorer):
    """Lazy-loaded FinBERT pipeline, returns score in [-1, +1]."""

    name = "finbert"

    def __init__(self, model_name: Optional[str] = None,
                 pos_threshold: Optional[float] = None,
                 neg_threshold: Optional[float] = None) -> None:
        self.model_name = model_name or SETTINGS.finbert_model
        self.pos_threshold = (
            pos_threshold if pos_threshold is not None else SETTINGS.positive_threshold
        )
        self.neg_threshold = (
            neg_threshold if neg_threshold is not None else SETTINGS.negative_threshold
        )
        self._pipeline = None

    def _load(self):
        if self._pipeline is None:
            from transformers import pipeline  # local import keeps startup fast
            self._pipeline = pipeline(
                "sentiment-analysis",
                model=self.model_name,
                truncation=True,
                max_length=512,
            )
        return self._pipeline

    def score(self, text: str) -> SentimentResult:
        if not text:
            return SentimentResult(0.0, NEUTRAL, 0.0)
        try:
            results = self._load()(text[:512])
            pos = neg = 0.0
            for r in results:
                label = r["label"].lower()
                prob = float(r["score"])
                if label == POSITIVE:
                    pos = prob
                elif label == NEGATIVE:
                    neg = prob
            continuous = pos - neg
            label = (
                POSITIVE if continuous > self.pos_threshold
                else NEGATIVE if continuous < self.neg_threshold
                else NEUTRAL
            )
            return SentimentResult(continuous, label, abs(continuous))
        except Exception:
            return SentimentResult(0.0, NEUTRAL, 0.0)
