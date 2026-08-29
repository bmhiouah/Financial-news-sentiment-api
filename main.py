#!/usr/bin/env python3
"""Single entry point for the financial sentiment pipeline.

Usage:
    python main.py --symbols AAPL MSFT --start-date 2026-07-01 --end-date 2026-08-28 --analyze
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from financial_sentiment.cli import main


if __name__ == "__main__":
    main()
