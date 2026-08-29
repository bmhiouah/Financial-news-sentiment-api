"""Finnhub-backed news provider.

Implements backward pagination: when a full page is returned, the next call
uses end-date = (oldest item date - 1 day) and refetches, until the page is
short or the user-requested start_date is reached.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import List, Optional, Set

import finnhub
from openbb import obb

from ..config import SETTINGS
from ..domain import NewsItem, SOURCE_FINNHUB
from .base import NewsProvider


def _get_client() -> finnhub.Client:
    secret = obb.user.credentials.finnhub_api_key
    api_key = (
        secret.get_secret_value() if hasattr(secret, "get_secret_value") else secret
    )
    if not api_key:
        raise ValueError("No Finnhub API key found in OpenBB credentials.")
    return finnhub.Client(api_key=api_key)


def _to_item(symbol: str, raw: dict, fallback_date: str) -> NewsItem:
    ts = raw.get("datetime")
    date = (
        datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d") if ts else fallback_date
    )
    return NewsItem(
        symbol=symbol,
        date=date,
        headline=raw.get("headline", ""),
        text=raw.get("summary", ""),
        source=raw.get("source", SOURCE_FINNHUB),
        url=raw.get("url", ""),
    )


class FinnhubNewsProvider(NewsProvider):
    name = "finnhub"

    def __init__(self, page_limit: Optional[int] = None,
                 max_pages: int = 20) -> None:
        self.page_limit = page_limit or SETTINGS.finnhub_page_limit
        self.max_pages = max_pages

    def fetch(self, symbols: List[str], start: datetime, end: datetime,
              sources: Optional[List[str]] = None) -> List[NewsItem]:
        client = _get_client()
        start_str = start.strftime("%Y-%m-%d")
        allowed: Optional[Set[str]] = (
            {s.upper() for s in sources} if sources else None
        )

        out: List[NewsItem] = []
        for raw_symbol in symbols:
            symbol = raw_symbol.upper()
            window_end = end
            seen: Set[str] = set()
            for _ in range(self.max_pages):
                if window_end.date() < start.date():
                    break
                window_end_str = window_end.strftime("%Y-%m-%d")
                try:
                    items = client.company_news(
                        symbol, _from=start_str, to=window_end_str
                    )
                except Exception as e:
                    print(f"Warning: Finnhub company_news({symbol}) failed: {e}")
                    break
                items = items or []
                if not items:
                    break

                for raw in items:
                    item = _to_item(symbol, raw, window_end_str)
                    if not item.url or item.url in seen:
                        continue
                    if allowed and item.source.upper() not in allowed:
                        continue
                    if item.date < start_str:
                        continue
                    seen.add(item.url)
                    out.append(item)

                if len(items) < self.page_limit:
                    break

                oldest_ts = min(
                    (r.get("datetime") for r in items if r.get("datetime")),
                    default=None,
                )
                if not oldest_ts:
                    break
                oldest_date = datetime.utcfromtimestamp(oldest_ts).date()
                window_end = datetime.combine(
                    oldest_date, datetime.min.time()
                ) - timedelta(days=1)

        out.sort(key=lambda i: (i.symbol, i.date), reverse=True)
        return out
