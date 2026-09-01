"""Groq LLM sentiment scorer (OpenAI-compatible chat completions).

Mimics the FinBERT output shape: returns a label plus a continuous
"compound" score in [-1, +1] (positive - negative probability), along
with the full (positive, negative, neutral) distribution.

Set the API key via the `GROQ_API_KEY` environment variable.  Never
hard-code it in source files.
"""
from __future__ import annotations

import json
import os
import time
from typing import Optional
from dotenv import load_dotenv

import requests

from ..domain import NEGATIVE, NEUTRAL, POSITIVE, SentimentResult
from .base import SentimentScorer

load_dotenv()


GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_DEFAULT_MODEL = "openai/gpt-oss-20b"

SYSTEM_PROMPT = """You are a financial sentiment classifier that mimics FinBERT.
Given a financial news headline, classify its sentiment from the perspective
of a company/stock/market impact (not general tone).

Respond with ONLY a JSON object, no prose, no markdown fences, in this exact form:
{"positive": <float>, "negative": <float>, "neutral": <float>, "label": "<positive|negative|neutral>"}

Rules:
- positive + negative + neutral must sum to 1.0 (each between 0 and 1)
- "label" is whichever of the three has the highest probability
- Base the judgement on likely market/financial impact, e.g.:
  - "Company X beats earnings estimates" -> positive
  - "Company X faces regulatory investigation" -> negative
  - "Company X to report earnings next Tuesday" -> neutral
"""


def _extract_json(content: str) -> dict:
    """Some reasoning models prepend chatter before the JSON. Pull the
    first {...} block out of the response."""
    start = content.find("{")
    end = content.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise json.JSONDecodeError("No JSON object found in response", content, 0)
    return json.loads(content[start:end + 1])


class GroqSentimentScorer(SentimentScorer):
    """Score headlines with a Groq-hosted LLM (e.g. openai/gpt-oss-20b)."""

    name = "groq"

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = GROQ_DEFAULT_MODEL,
        endpoint: str = GROQ_API_URL,
        retries: int = 3,
        timeout: int = 20,
        pos_threshold: Optional[float] = None,
        neg_threshold: Optional[float] = None,
        load_env: bool = True,
    ) -> None:
        if load_env and not os.environ.get("GROQ_API_KEY"):
            try:
                from ..env_loader import load_project_env
                load_project_env()
            except Exception:
                pass
        self.api_key = api_key or os.environ.get("GROQ_API_KEY")
        if not self.api_key:
            raise RuntimeError(
                "Groq API key not found. Set the GROQ_API_KEY environment variable "
                "or add GROQ_API_KEY=... to a .env file at the project root."
            )
        self.model = model
        self.endpoint = endpoint
        self.retries = retries
        self.timeout = timeout
        # Local imports to avoid a circular dep at module load time
        from ..config import SETTINGS
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
            data = self._call(text)
        except Exception:
            return SentimentResult(0.0, NEUTRAL, 0.0)
        return self._to_result(data)

    def score_detailed(self, text: str) -> dict:
        """Return the full FinBERT-style dict (pos/neg/neu/label/compound_score)."""
        if not text:
            return {
                "positive": 0.0, "negative": 0.0, "neutral": 1.0,
                "label": "neutral", "compound_score": 0.0,
            }
        data = self._to_result(self._call(text))
        return {
            "positive": max(0.0, (data.score + data.confidence) / 2.0),
            "negative": max(0.0, (data.confidence - data.score) / 2.0),
            "neutral": 1.0 - data.confidence,
            "label": data.label,
            "compound_score": data.score,
        }

    # ---- internals ----

    def _call(self, text: str) -> dict:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "temperature": 0,
            "max_tokens": 200,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Headline: {text[:1000]}"},
            ],
        }
        last_err: Optional[Exception] = None
        for attempt in range(self.retries):
            try:
                resp = requests.post(
                    self.endpoint, headers=headers, json=payload, timeout=self.timeout
                )
                resp.raise_for_status()
                content = resp.json()["choices"][0]["message"]["content"].strip()
                if "```" in content:
                    parts = content.split("```")
                    content = parts[1] if len(parts) >= 2 else content
                    content = content.replace("json", "", 1).strip()
                return _extract_json(content)
            except (requests.RequestException, json.JSONDecodeError, KeyError, IndexError) as e:
                last_err = e
                time.sleep(1.5 * (attempt + 1))
        raise RuntimeError(f"Groq call failed after {self.retries} attempts: {last_err}")

    def _to_result(self, data: dict) -> SentimentResult:
        pos = float(data.get("positive", 0.0))
        neg = float(data.get("negative", 0.0))
        neu = float(data.get("neutral", 0.0))
        total = pos + neg + neu
        if total > 0:
            pos, neg, neu = pos / total, neg / total, neu / total
        compound = pos - neg
        label = data.get("label") or (
            POSITIVE if pos >= max(neg, neu)
            else NEGATIVE if neg >= max(pos, neu)
            else NEUTRAL
        )
        return SentimentResult(compound, label, abs(compound))
