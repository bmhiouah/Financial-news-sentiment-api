"""Backfill LLM-based sentiment on news rows that already have a FinBERT score.

Each row whose `llm_score` is NULL is scored with the configured
`GroqSentimentScorer` (or `FinBERTScorer` for testing) and written back
to the database. Use `--limit` to cap the number of rows scored per run.

Set the `GROQ_API_KEY` environment variable before running::

    export GROQ_API_KEY="gsk_..."
    python scripts/score_llm.py --limit 200

Run again to resume -- rows that already have an `llm_score` are skipped.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from financial_sentiment.repository import Repository
from financial_sentiment.sentiment import GroqSentimentScorer, SentimentScorer


def _build_scorer(args: argparse.Namespace) -> SentimentScorer:
    if args.scorer == "groq":
        return GroqSentimentScorer(
            model=args.model,
            retries=args.retries,
        )
    raise ValueError(f"Unknown scorer: {args.scorer}")


def _to_llm_fields(detailed: dict) -> dict:
    return {
        "llm_label": detailed["label"],
        "llm_positive": detailed["positive"],
        "llm_negative": detailed["negative"],
        "llm_neutral": detailed["neutral"],
        "llm_score": detailed["compound_score"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scorer", default="groq", choices=("groq",),
                        help="Which LLM scorer to use (default: groq)")
    parser.add_argument("--model", default="openai/gpt-oss-20b",
                        help="Groq model name")
    parser.add_argument("--limit", type=int, default=None,
                        help="Maximum number of rows to score (default: all)")
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--delay", type=float, default=0.0,
                        help="Seconds to sleep between calls (rate-limit guard)")
    args = parser.parse_args()

    repo = Repository()
    repo.init()
    scorer = _build_scorer(args)

    pending = repo.fetch_pending_llm()
    if args.limit is not None:
        pending = pending[: args.limit]
    print(f"Rows pending LLM scoring: {len(pending)}")

    updated = 0
    t0 = time.time()
    for i, item in enumerate(pending, start=1):
        try:
            detailed = scorer.score_detailed(item.headline)
        except Exception as e:
            print(f"[{i}/{len(pending)}] ERROR for {item.url[:60]!r}: {e}")
            continue
        for col, val in _to_llm_fields(detailed).items():
            setattr(item, col, val)
        repo.update_llm_score(
            item.url, item.llm_label, item.llm_positive, item.llm_negative,
            item.llm_neutral, item.llm_score,
        )
        updated += 1
        if i % 25 == 0 or i == len(pending):
            elapsed = time.time() - t0
            rate = i / elapsed if elapsed > 0 else 0
            eta = (len(pending) - i) / rate if rate > 0 else 0
            print(f"  {i}/{len(pending)}  ({rate:.1f}/s, ETA {eta:.0f}s)")
        if args.delay:
            time.sleep(args.delay)

    print(f"Scored {updated} rows in {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
