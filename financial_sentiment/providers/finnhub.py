"""Finnhub-backed news provider.

Implements backward pagination: when a full page is returned, the next call
uses end-date = (oldest item date - 1 day) and refetches, until the page is
short or the user-requested start_date is reached.

Finnhub truncates a single `company_news` response to roughly 250 items and
returns the most recent ones, so walking the end date backwards is what makes
the older pages reachable at all.
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta
from typing import List, Optional, Sequence, Set

import finnhub
from openbb import obb

from ..config import SETTINGS
from ..domain import NewsItem, SOURCE_FINNHUB, news_key
from ..repository import FINNHUB_TABLE
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
    """Writes to a staging table; rows join `news` once they are scored."""

    name = "finnhub"
    table = FINNHUB_TABLE

    def __init__(self,
                 page_limit: Optional[int] = None,
                 max_pages: Optional[int] = None,
                 retry_attempts: int = 3) -> None:
        self.page_limit = page_limit or SETTINGS.finnhub_page_limit
        self.max_pages = max_pages or SETTINGS.finnhub_max_pages
        self.retry_attempts = retry_attempts

    # ---- internals ----

    def _call(self, client, symbol: str, start_str: str,
              window_end_str: str) -> Optional[List[dict]]:
        """One `company_news` page, retried on transient errors.

        Returns None when the page could not be read at all, so the caller can
        stop cleanly instead of treating a failure as "no older news exists".
        """
        for attempt in range(1, self.retry_attempts + 1):
            try:
                return client.company_news(
                    symbol, _from=start_str, to=window_end_str
                ) or []
            except Exception as e:
                if attempt >= self.retry_attempts:
                    print(f"Warning: Finnhub company_news({symbol}) failed: {e}")
                    return None
                # Free tier is rate limited to 60 calls/minute.
                time.sleep(2 * attempt)
        return None

    # ---- public API ----

    def fetch(self, symbols: List[str], start: datetime, end: datetime,
              publishers: Optional[Sequence[str]] = None) -> List[NewsItem]:
        client = _get_client()
        start_str = start.strftime("%Y-%m-%d")
        allowed: Optional[Set[str]] = (
            {p.upper() for p in publishers} if publishers else None
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

                items = self._call(client, symbol, start_str, window_end_str)
                if items is None:
                    break
                if not items:
                    break

                for raw in items:
                    item = _to_item(symbol, raw, window_end_str)
                    if item.date < start_str:
                        continue
                    if allowed and (item.source or "").upper() not in allowed:
                        continue
                    key = news_key(item)
                    if key in seen:
                        continue
                    seen.add(key)
                    out.append(item)

                # A short page means this window is fully drained.
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
                time.sleep(0.2)  # stay well clear of the rate limit

        out.sort(key=lambda i: (i.symbol, i.date), reverse=True)
        return out
