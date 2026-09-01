"""Pipeline orchestrator: fetch, score, persist.

This is the single object that the CLI drives. It owns a `Repository`,
one or more `NewsProvider`s, one `PriceProvider`, and one `SentimentScorer`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Sequence, Set

from .domain import Coverage, NewsItem, PriceBar, SOURCE_FINNHUB, SOURCE_OPENBB, news_key
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
    new: int = 0       # articles not already in the database
    scored: int = 0
    saved: int = 0
    promoted: int = 0
    skipped: int = 0
    failed: int = 0    # symbols where every provider came back empty

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
    #: Human-readable problems hit during the last run (empty providers, etc.).
    warnings: List[str] = field(default_factory=list)

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
            # News is re-fetched every run (providers never guarantee they
            # returned everything), prices are genuinely skipped.
            action = "skipping API call" if table == "prices" else "re-checking"
            print(f"  {symbol}: already in DB ({cov.n_rows} rows, "
                  f"{cov.min_date} -> {cov.max_date}), {action}")
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
        """Fetch news for every symbol and store whatever is not there yet.

        News is always re-fetched (there is no reliable way to know a provider
        gave us everything last time) and de-duplicated against the database
        before scoring, so a repeat run costs API calls but no FinBERT work.
        """
        stats = FetchStats(requested=len(symbols))
        start_str = start.strftime("%Y-%m-%d")
        end_str = end.strftime("%Y-%m-%d")
        items: List[NewsItem] = []

        print(f"{provider.name} news:")
        for symbol in symbols:
            self._print_coverage(symbol, table,
                                 self._coverage_status(symbol, table, start_str, end_str),
                                 start_str, end_str)
            kwargs = {}
            if provider.name == "finnhub" and finnhub_sources is not None:
                kwargs["sources"] = finnhub_sources
            try:
                fetched = provider.fetch([symbol], start, end, **kwargs)
            except Exception as e:
                # A missing API key must not abort the whole run: Finnhub is
                # optional if OpenBB is selected, and vice versa.
                print(f"  {symbol}: {provider.name} unavailable ({e})")
                self.warnings.append(f"{symbol}: {provider.name} news failed ({e})")
                stats.failed += 1
                continue
            if not fetched:
                print(f"  {symbol}: no articles from {provider.name}")
                stats.failed += 1
            items.extend(fetched)

        stats.fetched = len(items)
        items = self._drop_duplicates(items)
        fresh = self._drop_already_stored(items, table)
        stats.new = len(fresh)

        if analyze and fresh:
            print(f"Analyzing {provider.name} sentiment (FinBERT) on "
                  f"{len(fresh)} new article(s)...")
            for item in fresh:
                result = self.scorer.score(item.headline)
                item.sentiment_label = result.label
                item.confidence = result.confidence
                item.finbert_score = result.score
                stats.scored += 1
        elif items and not fresh:
            print(f"  all {len(items)} {provider.name} articles already in DB, "
                  f"nothing to score")

        if fresh:
            stats.saved = self.repository.save_news(fresh, table=table)
        print(f"Saved {stats.saved} new {provider.name} news articles "
              f"({stats.fetched} fetched, {stats.fetched - stats.new} already known)")
        return stats

    @staticmethod
    def _drop_duplicates(items: List[NewsItem]) -> List[NewsItem]:
        """Remove repeats inside a single fetch batch."""
        seen: Set[str] = set()
        out: List[NewsItem] = []
        for item in items:
            key = news_key(item)
            if key in seen:
                continue
            seen.add(key)
            out.append(item)
        return out

    def _drop_already_stored(self, items: List[NewsItem], table: str) -> List[NewsItem]:
        """Keep only articles whose URL is not already stored for that symbol."""
        by_symbol: Dict[str, List[NewsItem]] = {}
        for item in items:
            by_symbol.setdefault(item.symbol, []).append(item)

        fresh: List[NewsItem] = []
        for symbol, group in by_symbol.items():
            known = self.repository.existing_urls(
                symbol, table, [i.url for i in group if i.url]
            )
            fresh.extend(i for i in group if not i.url or i.url not in known)
        return fresh

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
            symbol_bars = self.price_provider.fetch(symbol, start, end)
            if not symbol_bars:
                # Without prices a symbol stays invisible in the Analyse tab,
                # so this must be reported rather than buried in a print().
                stats.failed += 1
                message = (f"{symbol}: no price data for {start_str} -> {end_str} "
                           f"(all OpenBB price providers returned nothing)")
                print(f"  Warning: {message}")
                self.warnings.append(message)
            bars.extend(symbol_bars)

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
        self.warnings.clear()
        results = self.fetch_news(
            symbols=symbols, start=start, end=end,
            sources=sources, finnhub_sources=finnhub_sources,
            force_refresh=force_refresh, analyze=analyze,
        )
        results["prices"] = self.fetch_prices(
            symbols=symbols, start=start, end=end, force_refresh=force_refresh,
        )
        return results
