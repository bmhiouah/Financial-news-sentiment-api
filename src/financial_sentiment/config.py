"""Application settings.

Resolution order:
  1. Environment variables (FINANCIAL_SENTIMENT_*)
  2. Defaults defined here
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent


@dataclass(frozen=True)
class Settings:
    db_path: Path = field(
        default_factory=lambda: Path(
            os.environ.get(
                "FINANCIAL_SENTIMENT_DB",
                str(_project_root() / "data" / "news.db"),
            )
        )
    )
    finbert_model: str = field(
        default_factory=lambda: os.environ.get(
            "FINANCIAL_SENTIMENT_FINBERT_MODEL", "ProsusAI/finbert"
        )
    )
    vllm_endpoint: str = field(
        default_factory=lambda: os.environ.get(
            "FINANCIAL_SENTIMENT_VLLM_ENDPOINT",
            "http://localhost:8000/v1/chat/completions",
        )
    )
    positive_threshold: float = field(
        default_factory=lambda: float(
            os.environ.get("FINANCIAL_SENTIMENT_POS_THRESHOLD", "0.2")
        )
    )
    negative_threshold: float = field(
        default_factory=lambda: float(
            os.environ.get("FINANCIAL_SENTIMENT_NEG_THRESHOLD", "-0.2")
        )
    )
    # Finnhub caps a single `company_news` response at ~250 items. Pagination
    # keeps going while a page is at least this large. It must stay comfortably
    # below the real cap, otherwise a truncated page looks like a complete one.
    finnhub_page_limit: int = field(
        default_factory=lambda: int(
            os.environ.get("FINANCIAL_SENTIMENT_FINNHUB_PAGE_LIMIT", "200")
        )
    )
    finnhub_max_pages: int = field(
        default_factory=lambda: int(
            os.environ.get("FINANCIAL_SENTIMENT_FINNHUB_MAX_PAGES", "40")
        )
    )
    # Ordered OpenBB price providers. The first one that returns rows wins, so a
    # symbol missing from a paid tier (FMP returns 402 for many tickers on the
    # free plan) is rescued by a free provider instead of silently yielding
    # nothing. An empty entry means "let OpenBB pick its own priority order".
    price_providers: tuple = field(
        default_factory=lambda: tuple(
            p.strip()
            for p in os.environ.get(
                "FINANCIAL_SENTIMENT_PRICE_PROVIDERS", "fmp,yfinance,tiingo"
            ).split(",")
            if p.strip()
        )
    )
    # Same idea for OpenBB news. Coverage varies a lot by ticker: Benzinga has
    # nothing for ABNB/NFLX while yfinance does.
    news_providers: tuple = field(
        default_factory=lambda: tuple(
            p.strip()
            for p in os.environ.get(
                "FINANCIAL_SENTIMENT_NEWS_PROVIDERS", ",yfinance"
            ).split(",")
        )
    )


SETTINGS = Settings()

# Backward-compatible module-level constants used by legacy code.
DB_PATH = str(SETTINGS.db_path)
FINBERT_MODEL = SETTINGS.finbert_model
VLLM_ENDPOINT = SETTINGS.vllm_endpoint
POSITIVE_THRESHOLD = SETTINGS.positive_threshold
NEGATIVE_THRESHOLD = SETTINGS.negative_threshold
