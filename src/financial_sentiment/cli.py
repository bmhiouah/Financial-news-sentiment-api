"""Command-line entry point for the financial sentiment pipeline."""
from __future__ import annotations

import argparse
from datetime import datetime
from typing import List, Sequence

from .pipeline import Pipeline


def _parse_args(argv: Sequence[str] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch financial news, score sentiment, and load prices."
    )
    parser.add_argument("--symbols", nargs="+", required=True,
                        help="Stock symbols to fetch")
    parser.add_argument("--start-date", required=True, help="YYYY-MM-DD")
    parser.add_argument("--end-date", required=True, help="YYYY-MM-DD")
    parser.add_argument("--analyze", action="store_true",
                        help="Run FinBERT sentiment on fetched headlines")
    parser.add_argument("--source", choices=("openbb", "finnhub", "both"),
                        default="both", help="News source (default: both)")
    parser.add_argument("--finnhub-sources", nargs="+", default=["CNBC"],
                        help="Sources to keep for Finnhub (default: CNBC)")
    parser.add_argument("--force-refresh", action="store_true",
                        help="Re-fetch even when DB already covers the window")
    return parser.parse_args(argv)


def _resolve_sources(choice: str) -> List[str]:
    if choice == "both":
        return ["openbb", "finnhub"]
    return [choice]


def main(argv: Sequence[str] = None) -> None:
    args = _parse_args(argv)
    start = datetime.strptime(args.start_date, "%Y-%m-%d")
    end = datetime.strptime(args.end_date, "%Y-%m-%d")

    Pipeline.default().run(
        symbols=args.symbols,
        start=start,
        end=end,
        sources=_resolve_sources(args.source),
        finnhub_sources=args.finnhub_sources,
        force_refresh=args.force_refresh,
        analyze=args.analyze,
    )


if __name__ == "__main__":
    main()
