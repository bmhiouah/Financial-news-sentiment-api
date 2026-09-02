"""FastAPI dependency injection."""
from __future__ import annotations

from functools import lru_cache

from ..pipeline import Pipeline
from ..repository import Repository


@lru_cache(maxsize=1)
def get_repository() -> Repository:
    """Process-wide Repository, with the schema ensured on first use."""
    repo = Repository()
    repo.init()
    return repo


def get_pipeline() -> Pipeline:
    """Pipeline built on the shared repository."""
    return Pipeline.default(repository=get_repository())
