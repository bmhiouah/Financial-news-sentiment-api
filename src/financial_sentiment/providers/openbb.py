"""OpenBB-backed providers for news and historical prices."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence

from openbb import obb

from ..config import SETTINGS
from ..domain import NewsItem, PriceBar, SOURCE_OPENBB, coerce_date
from .base import NewsProvider, PriceProvider

#: Entry meaning "let OpenBB apply its own provider priority order".
DEFAULT_PROVIDER = ""


def _provider_kwargs(name: str) -> Dict[str, Any]:
    """Build the `provider=` kwarg, or none at all for the OpenBB default."""
    return {} if name == DEFAULT_PROVIDER else {"provider": name}


def _provider_label(name: str) -> str:
    return "openbb-default" if name == DEFAULT_PROVIDER else name


def _get_attr(obj: Any, *keys: str, default=None):
    """Read a value from a dict or an object, trying each key in order."""
    for key in keys:
        if isinstance(obj, dict):
            if obj.get(key) is not None:
                return obj[key]
        elif getattr(obj, key, None) is not None:
            return getattr(obj, key)
    return default


def _price_rows(results: Any) -> List[Any]:
    """Normalise an OpenBB price result into a list of rows.

    Depending on the provider, `results` is a DataFrame, a list of dicts, or a
    list of provider-specific model objects (e.g. `FMPEquityHistoricalData`).
    `_get_attr` reads all three, so only the DataFrame needs converting.
    """
    if results is None:
        return []
    if hasattr(results, "to_dict"):
        return results.to_dict(orient="records")
    return list(results)


def _to_news_item(raw: Any, symbol: str) -> Optional[NewsItem]:
    """Turn a raw OpenBB news result into a NewsItem, filtered by symbol.

    Items carrying no symbol list at all are kept: the query was already scoped
    to `symbol`, so dropping them would throw away valid coverage.
    """
    raw_symbols = _get_attr(raw, "symbols", default=[])
    if isinstance(raw_symbols, str):
        raw_symbols = [s.strip() for s in raw_symbols.split(",") if s.strip()]
    raw_symbols = [s for s in (raw_symbols or []) if s]
    if raw_symbols and symbol.upper() not in {s.upper() for s in raw_symbols}:
        return None
    return NewsItem(
        symbol=symbol,
        date=coerce_date(_get_attr(raw, "date", "published")),
        headline=_get_attr(raw, "title", "headline", default=""),
        text=_get_attr(raw, "text", "body", "content", default=""),
        source=_get_attr(raw, "source", "source_name", default=SOURCE_OPENBB),
        url=_get_attr(raw, "url", default=""),
    )


def _add_returns(bars: List[PriceBar]) -> List[PriceBar]:
    """Fill daily/weekly/monthly returns from the ordered close prices."""
    # `bars` is chronologically sorted, so positional lookups are the lags.
    priced = [b for b in bars if b.close]
    closes = [b.close for b in priced]
    for index, bar in enumerate(priced):
        for field, lag in (("daily_return", 1), ("weekly_return", 7),
                           ("monthly_return", 30)):
            if index < lag:
                continue
            previous = closes[index - lag]
            if previous:
                setattr(bar, field, (bar.close - previous) / previous)
    return bars


class OpenBBNewsProvider(NewsProvider):
    """Tries each configured OpenBB news provider; the first with data wins."""

    name = "openbb"

    def __init__(self, providers: Optional[Sequence[str]] = None) -> None:
        self.providers = tuple(providers) if providers is not None else SETTINGS.news_providers

    def fetch(self, symbols: List[str], start: datetime, end: datetime,
              publishers: Optional[Sequence[str]] = None) -> List[NewsItem]:
        items: List[NewsItem] = []
        for symbol in symbols:
            items.extend(self._fetch_one(symbol, start, end))
        return items

    def _fetch_one(self, symbol: str, start: datetime, end: datetime) -> List[NewsItem]:
        errors: List[str] = []
        for provider in self.providers:
            try:
                response = obb.news.company(
                    symbol=[symbol],
                    start_date=start.strftime("%Y-%m-%d"),
                    end_date=end.strftime("%Y-%m-%d"),
                    **_provider_kwargs(provider),
                )
            except Exception as e:
                errors.append(f"{_provider_label(provider)}: {_short(e)}")
                continue

            found = [
                item
                for raw in getattr(response, "results", None) or []
                if (item := _to_news_item(raw, symbol)) is not None
            ]
            if found:
                return found
            errors.append(f"{_provider_label(provider)}: no articles")

        if errors:
            print(f"Warning: OpenBB news for {symbol} unavailable "
                  f"({' ; '.join(errors)})")
        return []


class OpenBBPriceProvider(PriceProvider):
    """Tries each configured OpenBB price provider; the first with data wins.

    Free FMP keys reject a lot of tickers with HTTP 402. Falling through to
    yfinance (no key required) keeps those symbols usable instead of leaving
    them with news but no prices, which hides them from the Analyse tab.
    """

    name = "openbb"

    def __init__(self, providers: Optional[Sequence[str]] = None) -> None:
        self.providers = tuple(providers) if providers is not None else SETTINGS.price_providers

    def fetch(self, symbol: str, start: datetime, end: datetime) -> List[PriceBar]:
        errors: List[str] = []
        for provider in self.providers:
            try:
                response = obb.equity.price.historical(
                    symbol=symbol,
                    start_date=start.strftime("%Y-%m-%d"),
                    end_date=end.strftime("%Y-%m-%d"),
                    **_provider_kwargs(provider),
                )
            except Exception as e:
                errors.append(f"{_provider_label(provider)}: {_short(e)}")
                continue

            bars = self._to_bars(symbol, response)
            if bars:
                if provider != DEFAULT_PROVIDER and self.providers[0] != provider:
                    print(f"  {symbol}: prices via OpenBB provider "
                          f"'{provider}' ({len(bars)} bars)")
                return bars
            errors.append(f"{_provider_label(provider)}: no bars")

        if errors:
            print(f"Warning: OpenBB prices for {symbol} failed on every provider "
                  f"({' ; '.join(errors)})")
        return []

    @staticmethod
    def _to_bars(symbol: str, response: Any) -> List[PriceBar]:
        bars = [
            PriceBar(
                symbol=symbol,
                date=coerce_date(_get_attr(row, "date")),
                open=_get_attr(row, "open"),
                high=_get_attr(row, "high"),
                low=_get_attr(row, "low"),
                close=_get_attr(row, "close"),
                volume=_get_attr(row, "volume"),
            )
            for row in _price_rows(getattr(response, "results", None))
        ]
        bars.sort(key=lambda b: b.date)
        return _add_returns(bars)


def _short(err: Exception, limit: int = 140) -> str:
    """One-line, squashed error text for warning messages."""
    text = " ".join(str(err).split())
    return text if len(text) <= limit else text[: limit - 1] + "…"
