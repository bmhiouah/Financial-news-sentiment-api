#!/usr/bin/env python3
import argparse
import sqlite3
from datetime import datetime

from provider import get_news, get_prices
from database import init_db, save_news, save_prices, DB_PATH
from analyzer import score as finbert_score


def _covered(symbol, table, start, end):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        f"SELECT MIN(date), MAX(date) FROM {table} WHERE symbol = ? AND date IS NOT NULL",
        (symbol,),
    )
    row = cur.fetchone()
    conn.close()
    return row and row[0] and row[1] and row[0] <= start and row[1] >= end


def main():
    parser = argparse.ArgumentParser(description="Fetch financial news and prices")
    parser.add_argument("--symbols", nargs="+", required=True)
    parser.add_argument("--start-date", type=str, required=True)
    parser.add_argument("--end-date", type=str, required=True)
    parser.add_argument("--analyze", action="store_true")
    args = parser.parse_args()

    start = args.start_date
    end = args.end_date
    init_db()

    print("Fetching news...")
    news = []
    for s in args.symbols:
        if _covered(s, "news", start, end):
            print(f"  {s}: already in DB, skipping")
            continue
        news.extend(get_news([s], datetime.strptime(start, "%Y-%m-%d"), datetime.strptime(end, "%Y-%m-%d")))

    if args.analyze:
        print("Analyzing sentiment...")
        sentiments = {}
        for i in news:
            score, label = finbert_score(i.get("headline", ""))
            sentiments[i["url"]] = (label, score, score)
        save_news(news, sentiments=sentiments)
    else:
        save_news(news)
    print(f"Saved {len(news)} news articles")

    print("Fetching prices...")
    prices = []
    for s in args.symbols:
        if _covered(s, "prices", start, end):
            print(f"  {s}: already in DB, skipping")
            continue
        prices.extend(get_prices(s, datetime.strptime(start, "%Y-%m-%d"), datetime.strptime(end, "%Y-%m-%d")))
    save_prices(prices)
    print(f"Saved {len(prices)} price records")


if __name__ == "__main__":
    main()
