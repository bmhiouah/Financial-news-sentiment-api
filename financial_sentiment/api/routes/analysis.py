"""Analysis router: serve data + plot payloads from the database.

Mirrors the explore/visualise workflow that used to live in a notebook:
discovery, correlation, price+sentiment series, FinBERT vs LLM comparison and
the sentiment/return distribution heatmaps.
"""
from __future__ import annotations

import math
from collections import defaultdict
from typing import Dict, List, Optional

import numpy as np
from fastapi import APIRouter, Depends, Query

from ..deps import get_repository
from ..schemas import (
    AvailableSymbols,
    CorrelationRowOut,
    CorrelationTable,
    DateRange,
    DistributionResponse,
    DistributionRow,
    FinBertVsLlmPoint,
    FinBertVsLlmResponse,
    NewsForSymbolResponse,
    NewsItemOut,
    PriceSentimentPoint,
    PriceSentimentSeries,
)
from ...analysis import CorrelationAnalyzer, daily_mean_sentiment, pearson
from ...repository import Repository

router = APIRouter(prefix="/analysis", tags=["analysis"])

RETURN_TYPES = ("daily", "weekly", "monthly")
N_BUCKETS = 12
# Ignore symbols with fewer sentiment observations than this (too noisy to plot).
MIN_SENTIMENT_N = 5

_SENTIMENT_BOUNDS = (0.2, -0.2)  # |score| above/below which a day is pos/neg


def _label(score: Optional[float]) -> Optional[str]:
    if score is None:
        return None
    positive, negative = _SENTIMENT_BOUNDS
    if score > positive:
        return "positive"
    return "negative" if score < negative else "neutral"


def _is_number(value) -> bool:
    return value is not None and not (isinstance(value, float) and math.isnan(value))


# --------------------------------------------------------------------------- #
# Discovery
# --------------------------------------------------------------------------- #

@router.get("/available-symbols", response_model=AvailableSymbols)
def available_symbols(repo: Repository = Depends(get_repository)) -> AvailableSymbols:
    """Symbols having BOTH at least one price bar and at least one scored news row."""
    news_symbols = {n.symbol for n in repo.fetch_news(with_sentiment_only=True)}
    price_symbols = {p.symbol for p in repo.fetch_prices()}
    common = sorted(price_symbols & news_symbols)
    return AvailableSymbols(symbols=common, count=len(common))


@router.get("/date-range", response_model=DateRange)
def date_range(
    symbol: Optional[str] = Query(None, description="Restrict to a specific symbol"),
    repo: Repository = Depends(get_repository),
) -> DateRange:
    """Min/max dates available across prices + news, optionally for a single symbol."""
    dates = [p.date for p in repo.fetch_prices(symbol=symbol) if p.date]
    dates += [n.date for n in repo.fetch_news(with_sentiment_only=False)
              if n.date and (symbol is None or n.symbol == symbol)]
    # Some legacy rows carry a full timestamp; keep only clean YYYY-MM-DD prefixes.
    clean = [d[:10] for d in dates if len(d) >= 10 and d[:10].count("-") == 2]
    if not clean:
        return DateRange()
    return DateRange(min_date=min(clean), max_date=max(clean))


# --------------------------------------------------------------------------- #
# Correlation
# --------------------------------------------------------------------------- #

@router.get("/correlation", response_model=CorrelationTable)
def correlation_table(
    symbol: Optional[str] = None,
    repo: Repository = Depends(get_repository),
) -> CorrelationTable:
    """Per-symbol Pearson correlation of mean-daily FinBERT sentiment vs returns."""
    rows = CorrelationAnalyzer(repo).run(symbol=symbol)
    return CorrelationTable(rows=[CorrelationRowOut(**row.__dict__) for row in rows])


# --------------------------------------------------------------------------- #
# Price + sentiment series
# --------------------------------------------------------------------------- #

@router.get("/price-sentiment", response_model=List[PriceSentimentSeries])
def price_sentiment(
    symbols: List[str] = Query(..., description="Symbols to include"),
    repo: Repository = Depends(get_repository),
) -> List[PriceSentimentSeries]:
    """Price line + daily sentiment markers (one series per symbol)."""
    news = repo.fetch_news(with_sentiment_only=False)
    out: List[PriceSentimentSeries] = []
    for sym in symbols:
        prices = repo.fetch_prices(symbol=sym)
        if not prices:
            continue
        news_by_date: Dict[str, List] = defaultdict(list)
        for item in news:
            if item.symbol == sym:
                news_by_date[item.date].append(item)

        points: List[PriceSentimentPoint] = []
        for price in prices:
            same_day = news_by_date.get(price.date, [])
            scores = [n.finbert_score for n in same_day if n.finbert_score is not None]
            mean = sum(scores) / len(scores) if scores else None
            headlines = [n.headline for n in same_day if n.headline]
            points.append(PriceSentimentPoint(
                date=price.date,
                close=float(price.close) if price.close is not None else 0.0,
                sentiment_score=mean,
                sentiment_label=_label(mean),
                headline=", ".join(headlines[:3]) or None,
            ))
        out.append(PriceSentimentSeries(symbol=sym, points=points))
    return out


# --------------------------------------------------------------------------- #
# FinBERT vs LLM comparison
# --------------------------------------------------------------------------- #

@router.get("/finbert-vs-llm", response_model=FinBertVsLlmResponse)
def finbert_vs_llm(
    symbol: Optional[str] = None,
    limit: int = Query(2000, ge=1, le=20000),
    repo: Repository = Depends(get_repository),
) -> FinBertVsLlmResponse:
    """Scatter comparison of FinBERT vs LLM sentiment on the same headlines."""
    rows = [
        n for n in repo.fetch_news(with_sentiment_only=False)
        if n.finbert_score not in (None, 0)
        and n.llm_score is not None
        and (symbol is None or n.symbol == symbol)
    ][:limit]

    points = [
        FinBertVsLlmPoint(
            symbol=n.symbol,
            finbert_score=float(n.finbert_score),
            llm_score=float(n.llm_score),
            finbert_label=n.sentiment_label,
            llm_label=n.llm_label,
            headline=n.headline or "",
        )
        for n in rows
    ]
    correlation = (
        pearson([p.finbert_score for p in points], [p.llm_score for p in points])
        if points else None
    )
    return FinBertVsLlmResponse(points=points, n=len(points), pearson=correlation)


# --------------------------------------------------------------------------- #
# Distribution (2D histogram + correlation bars)
# --------------------------------------------------------------------------- #

def _distribution_for_symbol(symbol: str, return_type: str,
                             daily_sentiment: Dict,
                             prices: List) -> Optional[DistributionRow]:
    """12x12 sentiment-vs-log-return heatmap + the 3 correlation bars.

    Returns None when the symbol has too few usable observations.
    """
    observations = []
    for bar in prices:
        score = daily_sentiment.get((symbol, bar.date))
        rval = getattr(bar, f"{return_type}_return", None)
        if not score or not _is_number(rval) or rval <= -1:
            continue
        observations.append((score, math.log1p(rval)))
    if len(observations) < 4:
        return None

    xs = np.array([s for s, _ in observations])
    ys = np.array([r for _, r in observations])

    # Clip returns to the 5th/95th percentile so a single outlier cannot flatten
    # the whole heatmap.
    lo, hi = np.percentile(ys, 5), np.percentile(ys, 95)
    if hi <= lo:
        lo, hi = ys.min(), ys.max() + 1e-6
    ys_clipped = np.clip(ys, lo, hi)

    score_min, score_max = xs.min(), xs.max()
    if score_max <= score_min:
        score_max = score_min + 1e-6

    score_edges = np.linspace(score_min, score_max, N_BUCKETS + 1)
    return_edges = np.linspace(lo, hi, N_BUCKETS + 1)
    histogram, _, _ = np.histogram2d(xs, ys_clipped,
                                     bins=[score_edges, return_edges])
    total = histogram.sum()
    # Rows = return buckets, columns = score buckets.
    percentages = (histogram / total * 100).T if total > 0 else histogram.T

    correlation_bars = []
    for name in RETURN_TYPES:
        pairs = [
            (daily_sentiment[(symbol, bar.date)], getattr(bar, f"{name}_return"))
            for bar in prices
            if daily_sentiment.get((symbol, bar.date))
            and _is_number(getattr(bar, f"{name}_return"))
        ]
        correlation_bars.append({
            "name": name.capitalize(),
            "value": pearson([s for s, _ in pairs], [r for _, r in pairs]),
        })

    return DistributionRow(
        symbol=symbol,
        heatmap_z=[[float(v) for v in row] for row in percentages],
        heatmap_x_labels=[f"{score_edges[i]:.3f} to {score_edges[i + 1]:.3f}"
                          for i in range(N_BUCKETS)],
        heatmap_y_labels=[f"{return_edges[i]:.4f} to {return_edges[i + 1]:.4f}"
                          for i in range(N_BUCKETS)],
        correlation=correlation_bars,
    )


@router.get("/distribution", response_model=DistributionResponse)
def distribution(
    symbols: List[str] = Query(..., description="Symbols to include"),
    return_type: str = Query("daily", enum=RETURN_TYPES),
    repo: Repository = Depends(get_repository),
) -> DistributionResponse:
    """Per-symbol 2D histogram (sentiment x log-return) + 3 correlation bars."""
    requested = set(symbols)
    news = [n for n in repo.fetch_news(with_sentiment_only=True)
            if n.symbol in requested]
    daily_sentiment = daily_mean_sentiment(news)

    observations: Dict[str, int] = defaultdict(int)
    for sym, _date in daily_sentiment:
        observations[sym] += 1
    qualifying = {s for s in requested if observations.get(s, 0) >= MIN_SENTIMENT_N}

    prices_by_symbol: Dict[str, List] = defaultdict(list)
    for bar in repo.fetch_prices():
        if bar.symbol in qualifying:
            prices_by_symbol[bar.symbol].append(bar)

    rows = [
        row for sym in sorted(qualifying)
        if (row := _distribution_for_symbol(
            sym, return_type, daily_sentiment, prices_by_symbol[sym])) is not None
    ]
    return DistributionResponse(return_type=return_type, rows=rows)


# --------------------------------------------------------------------------- #
# News (click-through from the price + sentiment chart)
# --------------------------------------------------------------------------- #

@router.get("/news", response_model=NewsForSymbolResponse)
def news_for_symbol(
    symbol: str = Query(..., description="Symbol to fetch news for"),
    repo: Repository = Depends(get_repository),
) -> NewsForSymbolResponse:
    """Every stored article for one symbol, most recent first."""
    items = [
        NewsItemOut(
            date=n.date,
            headline=n.headline or "",
            text=n.text or "",
            source=n.source or "",
            url=n.url or "",
            sentiment_label=n.sentiment_label,
            finbert_score=n.finbert_score,
            llm_label=n.llm_label,
            llm_score=n.llm_score,
        )
        for n in repo.fetch_news(with_sentiment_only=False)
        if n.symbol == symbol
    ]
    items.sort(key=lambda i: (i.date, -1 if i.finbert_score is None else i.finbert_score),
               reverse=True)
    return NewsForSymbolResponse(symbol=symbol, items=items)
