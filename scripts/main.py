#!/usr/bin/env python3
"""CLI launcher for a plain source checkout (no editable install required).

Usage:
    python scripts/main.py --symbols AAPL MSFT --start-date 2026-07-01 --end-date 2026-08-28 --analyze

After ``pip install -e .`` the same CLI is available as ``financial-sentiment``.
"""
from _bootstrap import add_root_to_path

add_root_to_path()

from financial_sentiment.cli import main  # noqa: E402

if __name__ == "__main__":
    main()
