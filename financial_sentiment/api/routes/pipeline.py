"""Pipeline router: inspect coverage and trigger the fetch + score workflow."""
from __future__ import annotations

from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, HTTPException

from ..deps import get_pipeline, get_repository
from ..schemas import PipelineRunRequest, PipelineRunResponse, ProviderStats
from ...repository import NEWS_TABLE, PRICES_TABLE, Repository


router = APIRouter(prefix="/pipeline", tags=["pipeline"])


@router.get("/status")
def pipeline_status(repo: Repository = Depends(get_repository)) -> dict:
    """Coverage summary for the current database state."""
    news = repo.fetch_news(with_sentiment_only=False)
    prices = repo.fetch_prices()
    return {
        "news_rows": len(news),
        "price_rows": len(prices),
        "symbols_with_news": len({n.symbol for n in news}),
        "symbols_with_prices": len({p.symbol for p in prices}),
        "rows_with_sentiment": sum(1 for n in news if n.finbert_score is not None),
    }


@router.post("/run", response_model=PipelineRunResponse)
def run_pipeline(
    request: PipelineRunRequest,
    pipeline=Depends(get_pipeline),
    repo: Repository = Depends(get_repository),
) -> PipelineRunResponse:
    """Run the full fetch + sentiment pipeline for the selected symbols.

    Synchronous: the pipeline runs inline and the response is returned once it
    finishes. Long-running jobs would need a background task queue.
    """
    if request.end_date < request.start_date:
        raise HTTPException(status_code=400, detail="end_date must be >= start_date")

    start = datetime.combine(request.start_date, datetime.min.time())
    end = datetime.combine(request.end_date, datetime.min.time())

    raw_results = pipeline.run(
        symbols=request.symbols,
        start=start,
        end=end,
        sources=tuple(request.sources) if request.sources else ("openbb",),
        finnhub_sources=request.finnhub_sources or None,
        force_refresh=request.force_refresh,
        analyze=request.analyze,
    )

    results = {name: ProviderStats(**stats.__dict__) for name, stats in raw_results.items()}
    warnings = list(pipeline.warnings) + _selectability_warnings(
        repo, request.symbols, start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"),
    )

    summary = (
        f"Pipeline run complete: "
        f"{sum(s.fetched for s in results.values())} items fetched "
        f"({sum(s.new for s in results.values())} new), "
        f"{sum(s.saved for s in results.values())} saved across "
        f"{len(request.symbols)} symbol(s)."
    )
    return PipelineRunResponse(results=results, summary=summary, warnings=warnings)


def _selectability_warnings(repo: Repository, symbols: List[str],
                            start: str, end: str) -> List[str]:
    """Flag symbols the Analyse tab will still refuse to show.

    Analyse only lists symbols having both a price bar and a scored news row, so
    anything missing either side silently disappears from the UI.
    """
    warnings: List[str] = []
    for symbol in symbols:
        prices = repo.coverage(symbol, PRICES_TABLE, start=start, end=end)
        news = repo.coverage(symbol, NEWS_TABLE, start=start, end=end)
        if prices.is_empty:
            warnings.append(
                f"{symbol}: no price data in [{start} -> {end}] - it will not be "
                f"selectable in Analyse until prices are available."
            )
        elif news.is_empty:
            warnings.append(
                f"{symbol}: no news in [{start} -> {end}] - it will not be "
                f"selectable in Analyse until articles are available."
            )
    return warnings
