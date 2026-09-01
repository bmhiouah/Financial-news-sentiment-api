"""Analysis router: serve data + plot payloads from the database.

Replicates the analyses and plots from notebooks/demo.ipynb.
"""
from __future__ import annotations

import math
from collections import defaultdict
from typing import List, Optional

import numpy as np
from fastapi import APIRouter, Depends, HTTPException, Query

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
from ...analysis import pearson
from ...strategy.data import DataLoader


router = APIRouter(prefix="/analysis", tags=["analysis"])

RETURN_TYPES = ("daily", "weekly", "monthly")
N_BUCKETS = 12
MIN_SENTIMENT_N = 5  # notebook: ignore symbols with < this many sentiment observations


# --------------------------------------------------------------------------- #
# Discovery
# --------------------------------------------------------------------------- #

@router.get("/available-symbols", response_model=AvailableSymbols)
def available_symbols(repo=Depends(get_repository)) -> AvailableSymbols:
    """Symbols that have BOTH at least one price bar and at least one scored news row."""
    news = repo.fetch_news(with_sentiment_only=True)
    news_symbols = {n.symbol for n in news}
    prices = repo.fetch_prices()
    price_symbols = {p.symbol for p in prices}
    common = sorted(price_symbols & news_symbols)
    return AvailableSymbols(symbols=common, count=len(common))


@router.get("/date-range", response_model=DateRange)
def date_range(
    symbol: Optional[str] = Query(None, description="Restrict to a specific symbol"),
    repo=Depends(get_repository),
) -> DateRange:
    """Min/max dates available across prices+news, optionally for a single symbol."""
    prices = repo.fetch_prices()
    if symbol:
        prices = [p for p in prices if p.symbol == symbol]
    news = repo.fetch_news(with_sentiment_only=False)
    if symbol:
        news = [n for n in news if n.symbol == symbol]
    all_dates = [p.date for p in prices if p.date] + [n.date for n in news if n.date]
    # keep only clean YYYY-MM-DD rows (some legacy rows have full timestamps)
    all_dates = [d for d in all_dates if len(d) >= 10 and d[:10].count("-") == 2]
    if not all_dates:
        return DateRange()
    clean = [d[:10] for d in all_dates]
    return DateRange(min_date=min(clean), max_date=max(clean))


# --------------------------------------------------------------------------- #
# Correlation
# --------------------------------------------------------------------------- #

@router.get("/correlation", response_model=CorrelationTable)
def correlation_table(
    symbol: Optional[str] = None,
    repo=Depends(get_repository),
) -> CorrelationTable:
    """Per-symbol Pearson correlation of mean-daily FinBERT sentiment vs returns."""
    news = repo.fetch_news(with_sentiment_only=True)
    prices = repo.fetch_prices()

    sentiment: dict = defaultdict(list)
    for n in news:
        if n.finbert_score is not None and n.finbert_score != 0:
            sentiment[(n.symbol, n.date)].append(n.finbert_score)
    daily_sentiment = {k: sum(v) / len(v) for k, v in sentiment.items()}

    by_symbol: dict = defaultdict(list)
    for p in prices:
        by_symbol[p.symbol].append(p)

    rows: List[CorrelationRowOut] = []
    for sym, bars in by_symbol.items():
        if symbol and sym != symbol:
            continue
        bars.sort(key=lambda b: b.date)
        xs = {"daily_return": [], "weekly_return": [], "monthly_return": []}
        ys = {"daily_return": [], "weekly_return": [], "monthly_return": []}
        n = 0
        for bar in bars:
            score = daily_sentiment.get((sym, bar.date))
            if score is None:
                continue
            for field in xs:
                v = getattr(bar, field)
                if v is not None and not (isinstance(v, float) and math.isnan(v)):
                    xs[field].append(score)
                    ys[field].append(v)
            n += 1
        rows.append(CorrelationRowOut(
            symbol=sym,
            daily=pearson(xs["daily_return"], ys["daily_return"]),
            weekly=pearson(xs["weekly_return"], ys["weekly_return"]),
            monthly=pearson(xs["monthly_return"], ys["monthly_return"]),
            n=n,
        ))
    rows.sort(key=lambda r: r.symbol)
    return CorrelationTable(rows=rows)


# --------------------------------------------------------------------------- #
# Price + Sentiment series
# --------------------------------------------------------------------------- #

@router.get("/price-sentiment", response_model=List[PriceSentimentSeries])
def price_sentiment(
    symbols: List[str] = Query(..., description="Symbols to include"),
    repo=Depends(get_repository),
) -> List[PriceSentimentSeries]:
    """Price line + sentiment markers (one series per symbol)."""
    prices = [p for p in repo.fetch_prices() if p.symbol in set(symbols)]
    news_all = [n for n in repo.fetch_news(with_sentiment_only=False) if n.symbol in set(symbols)]

    by_symbol_news: dict = defaultdict(list)
    for n in news_all:
        by_symbol_news[n.symbol].append(n)

    out: List[PriceSentimentSeries] = []
    for sym in symbols:
        sym_prices = sorted([p for p in prices if p.symbol == sym], key=lambda p: p.date)
        if not sym_prices:
            continue
        sym_news = by_symbol_news.get(sym, [])
        headlines_by_date: dict = defaultdict(list)
        for n in sym_news:
            if n.date and n.headline:
                headlines_by_date[n.date].append(n.headline)
        scores_by_date: dict = defaultdict(list)
        for n in sym_news:
            if n.date and n.finbert_score is not None:
                scores_by_date[n.date].append(n.finbert_score)

        points: List[PriceSentimentPoint] = []
        for p in sym_prices:
            scores = scores_by_date.get(p.date, [])
            sent = float(sum(scores) / len(scores)) if scores else None
            label = None
            if sent is not None:
                label = "positive" if sent > 0.2 else "negative" if sent < -0.2 else "neutral"
            headlines = headlines_by_date.get(p.date, [])
            points.append(PriceSentimentPoint(
                date=p.date,
                close=float(p.close) if p.close is not None else 0.0,
                sentiment_score=sent,
                sentiment_label=label,
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
    repo=Depends(get_repository),
) -> FinBertVsLlmResponse:
    """Scatter comparison of FinBERT vs LLM sentiment on the same headlines."""
    news = repo.fetch_news(with_sentiment_only=False)
    rows = [
        n for n in news
        if n.finbert_score is not None
        and n.finbert_score != 0
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
    r = pearson([p.finbert_score for p in points], [p.llm_score for p in points]) if points else None
    return FinBertVsLlmResponse(points=points, n=len(points), pearson=r)


# --------------------------------------------------------------------------- #
# Distribution (2D histogram + correlation bars)
# --------------------------------------------------------------------------- #

def _build_distribution_for_symbol(
    symbol: str,
    return_type: str,
    daily_sentiment: dict,
    by_symbol_prices: dict,
) -> Optional[DistributionRow]:
    """Replicate the notebook's 12x12 heatmap + 3-bar correlation for one symbol.

    Returns None if the symbol has too few observations.
    """
    rcol = f"log_{return_type}_return"
    bars = by_symbol_prices.get(symbol, [])
    rows = []
    for bar in bars:
        score = daily_sentiment.get((symbol, bar.date))
        if score is None or score == 0:
            continue
        rval = getattr(bar, f"{return_type}_return", None)
        if rval is None or (isinstance(rval, float) and math.isnan(rval)) or rval <= -1:
            continue
        log_r = math.log1p(rval)
        rows.append((score, log_r))
    if len(rows) < 4:
        return None

    xs = np.array([r[0] for r in rows])
    ys = np.array([r[1] for r in rows])

    # clip returns to 5th/95th percentiles (notebook behaviour)
    lo, hi = np.percentile(ys, 5), np.percentile(ys, 95)
    if hi <= lo:
        lo, hi = ys.min(), ys.max()
        if hi <= lo:
            hi = lo + 1e-6
    ys_clipped = np.clip(ys, lo, hi)

    score_min, score_max = xs.min(), xs.max()
    if score_max <= score_min:
        score_max = score_min + 1e-6

    score_edges = np.linspace(score_min, score_max, N_BUCKETS + 1)
    ret_edges = np.linspace(lo, hi, N_BUCKETS + 1)

    H, _, _ = np.histogram2d(xs, ys_clipped, bins=[score_edges, ret_edges])
    total = H.sum()
    pct = (H / total * 100).T if total > 0 else H.T  # rows = return buckets, cols = score buckets

    score_labels = [f"{score_edges[i]:.3f} to {score_edges[i+1]:.3f}" for i in range(N_BUCKETS)]
    ret_labels = [f"{ret_edges[i]:.4f} to {ret_edges[i+1]:.4f}" for i in range(N_BUCKETS)]

    # correlation bars: same as /analysis/correlation but log returns
    corr_bars = []
    for rt in RETURN_TYPES:
        rtype_col = f"{rt}_return"
        x_vals, y_vals = [], []
        for bar in bars:
            score = daily_sentiment.get((symbol, bar.date))
            if score is None or score == 0:
                continue
            v = getattr(bar, rtype_col, None)
            if v is None or (isinstance(v, float) and math.isnan(v)):
                continue
            x_vals.append(score)
            y_vals.append(v)
        r = pearson(x_vals, y_vals)
        corr_bars.append({"name": rt.capitalize(), "value": r})

    return DistributionRow(
        symbol=symbol,
        heatmap_z=[[float(v) for v in row] for row in pct],
        heatmap_x_labels=score_labels,
        heatmap_y_labels=ret_labels,
        correlation=corr_bars,
    )


@router.get("/distribution", response_model=DistributionResponse)
def distribution(
    symbols: List[str] = Query(..., description="Symbols to include"),
    return_type: str = Query("daily", enum=RETURN_TYPES),
    repo=Depends(get_repository),
) -> DistributionResponse:
    """Per-symbol 2D histogram (sentiment x log-return) + 3-bar correlation.

    Matches the "Correlation & Distribution by Equity" section of demo.ipynb.
    """
    symbol_set = set(symbols)
    news = [n for n in repo.fetch_news(with_sentiment_only=True) if n.symbol in symbol_set]

    # daily mean sentiment per (symbol, date)
    sent: dict = defaultdict(list)
    for n in news:
        if n.finbert_score is not None and n.finbert_score != 0:
            sent[(n.symbol, n.date)].append(n.finbert_score)
    daily_sentiment = {k: sum(v) / len(v) for k, v in sent.items()}

    # filter to symbols with >= MIN_SENTIMENT_N observations
    counts: dict = defaultdict(int)
    for (s, _), _ in daily_sentiment.items():
        counts[s] += 1
    qualifying = {s for s in symbol_set if counts.get(s, 0) >= MIN_SENTIMENT_N}

    prices = [p for p in repo.fetch_prices() if p.symbol in qualifying]
    by_symbol_prices: dict = defaultdict(list)
    for p in prices:
        by_symbol_prices[p.symbol].append(p)

    rows: List[DistributionRow] = []
    for sym in sorted(qualifying):
        row = _build_distribution_for_symbol(sym, return_type, daily_sentiment, by_symbol_prices)
        if row is not None:
            rows.append(row)
    return DistributionResponse(return_type=return_type, rows=rows)


# --------------------------------------------------------------------------- #
# News (for the click-to-show feature on Price + Sentiment)
# --------------------------------------------------------------------------- #

@router.get("/news", response_model=NewsForSymbolResponse)
def news_for_symbol(
    symbol: str = Query(..., description="Symbol to fetch news for"),
    repo=Depends(get_repository),
) -> NewsForSymbolResponse:
    """Return all news rows for a single symbol (used by the click handler)."""
    all_news = repo.fetch_news(with_sentiment_only=False)
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
        for n in all_news
        if n.symbol == symbol
    ]
    items.sort(key=lambda i: (i.date, -1 if i.finbert_score is None else i.finbert_score), reverse=True)
    return NewsForSymbolResponse(symbol=symbol, items=items)
