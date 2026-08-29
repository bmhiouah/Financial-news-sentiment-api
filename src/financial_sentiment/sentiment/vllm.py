"""vLLM-backed sentiment scorer. Calls a chat-completions endpoint that is
expected to return JSON {"score": float, "label": "positive"|"negative"|"neutral"}.
"""
from __future__ import annotations

import json
from typing import Optional

import requests

from ..config import SETTINGS
from ..domain import NEUTRAL, POSITIVE, NEGATIVE, SentimentResult
from .base import SentimentScorer


class VLLMScorer(SentimentScorer):
    name = "vllm"

    def __init__(self, endpoint: Optional[str] = None,
                 pos_threshold: Optional[float] = None,
                 neg_threshold: Optional[float] = None) -> None:
        self.endpoint = endpoint or SETTINGS.vllm_endpoint
        self.pos_threshold = (
            pos_threshold if pos_threshold is not None else SETTINGS.positive_threshold
        )
        self.neg_threshold = (
            neg_threshold if neg_threshold is not None else SETTINGS.negative_threshold
        )

    def score(self, text: str) -> SentimentResult:
        if not text:
            return SentimentResult(0.0, NEUTRAL, 0.0)
        try:
            prompt = (
                "Rate the financial sentiment of the following text on a scale from -1 "
                "(very negative) to +1 (very positive). Return only a JSON object like "
                '{"score": 0.5, "label": "positive"}.\n\n'
                f"Text: {text[:1000]}"
            )
            response = requests.post(
                self.endpoint,
                json={
                    "model": "default",
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.0,
                },
                timeout=30,
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            data = json.loads(content)
            score = float(data.get("score", 0.0))
            score = max(-1.0, min(1.0, score))
            label = (
                POSITIVE if score > self.pos_threshold
                else NEGATIVE if score < self.neg_threshold
                else NEUTRAL
            )
            return SentimentResult(score, label, abs(score))
        except Exception:
            return SentimentResult(0.0, NEUTRAL, 0.0)
