"""Application settings.

Resolution order for every value:

1. Environment variables
2. `.env` at the project root (loaded once, at import time)
3. The defaults below
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def load_dotenv(*paths: Path) -> int:
    """Load `KEY=value` lines into `os.environ` without overwriting existing values.

    Comments and surrounding quotes are ignored. Returns the number of variables set.
    """
    loaded = 0
    for path in paths:
        if not path.is_file():
            continue
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key, value = key.strip(), value.strip().strip("\"'")
            if key and key not in os.environ:
                os.environ[key] = value
                loaded += 1
    return loaded


def _env(key: str, default: str) -> str:
    return os.environ.get(key, default)


def _env_float(key: str, default: str) -> float:
    return float(_env(key, default))


def _env_int(key: str, default: str) -> int:
    return int(_env(key, default))


def _env_tuple(key: str, default: str) -> tuple:
    return tuple(part.strip() for part in _env(key, default).split(",") if part.strip())


# Read the .env file before Settings() is built so env-derived defaults pick it up.
load_dotenv(PROJECT_ROOT / ".env", Path.cwd() / ".env")


@dataclass(frozen=True)
class Settings:
    """PostgreSQL is the only supported backend."""

    database_url: str = field(
        default_factory=lambda: _env("DATABASE_URL", "postgresql:///financial_sentiment")
    )

    finbert_model: str = field(
        default_factory=lambda: _env(
            "FINANCIAL_SENTIMENT_FINBERT_MODEL", "ProsusAI/finbert"
        )
    )
    positive_threshold: float = field(
        default_factory=lambda: _env_float("FINANCIAL_SENTIMENT_POS_THRESHOLD", "0.2")
    )
    negative_threshold: float = field(
        default_factory=lambda: _env_float("FINANCIAL_SENTIMENT_NEG_THRESHOLD", "-0.2")
    )

    # Finnhub caps a single `company_news` response at ~250 items. Pagination keeps
    # going while a page is at least this large; it must stay comfortably below the
    # real cap, otherwise a truncated page looks like a complete one.
    finnhub_page_limit: int = field(
        default_factory=lambda: _env_int("FINANCIAL_SENTIMENT_FINNHUB_PAGE_LIMIT", "200")
    )
    finnhub_max_pages: int = field(
        default_factory=lambda: _env_int("FINANCIAL_SENTIMENT_FINNHUB_MAX_PAGES", "40")
    )

    # Ordered OpenBB providers. The first one that returns rows wins, so a symbol
    # missing from a paid tier (FMP answers 402 for many tickers on the free plan)
    # is rescued by a free provider instead of silently yielding nothing. An empty
    # entry means "let OpenBB pick its own priority order".
    price_providers: tuple = field(
        default_factory=lambda: _env_tuple(
            "FINANCIAL_SENTIMENT_PRICE_PROVIDERS", "fmp,yfinance,tiingo"
        )
    )
    # Same idea for OpenBB news: coverage varies a lot by ticker (Benzinga has
    # nothing for ABNB/NFLX while yfinance does).
    news_providers: tuple = field(
        default_factory=lambda: _env_tuple(
            "FINANCIAL_SENTIMENT_NEWS_PROVIDERS", ",yfinance"
        )
    )


SETTINGS = Settings()
