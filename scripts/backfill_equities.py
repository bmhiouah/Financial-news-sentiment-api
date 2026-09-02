#!/usr/bin/env python3
"""Populate the `equities` reference table with the tickers OpenBB exposes.

Idempotent: re-running only inserts symbols that are not already stored.

Usage:
    python scripts/backfill_equities.py                  # all major US exchanges
    python scripts/backfill_equities.py --exchanges XNAS XNYS  # specific exchanges
    python scripts/backfill_equities.py --limit 1000     # cap per-exchange count
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from openbb import obb  # noqa: E402

from financial_sentiment.domain import Equity  # noqa: E402
from financial_sentiment.repository import Repository  # noqa: E402

EXCHANGES = ["XNAS", "XNYS", "XASE"]  # NASDAQ, NYSE, NYSE American


def fetch_exchange_tickers(exchange: str, limit: int | None, delay: float) -> list[Equity]:
    """Fetch the tickers listed on one exchange (MIC code) via OpenBB."""
    try:
        result = obb.equity.search(query="", exchange=exchange)
    except Exception as e:
        print(f"  {exchange}: search failed: {e}")
        return []

    df = result.to_df()
    if df.empty:
        print(f"  {exchange}: no results")
        return []
    if limit is not None:
        df = df.head(limit)

    equities = []
    for _, row in df.iterrows():
        raw = row.to_dict()
        equities.append(Equity(
            symbol=(raw.get("symbol") or str(row.name)).upper(),
            name=raw.get("name") or raw.get("company_name") or "",
            exchange=raw.get("exchange") or raw.get("exchange_name") or "",
            sector=raw.get("sector") or "",
            industry=raw.get("industry") or "",
            market_cap=raw.get("market_cap"),
        ))

    if delay:
        time.sleep(delay)
    return equities


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exchanges", nargs="+", default=EXCHANGES,
                        help="Exchange MIC codes to query (default: all major US)")
    parser.add_argument("--limit", type=int, default=None,
                        help="Max tickers per exchange (default: no limit)")
    parser.add_argument("--delay", type=float, default=1.0,
                        help="Seconds to sleep between exchange calls (rate-limit guard)")
    parser.add_argument("--clear", action="store_true",
                        help="Delete all existing equities before backfilling")
    args = parser.parse_args()

    repo = Repository()
    repo.init()

    if args.clear:
        repo.clear_equities()
        print("Cleared equities table.")

    before = repo.equity_count()
    print(f"Starting equities table: {before} rows")

    for exchange in args.exchanges:
        print(f"\nFetching exchange: {exchange}")
        items = fetch_exchange_tickers(exchange, args.limit, args.delay)
        if not items:
            continue
        written = repo.save_equities(items)
        print(f"  {exchange}: {len(items)} fetched, {written} new, "
              f"total in DB: {repo.equity_count()}")

    after = repo.equity_count()
    print(f"\nDone. {before} -> {after} equities ({after - before} new).")


if __name__ == "__main__":
    main()
