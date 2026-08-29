"""OpenBB-backed providers for news and historical prices."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from openbb import obb

from ..domain import NewsItem, PriceBar, SOURCE_OPENBB
from .base import NewsProvider, PriceProvider


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _get_attr(obj: Any, *keys: str, default=None):
    """Read a value from a dict or attribute, trying each key in order."""
    for k in keys:
        if isinstance(obj, dict):
            if k in obj and obj[k] is not None:
                return obj[k]
        else:
            v = getattr(obj, k, None)
            if v is not None:
                return v
    return default


def _normalize_news_item(raw: Any, symbol: str) -> Optional[NewsItem]:
    """Turn a raw OpenBB news result into a NewsItem, filtering by symbol."""
    raw_symbols = _get_attr(raw, "symbols", default=[])
    if isinstance(raw_symbols, str):
        raw_symbols = [s.strip() for s in raw_symbols.split(",") if s.strip()]
    if symbol.upper() not in {s.upper() for s in (raw_symbols or [])}:
        return None
    return NewsItem(
        symbol=symbol,
        date=_coerce_iso(_get_attr(raw, "date", "published")),
        headline=_get_attr(raw, "title", "headline", default=""),
        text=_get_attr(raw, "text", "body", "content", default=""),
        source=_get_attr(raw, "source", "source_name", default=SOURCE_OPENBB),
        url=_get_attr(raw, "url", default=""),
    )


def _coerce_iso(value) -> str:
    if value is None:
        return ""
    if hasattr(value, "date") and callable(value.date):
        try:
            return value.date().strftime("%Y-%m-%d")
        except Exception:
            pass
    return str(value)[:10]


def _price_rows_to_dicts(results) -> List[Dict[str, Any]]:
    if hasattr(results, "to_dict"):
        return results.to_dict(orient="records")
    out: List[Dict[str, Any]] = []
    for r in results or []:
        if isinstance(r, dict):
            out.append(r)
        else:
            out.append({
                "date": getattr(r, "date", None),
                "open": getattr(r, "open", None),
                "high": getattr(r, "high", None),
                "low": getattr(r, "low", None),
                "close": getattr(r, "close", None),
                "volume": getattr(r, "volume", None),
            })
    return out


def _compute_returns(bars: List[PriceBar]) -> List[PriceBar]:
    """Fill daily/weekly/monthly forward returns from close prices."""
    closes = [b.close for b in bars if b.close is not None]
    for i, bar in enumerate(bars):
        if bar.close is None:
            continue
        # Find the index of this bar within `closes`
        try:
            ci = closes.index(bar.close, sum(1 for b in bars[:i] if b.close is not None))
        except ValueError:
            continue
        if ci > 0 and closes[ci - 1]:
            bar.daily_return = (bar.close - closes[ci - 1]) / closes[ci - 1]
        if ci >= 7 and closes[ci - 7]:
            bar.weekly_return = (bar.close - closes[ci - 7]) / closes[ci - 7]
        if ci >= 30 and closes[ci - 30]:
            bar.monthly_return = (bar.close - closes[ci - 30]) / closes[ci - 30]
    return bars


# --------------------------------------------------------------------------- #
# Providers
# --------------------------------------------------------------------------- #

class OpenBBNewsProvider(NewsProvider):
    name = "openbb"

    def fetch(self, symbols: List[str], start: datetime, end: datetime,
              sources: Optional[List[str]] = None) -> List[NewsItem]:
        items: List[NewsItem] = []
        for symbol in symbols:
            try:
                response = obb.news.company(
                    symbol=[symbol],
                    start_date=start.strftime("%Y-%m-%d"),
                    end_date=end.strftime("%Y-%m-%d"),
                )
            except Exception as e:
                print(f"Warning: OpenBB news for {symbol} failed: {e}")
                continue
            for raw in getattr(response, "results", None) or []:
                item = _normalize_news_item(raw, symbol)
                if item is not None:
                    items.append(item)
        return items


class OpenBBPriceProvider(PriceProvider):
    name = "openbb"

    def fetch(self, symbol: str, start: datetime, end: datetime) -> List[PriceBar]:
        try:
            response = obb.equity.price.historical(
                symbol=symbol,
                start_date=start.strftime("%Y-%m-%d"),
                end_date=end.strftime("%Y-%m-%d"),
            )
        except Exception as e:
            print(f"Warning: OpenBB prices for {symbol} failed: {e}")
            return []

        rows = _price_rows_to_dicts(getattr(response, "results", None))
        bars: List[PriceBar] = []
        for row in rows:
            bars.append(PriceBar(
                symbol=symbol,
                date=_coerce_iso(row.get("date")),
                open=row.get("open"),
                high=row.get("high"),
                low=row.get("low"),
                close=row.get("close"),
                volume=row.get("volume"),
            ))
        bars.sort(key=lambda b: b.date)
        return _compute_returns(bars)
