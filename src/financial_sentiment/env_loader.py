"""Tiny `.env` loader used by the sentiment pipeline.

Loads key=value lines from `<project_root>/.env` (and optionally from
the current working directory) into `os.environ` if the variable is
not already set. No external dependency.

Lines starting with `#` are ignored. Quotes around values are stripped.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable


def _strip_quotes(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
        return value[1:-1]
    return value


def load_env(paths: Iterable[Path]) -> int:
    """Load each path if it exists. Returns the number of variables set."""
    n = 0
    for path in paths:
        if not path.is_file():
            continue
        for raw in path.read_text().splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = _strip_quotes(value)
            if key and key not in os.environ:
                os.environ[key] = value
                n += 1
    return n


def load_project_env(project_root: Path | None = None) -> int:
    """Load `<project_root>/.env` then `<cwd>/.env` (later files don't override)."""
    if project_root is None:
        # src/financial_sentiment/env_loader.py -> ../../..
        here = Path(__file__).resolve()
        project_root = here.parents[2]
    return load_env([project_root / ".env", Path.cwd() / ".env"])
