#!/usr/bin/env python3
"""Recompute the forward returns on every price row already in the database.

The return columns are derived data (they depend only on the stored closes), so
when the definition changes they can be rebuilt without touching any provider.
Rows near the end of each series end up NULL, because their future return has
not happened yet.

Usage:
    python scripts/recompute_returns.py            # recompute everything
    python scripts/recompute_returns.py AAPL MSFT  # only these symbols
"""
from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from financial_sentiment.domain import RETURN_HORIZONS, add_forward_returns  # noqa: E402
from financial_sentiment.repository import Repository  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("symbols", nargs="*",
                        help="Restrict to these symbols (default: all)")
    args = parser.parse_args()

    wanted = {s.upper() for s in args.symbols}
    repo = Repository()
    repo.init()

    by_symbol: dict = defaultdict(list)
    for bar in repo.fetch_prices():
        if not wanted or bar.symbol in wanted:
            by_symbol[bar.symbol].append(bar)

    if not by_symbol:
        print("No price rows to recompute.")
        return

    print(f"Recomputing forward returns for {len(by_symbol)} symbol(s) "
          f"({sum(len(v) for v in by_symbol.values())} rows)")
    print("horizons:", ", ".join(f"{k}={v}d" for k, v in RETURN_HORIZONS.items()))

    for symbol in sorted(by_symbol):
        bars = add_forward_returns(by_symbol[symbol])
        repo.update_returns(bars)

        known = {f: sum(1 for b in bars if getattr(b, f) is not None)
                 for f in RETURN_HORIZONS}
        unknown = len(bars) - known["daily_return"]
        print(f"  {symbol:<6} {len(bars):>4} rows | daily {known['daily_return']:>4} | "
              f"weekly {known['weekly_return']:>4} | monthly {known['monthly_return']:>4} "
              f"| {unknown} too recent to have a future")

    print("\nDone. Returns are now forward-looking: "
          "return[t] = (close[t + h] - close[t]) / close[t].")


if __name__ == "__main__":
    main()
