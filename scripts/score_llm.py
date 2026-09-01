"""Backfill LLM-based sentiment on news rows that already have a FinBERT score.

Each row whose `llm_score` is NULL is scored with the configured
`GroqSentimentScorer` and written back to the database. The script is
idempotent: rows that already have an `llm_score` are skipped, so it
is safe to re-run to resume an interrupted backfill.

Set the API key once via either:
  * environment variable:    export GROQ_API_KEY="gsk_..."
  * a `.env` file at the project root:    GROQ_API_KEY=gsk_...
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

# Load GROQ_API_KEY (and any other vars) from <project_root>/.env before
# importing the scorer, so the key is in os.environ by the time the
# GroqSentimentScorer constructor runs.
from financial_sentiment.env_loader import load_project_env
load_project_env(ROOT)

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
    parser.add_argument("--batch-size", type=int, default=50,
                        help="Write scored rows to the DB every N rows (default: 50)")
    args = parser.parse_args()

    repo = Repository()
    repo.init()
    scorer = _build_scorer(args)

    pending = repo.fetch_pending_llm()
    if args.limit is not None:
        pending = pending[: args.limit]
    print(f"Rows pending LLM scoring: {len(pending)}")
    if not pending:
        print("Nothing to do.")
        return

    batch: list = []
    updated = 0
    failures = 0
    t0 = time.time()
    for i, item in enumerate(pending, start=1):
        try:
            detailed = scorer.score_detailed(item.headline)
        except Exception as e:
            failures += 1
            print(f"[{i}/{len(pending)}] ERROR for {item.url[:60]!r}: {e}")
            continue
        for col, val in _to_llm_fields(detailed).items():
            setattr(item, col, val)
        batch.append(item)

        if len(batch) >= args.batch_size:
            written = repo.update_llm_scores_bulk(batch, table="news")
            updated += written
            batch.clear()

        if i % 25 == 0 or i == len(pending):
            elapsed = time.time() - t0
            rate = i / elapsed if elapsed > 0 else 0
            eta = (len(pending) - i) / rate if rate > 0 else 0
            print(f"  {i}/{len(pending)}  ({rate:.1f}/s, ETA {eta:.0f}s)")

        if args.delay:
            time.sleep(args.delay)

    # Flush remaining rows
    if batch:
        written = repo.update_llm_scores_bulk(batch, table="news")
        updated += written
        batch.clear()

    print(f"Scored {updated} rows in {time.time() - t0:.1f}s  (failures: {failures})")


if __name__ == "__main__":
    main()
