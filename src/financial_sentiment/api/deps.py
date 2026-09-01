"""FastAPI dependency injection."""
from __future__ import annotations

from functools import lru_cache

from ..pipeline import Pipeline
from ..repository import Repository


@lru_cache(maxsize=1)
def get_repository():
    """Singleton Repository instance (one per process).

    SQLite handles concurrent reads fine; writes are serialized via
    the context manager.  For PostgreSQL this will switch to a
    connection pool.
    """
    repo = Repository()
    repo.init()
    return repo


def get_pipeline(repo=None):
    """Build a Pipeline using the shared repository."""
    if repo is None:
        repo = get_repository()
    return Pipeline.default(repository=repo)
