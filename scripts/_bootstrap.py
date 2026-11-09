"""Shared bootstrap for the runnable scripts in this folder.

Running a file directly (``python scripts/run_api.py``) puts this directory on
``sys.path`` but not the project root, where the ``financial_sentiment`` package
lives. Adding it once lets every script import the package without an editable
install being present.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def add_root_to_path() -> None:
    """Prepend the project root once, so repeated calls never grow ``sys.path``."""
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
