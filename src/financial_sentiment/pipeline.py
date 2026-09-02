"""Pipeline orchestrator: fetch news + prices, score sentiment, persist.

The single object the CLI and the API drive. It owns a `Repository`, a list of
`NewsProvider`s, one `PriceProvider` and one `SentimentScorer`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Sequence, Set

from .domain import NewsItem, PriceBar, news_key
from .providers import (
    FinnhubNewsProvider,
    NewsProvider,
    OpenBBNewsProvider,
    OpenBBPriceProvider,
    PriceProvider,
)
from .repository import NEWS_TABLE, PRICES_TABLE, Repository
from .sentiment import FinBERTScorer, SentimentScorer


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

    @classmethod
    def default(cls,
                repository: Optional[Repository] = None,
                scorer: Optional[SentimentScorer] = None) -> "Pipeline":
        return cls(
            repository=repository or Repository(),
            news_providers=[OpenBBNewsProvider(), FinnhubNewsProvider()],
            price_provider=OpenBBPriceProvider(),
            scorer=scorer or FinBERTScorer(),
        )

    # ---- news ----

    def _run_news_provider(self, provider: NewsProvider,
                           symbols: Sequence[str], start: datetime, end: datetime,
                           analyze: bool,
                           publishers: Optional[Sequence[str]] = None,
                           ) -> FetchStats:
        """Fetch news for every symbol and store whatever is not there yet.

        News is always re-fetched (there is no reliable way to know a provider
        gave us everything last time) and de-duplicated against the database
        before scoring, so a repeat run costs API calls but no FinBERT work.
        """
        table = provider.table
        stats = FetchStats(requested=len(symbols))
        print(f"{provider.name} news:")
        items: List[NewsItem] = []
        for symbol in symbols:
            self._log_coverage(symbol, table, start, end)
            try:
                fetched = provider.fetch([symbol], start, end, publishers=publishers)
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
        fresh = self._drop_known(_drop_duplicates(items), table)
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

    def _drop_known(self, items: List[NewsItem], table: str) -> List[NewsItem]:
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
                   finnhub_sources: Optional[Sequence[str]] = None,
                   analyze: bool = True) -> Dict[str, FetchStats]:
        """Fetch from every configured provider named in `sources`.

        `finnhub_sources` restricts Finnhub by publisher; other providers ignore it.
        """
        results: Dict[str, FetchStats] = {}
        for provider in self.news_providers:
            if provider.name not in sources:
                continue
            publishers = finnhub_sources if provider.name == "finnhub" else None
            stats = self._run_news_provider(
                provider, symbols=symbols, start=start, end=end,
                analyze=analyze, publishers=publishers,
            )
            # Providers writing to a staging table must be promoted into `news`.
            if provider.table != NEWS_TABLE:
                stats.promoted, extra_scored = self._promote(provider.table, analyze)
                stats.scored += extra_scored
            results[provider.name] = stats
        return results

    def _promote(self, table: str, analyze: bool) -> tuple:
        """Move staged rows from `table` into `news`; returns (promoted, scored)."""
        promoted = self.repository.promote_finnhub_to_news()
        print(f"Promoted {promoted} Finnhub headlines into the main news table")
        if not analyze:
            return promoted, 0
        # Rows staged before FinBERT ran still have a NULL score; fill them in and
        # promote a second time to carry the fresh sentiment across.
        scored = self._score_unscored(table)
        if not scored:
            return promoted, 0
        print(f"Scored {scored} previously unscored Finnhub rows")
        extra = self.repository.promote_finnhub_to_news()
        print(f"Promoted {extra} additional rows after scoring")
        return promoted + extra, scored

    def _score_unscored(self, table: str) -> int:
        pending = self.repository.fetch_unscored_news(table=table)
        for item in pending:
            result = self.scorer.score(item.headline)
            item.sentiment_label = result.label
            item.confidence = result.confidence
            item.finbert_score = result.score
        return self.repository.update_sentiment(pending, table=table)

    # ---- prices ----

    def fetch_prices(self, symbols: Sequence[str], start: datetime, end: datetime,
                     force_refresh: bool = False) -> FetchStats:
        stats = FetchStats(requested=len(symbols))
        bars: List[PriceBar] = []
        start_str, end_str = start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")

        print("Prices:")
        for symbol in symbols:
            coverage = self.repository.coverage(symbol, PRICES_TABLE, start_str, end_str)
            covers_window = (coverage.min_date is not None
                             and coverage.min_date <= start_str
                             and coverage.max_date >= end_str)
            if not force_refresh and covers_window:
                print(f"  {symbol}: already in DB ({coverage.n_rows} rows, "
                      f"{coverage.min_date} -> {coverage.max_date}), skipping API call")
                stats.skipped += 1
                continue

            print(f"  {symbol}: fetching")
            symbol_bars = self.price_provider.fetch(symbol, start, end)
            if not symbol_bars:
                # Without prices a symbol stays invisible in the Analyse tab, so
                # this must be reported rather than buried in a print().
                stats.failed += 1
                message = (f"{symbol}: no price data for {start_str} -> {end_str} "
                           f"(every OpenBB price provider returned nothing)")
                print(f"  Warning: {message}")
                self.warnings.append(message)
            bars.extend(symbol_bars)

        if bars:
            stats.saved = self.repository.save_prices(bars)
        stats.fetched = len(bars)
        print(f"Saved {len(bars)} price records")
        return stats

    # ---- coverage reporting ----

    def _log_coverage(self, symbol: str, table: str,
                      start: datetime, end: datetime) -> None:
        coverage = self.repository.coverage(
            symbol, table, start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")
        )
        if coverage.is_empty:
            print(f"  {symbol}: not in DB, fetching")
        else:
            # News is re-fetched every run (providers never guarantee they
            # returned everything), so this is informational only.
            print(f"  {symbol}: already in DB ({coverage.n_rows} rows, "
                  f"{coverage.min_date} -> {coverage.max_date}), re-checking")

    # ---- end-to-end ----

    def run(self, symbols: Sequence[str], start: datetime, end: datetime,
            sources: Sequence[str] = ("openbb", "finnhub"),
            finnhub_sources: Optional[Sequence[str]] = None,
            force_refresh: bool = False,
            analyze: bool = True) -> Dict[str, FetchStats]:
        self.repository.init()
        self.warnings.clear()
        results = self.fetch_news(
            symbols=symbols, start=start, end=end,
            sources=sources, finnhub_sources=finnhub_sources, analyze=analyze,
        )
        results["prices"] = self.fetch_prices(
            symbols=symbols, start=start, end=end, force_refresh=force_refresh,
        )
        return results


def _drop_duplicates(items: List[NewsItem]) -> List[NewsItem]:
    """Remove repeats inside a single fetch batch."""
    seen: Set[str] = set()
    out: List[NewsItem] = []
    for item in items:
        key = news_key(item)
        if key not in seen:
            seen.add(key)
            out.append(item)
    return out
