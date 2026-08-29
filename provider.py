from openbb import obb
from datetime import datetime
from typing import List, Dict, Any


def _item_symbols(item):
    if isinstance(item, dict):
        raw = item.get("symbols")
    else:
        raw = getattr(item, "symbols", None)
    if not raw:
        return []
    if isinstance(raw, str):
        return [s.strip() for s in raw.split(",") if s.strip()]
    return list(raw)


def get_news(symbols: List[str], start_date: datetime, end_date: datetime) -> List[Dict[str, Any]]:
    news = []
    for symbol in symbols:
        try:
            response = obb.news.company(
                symbol=[symbol],
                start_date=start_date.strftime("%Y-%m-%d"),
                end_date=end_date.strftime("%Y-%m-%d"),
            )
            for item in getattr(response, "results", None) or []:
                item_symbols = [s.upper() for s in _item_symbols(item)]
                if symbol.upper() not in item_symbols:
                    continue
                if isinstance(item, dict):
                    news.append({
                        "symbol": symbol,
                        "date": item.get("date") or item.get("published"),
                        "headline": item.get("title") or item.get("headline") or "",
                        "text": item.get("text") or item.get("body") or item.get("content") or "",
                        "source": item.get("source") or item.get("source_name") or "OpenBB",
                        "url": item.get("url") or "",
                    })
                else:
                    news.append({
                        "symbol": symbol,
                        "date": getattr(item, "date", None) or getattr(item, "published", None),
                        "headline": getattr(item, "title", "") or getattr(item, "headline", ""),
                        "text": getattr(item, "text", "") or getattr(item, "body", "") or getattr(item, "content", "") or "",
                        "source": getattr(item, "source", None) or getattr(item, "source_name", None) or "OpenBB",
                        "url": getattr(item, "url", "") or "",
                    })
        except Exception as e:
            print(f"Warning: could not fetch news for {symbol}: {e}")
    return news


def get_prices(symbol: str, start_date: datetime, end_date: datetime) -> List[Dict[str, Any]]:
    try:
        response = obb.equity.price.historical(
            symbol=symbol,
            start_date=start_date.strftime("%Y-%m-%d"),
            end_date=end_date.strftime("%Y-%m-%d"),
        )
        results = getattr(response, "results", None)
        if not results:
            return []

        prices = []
        rows = []
        if hasattr(results, "to_dict"):
            rows = results.to_dict(orient="records")
        else:
            for item in results:
                if isinstance(item, dict):
                    rows.append(item)
                else:
                    rows.append({
                        "date": getattr(item, "date", None),
                        "open": getattr(item, "open", None),
                        "high": getattr(item, "high", None),
                        "low": getattr(item, "low", None),
                        "close": getattr(item, "close", None),
                        "volume": getattr(item, "volume", None),
                    })

        from datetime import datetime as dt
        parsed = []
        for row in rows:
            date_val = row.get("date")
            if hasattr(date_val, "date"):
                date_val = date_val.date()
            elif isinstance(date_val, str):
                date_val = dt.strptime(date_val[:10], "%Y-%m-%d").date()
            parsed.append({
                "symbol": symbol,
                "date": date_val,
                "open": row.get("open"),
                "high": row.get("high"),
                "low": row.get("low"),
                "close": row.get("close"),
                "volume": row.get("volume"),
            })

        parsed.sort(key=lambda x: x["date"])
        close_by_date = {r["date"]: r["close"] for r in parsed if r["date"] and r["close"] is not None}
        dates = sorted(close_by_date.keys())

        for r in parsed:
            d = r["date"]
            daily = weekly = monthly = None
            if d in close_by_date:
                idx = dates.index(d)
                if idx > 0:
                    prev = close_by_date[dates[idx - 1]]
                    if prev:
                        daily = (close_by_date[d] - prev) / prev
                if idx >= 7:
                    prev = close_by_date[dates[idx - 7]]
                    if prev:
                        weekly = (close_by_date[d] - prev) / prev
                if idx >= 30:
                    prev = close_by_date[dates[idx - 30]]
                    if prev:
                        monthly = (close_by_date[d] - prev) / prev
            r["daily_return"] = daily
            r["weekly_return"] = weekly
            r["monthly_return"] = monthly
            prices.append(r)

        return prices
    except Exception as e:
        print(f"Warning: could not fetch prices for {symbol}: {e}")
        return []
