"""Equities router: list and search the universe of tickers."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from ..deps import get_repository
from ..schemas import EquityList, EquityOut
from ...repository import Repository

router = APIRouter(prefix="/equities", tags=["equities"])


@router.get("/symbols", response_model=EquityList)
def list_equities(
    q: str | None = None,
    limit: int = 500,
    offset: int = 0,
    repo: Repository = Depends(get_repository),
) -> EquityList:
    """List tickers, optionally filtered by symbol or company name (`q`)."""
    total, items = repo.fetch_equities(query=q, limit=limit, offset=offset)
    return EquityList(total=total, items=[EquityOut(**e.__dict__) for e in items])


@router.get("/count")
def equities_count(repo: Repository = Depends(get_repository)) -> dict:
    """Total number of tickers in the equities table."""
    return {"total": repo.equity_count()}
