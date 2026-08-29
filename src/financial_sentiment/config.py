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
    finnhub_page_limit: int = 245


SETTINGS = Settings()

# Backward-compatible module-level constants used by legacy code.
DB_PATH = str(SETTINGS.db_path)
FINBERT_MODEL = SETTINGS.finbert_model
VLLM_ENDPOINT = SETTINGS.vllm_endpoint
POSITIVE_THRESHOLD = SETTINGS.positive_threshold
NEGATIVE_THRESHOLD = SETTINGS.negative_threshold
