import sqlite3
from datetime import datetime
from collections import defaultdict
import math

DB_PATH = "data/news.db"


def load_news():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT symbol, date, sentiment_label, confidence, finbert_score
        FROM news
        WHERE finbert_score IS NOT NULL
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def load_prices():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT symbol, date, close, daily_return, weekly_return, monthly_return
        FROM prices
        ORDER BY symbol, date
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def aggregate_daily_sentiment(news):
    daily = defaultdict(lambda: {"finbert": [], "count": 0})
    for item in news:
        date = item["date"]
        if item.get("finbert_score") is not None:
            daily[date]["finbert"].append(item["finbert_score"])
        daily[date]["count"] += 1
    return daily


def correlation(x, y):
    n = len(x)
    if n < 2:
        return None
    mean_x = sum(x) / n
    mean_y = sum(y) / n
    num = sum((xi - mean_x) * (yi - mean_y) for xi, yi in zip(x, y))
    den_x = math.sqrt(sum((xi - mean_x) ** 2 for xi in x))
    den_y = math.sqrt(sum((yi - mean_y) ** 2 for yi in y))
    if den_x == 0 or den_y == 0:
        return None
    return num / (den_x * den_y)


def analyze():
    news = load_news()
    prices = load_prices()
    if not news or not prices:
        print("Not enough data.")
        return

    daily_sentiment = aggregate_daily_sentiment(news)

    by_symbol = defaultdict(list)
    for p in prices:
        by_symbol[p["symbol"]].append(p)

    print("Correlation by symbol (ignoring sentiment_score == 0):")
    print(f"{'Symbol':<8} {'Daily':>10} {'Weekly':>10} {'Monthly':>10} {'N':>5}")
    print("-" * 45)

    for symbol, rows in by_symbol.items():
        rows.sort(key=lambda x: x["date"])
        daily_x, daily_y = [], []
        weekly_x, weekly_y = [], []
        monthly_x, monthly_y = [], []

        for row in rows:
            date = row["date"]
            s = daily_sentiment.get(date, {})
            scores = s.get("finbert", [])
            if not scores:
                continue
            avg_score = sum(scores) / len(scores)
            if avg_score == 0:
                continue

            if row.get("daily_return") is not None:
                daily_x.append(avg_score)
                daily_y.append(row["daily_return"])
            if row.get("weekly_return") is not None:
                weekly_x.append(avg_score)
                weekly_y.append(row["weekly_return"])
            if row.get("monthly_return") is not None:
                monthly_x.append(avg_score)
                monthly_y.append(row["monthly_return"])

        daily_corr = correlation(daily_x, daily_y)
        weekly_corr = correlation(weekly_x, weekly_y)
        monthly_corr = correlation(monthly_x, monthly_y)

        daily_str = f"{daily_corr:>10.3f}" if daily_corr is not None else "N/A"
        weekly_str = f"{weekly_corr:>10.3f}" if weekly_corr is not None else "N/A"
        monthly_str = f"{monthly_corr:>10.3f}" if monthly_corr is not None else "N/A"
        n = len(daily_x)

        print(f"{symbol:<8} {daily_str:>10} {weekly_str:>10} {monthly_str:>10} {n:>5}")


if __name__ == "__main__":
    analyze()
