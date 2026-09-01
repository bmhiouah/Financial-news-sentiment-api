#!/usr/bin/env python3
"""Populate the `equities` reference table with all tickers available via OpenBB.

This script discovers tradable securities from multiple exchanges and stores
them in the database's `equities` table.  It is idempotent: re-running only
inserts symbols that are not already present.

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

from openbb import obb

from financial_sentiment.repository import Repository
from financial_sentiment.domain import Equity


EXCHANGES = ["XNAS", "XNYS", "XASE"]  # NASDAQ, NYSE, NYSE American (Arca)


def _normalize_equity(symbol: str, raw: dict) -> Equity:
    """Normalize an OpenBB search result row into an Equity."""
    return Equity(
        symbol=symbol.upper(),
        name=raw.get("name") or raw.get("company_name") or "",
        exchange=raw.get("exchange") or raw.get("exchange_name") or "",
        sector=raw.get("sector") or "",
        industry=raw.get("industry") or "",
        market_cap=raw.get("market_cap"),
    )


def fetch_exchange_tickers(exchange: str, limit: int | None, delay: float) -> list[Equity]:
    """Fetch tickers for a single exchange via OpenBB equity search."""
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
        symbol = raw.get("symbol") or str(row.name)
        try:
            equities.append(_normalize_equity(symbol, raw))
        except Exception:
            equities.append(Equity(symbol=str(symbol).upper()))

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
        with repo._conn() as conn:
            conn.execute("DELETE FROM equities")
        print("Cleared equities table.")

    total_before = repo.equity_count()
    print(f"Starting equities table: {total_before} rows")

    for exchange in args.exchanges:
        print(f"\nFetching exchange: {exchange}")
        items = fetch_exchange_tickers(exchange, args.limit, args.delay)
        if not items:
            continue
        written = repo.save_equities(items)
        total_after = repo.equity_count()
        print(f"  {exchange}: {len(items)} fetched, {written} new, "
              f"total in DB: {total_after}")

    total_final = repo.equity_count()
    print(f"\nDone. {total_before} -> {total_final} equities "
          f"({total_final - total_before} new).")


if __name__ == "__main__":
    main()
