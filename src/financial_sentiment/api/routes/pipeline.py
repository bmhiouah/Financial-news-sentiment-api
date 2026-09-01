"""Pipeline router: trigger the fetch + score workflow."""
from __future__ import annotations

from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, HTTPException

from ..deps import get_pipeline, get_repository
from ..schemas import PipelineRunRequest, PipelineRunResponse, ProviderStats


router = APIRouter(prefix="/pipeline", tags=["pipeline"])


@router.get("/status")
def pipeline_status(repo=Depends(get_repository)) -> dict:
    """Coverage summary for the current database state."""
    news = repo.fetch_news(with_sentiment_only=False)
    prices = repo.fetch_prices()
    news_symbols = {n.symbol for n in news}
    price_symbols = {p.symbol for p in prices}
    sentiment_count = sum(1 for n in news if n.finbert_score is not None)
    return {
        "news_rows": len(news),
        "price_rows": len(prices),
        "symbols_with_news": len(news_symbols),
        "symbols_with_prices": len(price_symbols),
        "rows_with_sentiment": sentiment_count,
    }


@router.post("/run", response_model=PipelineRunResponse)
def run_pipeline(
    request: PipelineRunRequest,
    pipeline=Depends(get_pipeline),
    repo=Depends(get_repository),
) -> PipelineRunResponse:
    """Run the full fetch + sentiment pipeline for the selected symbols.

    This is a synchronous endpoint: it runs the pipeline inline and
    returns when finished.  For long-running jobs, wrap with a
    background task queue (Celery / RQ) later.
    """
    if request.end_date < request.start_date:
        raise HTTPException(status_code=400, detail="end_date must be >= start_date")

    start = datetime.combine(request.start_date, datetime.min.time())
    end = datetime.combine(request.end_date, datetime.min.time())

    sources = tuple(request.sources) if request.sources else ("openbb",)
    # An empty list is as good as "no filter": keep every publisher.
    finnhub_sources = request.finnhub_sources or None

    raw_results = pipeline.run(
        symbols=request.symbols,
        start=start,
        end=end,
        sources=sources,
        finnhub_sources=finnhub_sources,
        force_refresh=request.force_refresh,
        analyze=request.analyze,
    )

    results = {
        name: ProviderStats(**stats.__dict__)
        for name, stats in raw_results.items()
    }

    warnings = list(pipeline.warnings)
    warnings.extend(_selectability_warnings(
        repo, request.symbols,
        start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"),
    ))

    total_fetched = sum(s.fetched for s in results.values())
    total_saved = sum(s.saved for s in results.values())
    total_new = sum(s.new for s in results.values())
    summary = (
        f"Pipeline run complete: {total_fetched} items fetched "
        f"({total_new} new), {total_saved} saved across "
        f"{len(request.symbols)} symbol(s)."
    )
    return PipelineRunResponse(results=results, summary=summary,
                               warnings=warnings)


def _selectability_warnings(repo, symbols, start: str, end: str) -> List[str]:
    """Flag symbols the Analyse tab will still refuse to show.

    Analyse only lists symbols having both a price bar and a scored news row,
    so anything missing either side silently disappears from the UI.
    """
    out: List[str] = []
    for symbol in symbols:
        prices = repo.coverage(symbol, "prices", start=start, end=end)
        news = repo.coverage(symbol, "news", start=start, end=end)
        if prices.is_empty:
            out.append(
                f"{symbol}: no price data in [{start} -> {end}] - it will not "
                f"be selectable in Analyse until prices are available."
            )
        elif news.is_empty:
            out.append(
                f"{symbol}: no news in [{start} -> {end}] - it will not be "
                f"selectable in Analyse until articles are available."
            )
    return out
