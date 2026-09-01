"""Equities router: list and search the universe of tickers."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query

from ..deps import get_repository
from ..schemas import EquityList, EquityOut


router = APIRouter(prefix="/equities", tags=["equities"])


@router.get("/symbols", response_model=EquityList)
def list_equities(
    q: str | None = None,
    limit: int = 500,
    offset: int = 0,
    repo=Depends(get_repository),
) -> EquityList:
    """List available tickers, optionally filtered by `q`."""
    items = repo.fetch_equities()
    if q:
        ql = q.lower()
        items = [
            e for e in items
            if ql in e.symbol.lower() or ql in (e.name or "").lower()
        ]
    total = len(items)
    page = items[offset : offset + limit]
    return EquityList(
        total=total,
        items=[EquityOut(**e.__dict__) for e in page],
    )


@router.get("/count")
def equities_count(repo=Depends(get_repository)) -> dict:
    """Total number of tickers in the equities table."""
    return {"total": repo.equity_count()}
