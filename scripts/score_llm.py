"""Backfill LLM-based sentiment on news rows that already have a FinBERT score.

Rows whose `llm_score` is NULL are scored with `GroqSentimentScorer` and written
back. The script is idempotent: rows that already have an `llm_score` are
skipped, so it is safe to re-run to resume an interrupted backfill.

Set the API key once via either:
  * environment variable:  export GROQ_API_KEY="gsk_..."
  * a `.env` file at the project root:  GROQ_API_KEY=gsk_...
"""
from __future__ import annotations

import argparse
import time

from _bootstrap import add_root_to_path

add_root_to_path()

# Importing the package loads <project_root>/.env, so GROQ_API_KEY is in
# os.environ by the time the scorer is constructed.
from financial_sentiment.repository import Repository  # noqa: E402
from financial_sentiment.sentiment import GroqSentimentScorer  # noqa: E402

LLM_FIELDS = ("llm_label", "llm_positive", "llm_negative", "llm_neutral", "llm_score")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
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
    scorer = GroqSentimentScorer(model=args.model, retries=args.retries)

    pending = repo.fetch_pending_llm()
    if args.limit is not None:
        pending = pending[: args.limit]
    print(f"Rows pending LLM scoring: {len(pending)}")
    if not pending:
        print("Nothing to do.")
        return

    scored = failures = 0
    batch: list = []
    started = time.time()
    for position, item in enumerate(pending, start=1):
        try:
            detailed = scorer.score_detailed(item.headline)
        except Exception as e:
            failures += 1
            print(f"[{position}/{len(pending)}] ERROR for {item.url[:60]!r}: {e}")
            continue
        for field, value in zip(LLM_FIELDS,
                                (detailed["label"], detailed["positive"],
                                 detailed["negative"], detailed["neutral"],
                                 detailed["compound_score"])):
            setattr(item, field, value)
        batch.append(item)

        if len(batch) >= args.batch_size:
            scored += repo.update_llm_scores(batch)
            batch.clear()

        if position % 25 == 0 or position == len(pending):
            elapsed = time.time() - started
            rate = position / elapsed if elapsed > 0 else 0
            eta = (len(pending) - position) / rate if rate > 0 else 0
            print(f"  {position}/{len(pending)}  ({rate:.1f}/s, ETA {eta:.0f}s)")

        if args.delay:
            time.sleep(args.delay)

    if batch:  # flush the tail
        scored += repo.update_llm_scores(batch)

    print(f"Scored {scored} rows in {time.time() - started:.1f}s "
          f"(failures: {failures})")


if __name__ == "__main__":
    main()
