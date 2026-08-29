"""Pipeline orchestrator: fetch, score, persist.

This is the single object that the CLI drives. It owns a `Repository`,
one or more `NewsProvider`s, one `PriceProvider`, and one `SentimentScorer`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Sequence

from .domain import Coverage, NewsItem, PriceBar, SOURCE_FINNHUB, SOURCE_OPENBB
from .providers import (
    FinnhubNewsProvider,
    NewsProvider,
    OpenBBNewsProvider,
    OpenBBPriceProvider,
    PriceProvider,
)
from .repository import Repository
from .sentiment import FinBERTScorer, SentimentScorer


# --------------------------------------------------------------------------- #
# Stats
# --------------------------------------------------------------------------- #

@dataclass
class FetchStats:
    requested: int = 0
    fetched: int = 0
    scored: int = 0
    saved: int = 0
    promoted: int = 0
    skipped: int = 0

    @property
    def api_calls(self) -> int:
        return self.fetched


# --------------------------------------------------------------------------- #
# Pipeline
# --------------------------------------------------------------------------- #

@dataclass
class Pipeline:
    """High-level data-fetching pipeline.

    Args:
      repository: storage layer
      news_providers: ordered list of `NewsProvider`s to try
      price_provider: source of historical prices
      scorer: sentiment scorer
    """

    repository: Repository
    news_providers: List[NewsProvider] = field(default_factory=list)
    price_provider: PriceProvider = field(default_factory=OpenBBPriceProvider)
    scorer: SentimentScorer = field(default_factory=FinBERTScorer)

    # ---- factories ----

    @classmethod
    def default(cls,
                repository: Optional[Repository] = None,
                scorer: Optional[SentimentScorer] = None) -> "Pipeline":
        return cls(
            repository=repository or Repository(),
            news_providers=[
                OpenBBNewsProvider(),
                FinnhubNewsProvider(),
            ],
            price_provider=OpenBBPriceProvider(),
            scorer=scorer or FinBERTScorer(),
        )

    # ---- coverage ----

    def _coverage_status(self, symbol: str, table: str,
                         start: str, end: str) -> str:
        cov = self.repository.coverage(symbol, table, start=start, end=end)
        if cov.is_empty:
            return "empty"
        if table == "prices":
            return "full" if (cov.min_date <= start and cov.max_date >= end) else "partial"
        return "full" if cov.n_rows > 0 else "partial"

    def _print_coverage(self, symbol: str, table: str, status: str,
                        start: str, end: str) -> None:
        cov = self.repository.coverage(symbol, table, start=start, end=end)
        if status == "full":
            print(f"  {symbol}: already in DB ({cov.n_rows} rows, "
                  f"{cov.min_date} -> {cov.max_date}), skipping API call")
        elif status == "partial":
            print(f"  {symbol}: partial coverage ({cov.n_rows} rows, "
                  f"{cov.min_date} -> {cov.max_date}), fetching to fill "
                  f"[{start} -> {end}]")
        else:
            print(f"  {symbol}: not in DB, fetching")

    # ---- news ----

    def _run_news_provider(self, provider: NewsProvider, table: str,
                            symbols: Sequence[str], start: datetime, end: datetime,
                            force_refresh: bool, analyze: bool,
                            finnhub_sources: Optional[List[str]] = None,
                            ) -> FetchStats:
        stats = FetchStats(requested=len(symbols))
        start_str = start.strftime("%Y-%m-%d")
        end_str = end.strftime("%Y-%m-%d")
        items: List[NewsItem] = []

        print(f"{provider.name} news:")
        for symbol in symbols:
            status = self._coverage_status(symbol, table, start_str, end_str)
            if not force_refresh and status == "full":
                self._print_coverage(symbol, table, "full", start_str, end_str)
                stats.skipped += 1
                continue
            self._print_coverage(symbol, table, status, start_str, end_str)
            kwargs = {}
            if provider.name == "finnhub" and finnhub_sources is not None:
                kwargs["sources"] = finnhub_sources
            items.extend(provider.fetch([symbol], start, end, **kwargs))

        if analyze and items:
            print(f"Analyzing {provider.name} sentiment (FinBERT)...")
            for item in items:
                result = self.scorer.score(item.headline)
                item.sentiment_label = result.label
                item.confidence = result.confidence
                item.finbert_score = result.score
                stats.scored += 1
        if items:
            stats.saved = self.repository.save_news(items, table=table)
        stats.fetched = sum(
            1 for s in symbols
            if self._coverage_status(s, table, start_str, end_str) != "full"
        )
        print(f"Saved {len(items)} {provider.name} news articles")
        return stats

    def fetch_news(self, symbols: Sequence[str], start: datetime, end: datetime,
                   sources: Sequence[str] = ("openbb", "finnhub"),
                   finnhub_sources: Optional[List[str]] = None,
                   force_refresh: bool = False,
                   analyze: bool = True) -> Dict[str, FetchStats]:
        results: Dict[str, FetchStats] = {}
        # OpenBB writes straight to `news`
        if "openbb" in sources:
            for p in self.news_providers:
                if isinstance(p, OpenBBNewsProvider):
                    results["openbb"] = self._run_news_provider(
                        p, table="news", symbols=symbols,
                        start=start, end=end, force_refresh=force_refresh,
                        analyze=analyze,
                    )
                    break
        # Finnhub writes to `finnhub_news`, then promotes + scores pending
        if "finnhub" in sources:
            for p in self.news_providers:
                if isinstance(p, FinnhubNewsProvider):
                    stats = self._run_news_provider(
                        p, table="finnhub_news", symbols=symbols,
                        start=start, end=end, force_refresh=force_refresh,
                        analyze=analyze, finnhub_sources=finnhub_sources,
                    )
                    promoted = self.repository.promote_finnhub_to_news()
                    print(f"Promoted {promoted} Finnhub headlines into the main news table")
                    stats.promoted = promoted
                    if analyze:
                        scored = self._score_pending_finnhub()
                        if scored:
                            print(f"Scored {scored} previously unscored Finnhub rows")
                            extra = self.repository.promote_finnhub_to_news()
                            print(f"Promoted {extra} additional rows after scoring")
                            stats.promoted += extra
                            stats.scored += scored
                    results["finnhub"] = stats
                    break
        return results

    def _score_pending_finnhub(self) -> int:
        pending = self.repository.fetch_pending_finnhub()
        for item in pending:
            result = self.scorer.score(item.headline)
            item.sentiment_label = result.label
            item.confidence = result.confidence
            item.finbert_score = result.score
        return self.repository.score_pending_finnhub(pending)

    # ---- prices ----

    def fetch_prices(self, symbols: Sequence[str], start: datetime, end: datetime,
                     force_refresh: bool = False) -> FetchStats:
        stats = FetchStats(requested=len(symbols))
        start_str = start.strftime("%Y-%m-%d")
        end_str = end.strftime("%Y-%m-%d")
        bars: List[PriceBar] = []

        print("Prices:")
        for symbol in symbols:
            status = self._coverage_status(symbol, "prices", start_str, end_str)
            if not force_refresh and status == "full":
                self._print_coverage(symbol, "prices", "full", start_str, end_str)
                stats.skipped += 1
                continue
            self._print_coverage(symbol, "prices", status, start_str, end_str)
            bars.extend(self.price_provider.fetch(symbol, start, end))

        if bars:
            stats.saved = self.repository.save_prices(bars)
        stats.fetched = len(bars)
        print(f"Saved {len(bars)} price records")
        return stats

    # ---- end-to-end ----

    def run(self, symbols: Sequence[str], start: datetime, end: datetime,
            sources: Sequence[str] = ("openbb", "finnhub"),
            finnhub_sources: Optional[List[str]] = None,
            force_refresh: bool = False,
            analyze: bool = True) -> Dict[str, FetchStats]:
        self.repository.init()
        results = self.fetch_news(
            symbols=symbols, start=start, end=end,
            sources=sources, finnhub_sources=finnhub_sources,
            force_refresh=force_refresh, analyze=analyze,
        )
        results["prices"] = self.fetch_prices(
            symbols=symbols, start=start, end=end, force_refresh=force_refresh,
        )
        return results
