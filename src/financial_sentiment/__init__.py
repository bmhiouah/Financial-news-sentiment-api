"""Public API for the financial_sentiment package.

The recommended entry point is `Pipeline.default().run(...)`. The legacy
free-function names (`init_db`, `save_news`, `get_news`, `finbert_score`,
`correlation`, ...) are re-exported as thin adapters for backward
compatibility with the original notebook and scripts.
"""
from .config import (
    DB_PATH,
    FINBERT_MODEL,
    NEGATIVE_THRESHOLD,
    POSITIVE_THRESHOLD,
    SETTINGS,
    VLLM_ENDPOINT,
)
from .domain import (
    Coverage,
    NEGATIVE,
    NEUTRAL,
    NewsItem,
    POSITIVE,
    PriceBar,
    SentimentResult,
)
from .analysis import (
    CorrelationAnalyzer,
    CorrelationRow,
    daily_mean_sentiment,
    pearson,
)
from .pipeline import FetchStats, Pipeline
from .providers import (
    FinnhubNewsProvider,
    NewsProvider,
    OpenBBNewsProvider,
    OpenBBPriceProvider,
    PriceProvider,
)
from .repository import Repository
from .sentiment import FinBERTScorer, SentimentScorer, VLLMScorer
from .strategy import (  # noqa: E402
    Backtester,
    DataLoader,
    InsufficientSignalsError,
    MarketDataPoint,
    Portfolio,
    SentimentThresholdStrategy,
    Side,
    Trade,
)

# --------------------------------------------------------------------------- #
# Backward-compatible free functions
# --------------------------------------------------------------------------- #

_repository = Repository


def init_db() -> None:
    _repository().init()


def save_news(items, sentiments=None, table: str = "news") -> int:
    news_items = [_to_news_item(i) for i in items]
    if sentiments:
        for item in news_items:
            s = sentiments.get(item.url)
            if s:
                item.sentiment_label, item.confidence, item.finbert_score = s
    return _repository().save_news(news_items, table=table)


def save_finnhub_news(items, sentiments=None) -> int:
    return save_news(items, sentiments=sentiments, table="finnhub_news")


def save_prices(items) -> int:
    return _repository().save_prices([_to_price_bar(p) for p in items])


def update_sentiment(url, sentiment_label, finbert_score, confidence=None) -> None:
    _repository().update_sentiment(url, sentiment_label, finbert_score, confidence)


def promote_finnhub_to_news(symbol=None) -> int:
    return _repository().promote_finnhub_to_news(symbol=symbol)


def score_finnhub_pending() -> int:
    pipeline = Pipeline.default()
    pending = _repository().fetch_pending_finnhub()
    for item in pending:
        result = pipeline.scorer.score(item.headline)
        item.sentiment_label = result.label
        item.confidence = result.confidence
        item.finbert_score = result.score
    return _repository().score_pending_finnhub(pending)


def get_news(symbols, start_date, end_date):
    items = OpenBBNewsProvider().fetch(list(symbols), start_date, end_date)
    return [_item_to_dict(i) for i in items]


def get_prices(symbol, start_date, end_date):
    bars = OpenBBPriceProvider().fetch(symbol, start_date, end_date)
    return [_bar_to_dict(b) for b in bars]


def get_company_news(symbols, start_date, end_date, sources=None):
    items = FinnhubNewsProvider().fetch(
        list(symbols), start_date, end_date, sources=sources
    )
    return [_item_to_dict(i) for i in items]


def get_general_news(category: str = "general", sources=None):
    from .providers.finnhub import _get_client  # noqa: WPS437
    from datetime import datetime as _dt

    client = _get_client()
    try:
        items = client.general_news(category, min_id=0)
    except Exception as e:
        print(f"Warning: could not fetch Finnhub general news: {e}")
        return []
    out = []
    for raw in items or []:
        ts = raw.get("datetime")
        date = _dt.utcfromtimestamp(ts).strftime("%Y-%m-%d") if ts else ""
        out.append({
            "date": date,
            "headline": raw.get("headline", ""),
            "text": raw.get("summary", ""),
            "source": raw.get("source", "Finnhub"),
            "url": raw.get("url", ""),
        })
    if sources:
        allowed = {s.upper() for s in sources}
        out = [n for n in out if n["source"].upper() in allowed]
    return out


def finbert_score(text: str):
    """Legacy tuple-returning FinBERT scorer."""
    result = FinBERTScorer().score(text)
    return result.score, result.label


def vllm_score(text: str, endpoint: str = None):
    result = VLLMScorer(endpoint=endpoint).score(text)
    return result.score, result.label


def load_news():
    return [_item_to_dict(i) for i in _repository().fetch_news(with_sentiment_only=True)]


def load_prices():
    return [_bar_to_dict(b) for b in _repository().fetch_prices()]


def aggregate_daily_sentiment(news):
    from collections import defaultdict as _dd
    by_date: dict = _dd(lambda: {"finbert": [], "count": 0})
    for item in news:
        d = item["date"]
        if item.get("finbert_score") is not None:
            by_date[d]["finbert"].append(item["finbert_score"])
        by_date[d]["count"] += 1
    return by_date


def correlation(x, y):
    return pearson(list(x), list(y))


def analyze():
    CorrelationAnalyzer(_repository()).print_table()


# --------------------------------------------------------------------------- #
# Adapter helpers
# --------------------------------------------------------------------------- #

def _to_news_item(d):
    if isinstance(d, NewsItem):
        return d
    return NewsItem.from_dict(d)


def _to_price_bar(d):
    if isinstance(d, PriceBar):
        return d
    return PriceBar.from_dict(d)


def _item_to_dict(i: NewsItem) -> dict:
    return {
        "symbol": i.symbol,
        "date": i.date,
        "headline": i.headline,
        "text": i.text,
        "source": i.source,
        "url": i.url,
        "sentiment_label": i.sentiment_label,
        "confidence": i.confidence,
        "finbert_score": i.finbert_score,
    }


def _bar_to_dict(b: PriceBar) -> dict:
    return {
        "symbol": b.symbol,
        "date": b.date,
        "open": b.open,
        "high": b.high,
        "low": b.low,
        "close": b.close,
        "volume": b.volume,
        "daily_return": b.daily_return,
        "weekly_return": b.weekly_return,
        "monthly_return": b.monthly_return,
    }


__all__ = [
    # Settings
    "DB_PATH", "FINBERT_MODEL", "VLLM_ENDPOINT",
    "POSITIVE_THRESHOLD", "NEGATIVE_THRESHOLD", "SETTINGS",
    # Domain
    "NewsItem", "PriceBar", "Coverage", "SentimentResult",
    "POSITIVE", "NEGATIVE", "NEUTRAL",
    # Repository
    "Repository",
    # Providers
    "NewsProvider", "PriceProvider",
    "OpenBBNewsProvider", "OpenBBPriceProvider", "FinnhubNewsProvider",
    # Scorers
    "SentimentScorer", "FinBERTScorer", "VLLMScorer",
    # Analysis
    "CorrelationAnalyzer", "CorrelationRow", "daily_mean_sentiment", "pearson",
    # Strategy / Backtester
    "Side", "Trade", "Portfolio", "SentimentThresholdStrategy",
    "DataLoader", "MarketDataPoint",
    "Backtester", "InsufficientSignalsError",
    # Pipeline
    "Pipeline", "FetchStats",
    # Legacy free functions
    "init_db", "save_news", "save_prices", "save_finnhub_news",
    "update_sentiment", "promote_finnhub_to_news", "score_finnhub_pending",
    "get_news", "get_prices", "get_company_news", "get_general_news",
    "finbert_score", "vllm_score",
    "load_news", "load_prices", "aggregate_daily_sentiment",
    "correlation", "analyze",
]
