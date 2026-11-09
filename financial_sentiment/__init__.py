"""Financial news sentiment pipeline: OpenBB -> news -> FinBERT -> PostgreSQL.

Typical use::

    from datetime import datetime
    from financial_sentiment import Pipeline

    Pipeline.default().run(
        symbols=["AAPL"], start=datetime(2026, 7, 1), end=datetime(2026, 8, 28),
        analyze=True,
    )

Sub-packages are imported explicitly when needed:
`financial_sentiment.analysis`, `financial_sentiment.strategy`,
`financial_sentiment.api`.
"""
from .config import SETTINGS
from .domain import (
    NEGATIVE,
    NEUTRAL,
    POSITIVE,
    SOURCE_FINNHUB,
    SOURCE_OPENBB,
    Coverage,
    Equity,
    NewsItem,
    PriceBar,
    SentimentResult,
)
from .pipeline import FetchStats, Pipeline
from .providers import (
    FinnhubNewsProvider,
    NewsProvider,
    OpenBBNewsProvider,
    OpenBBPriceProvider,
    PriceProvider,
)
from .repository import Repository
from .sentiment import FinBERTScorer, GroqSentimentScorer, SentimentScorer

__all__ = [
    "SETTINGS",
    # Domain
    "NewsItem", "PriceBar", "SentimentResult", "Coverage", "Equity",
    "POSITIVE", "NEGATIVE", "NEUTRAL", "SOURCE_OPENBB", "SOURCE_FINNHUB",
    # Persistence
    "Repository",
    # Ingestion
    "NewsProvider", "PriceProvider",
    "OpenBBNewsProvider", "OpenBBPriceProvider", "FinnhubNewsProvider",
    # Sentiment
    "SentimentScorer", "FinBERTScorer", "GroqSentimentScorer",
    # Orchestration
    "Pipeline", "FetchStats",
]
