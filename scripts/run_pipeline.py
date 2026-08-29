#!/usr/bin/env python3
"""Backward-compatible shim. Prefer `python main.py` from the project root.

This script forwards to `financial_sentiment.cli.main` with the same
argument set, so any old invocation like

    python scripts/run_pipeline.py --symbols AAPL MSFT ...

keeps working.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from financial_sentiment.cli import main


if __name__ == "__main__":
    main()
