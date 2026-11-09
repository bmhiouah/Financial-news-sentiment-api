# Database

PostgreSQL is the only backend. The app needs nothing but a connection string,
so it works against a local instance, Docker or a managed service. Set
`DATABASE_URL` in `.env` (see [Configuration](configuration.md)).

Under Docker the database comes from the `db` service. For local work without
Docker, `scripts/pg_server.py` manages a bundled instance:

```bash
python scripts/pg_server.py start     # prints the DATABASE_URL to put in .env
python scripts/pg_server.py status
python scripts/pg_server.py stop
python scripts/pg_server.py psql "SELECT count(*) FROM news;"
```

The schema is created on startup (`Repository.init()` is idempotent) and every
write is an upsert, so restarts and re-runs never clobber data.

## Schema

| Table | Contents |
|---|---|
| `news` | the articles that everything else reads |
| `finnhub_news` | staging table; rows join `news` once scored |
| `prices` | daily OHLCV + forward daily/weekly/monthly returns |
| `equities` | ticker universe used for symbol lookup |

`news` and `finnhub_news` share one schema: `symbol`, `date`, `headline`, `text`,
`source`, `url`, `sentiment_label`, `confidence`, `finbert_score`, and the five
`llm_*` columns. Deduplication relies on unique indexes on `(symbol, url)` for
news and `(symbol, date)` for prices.

## Forward returns, not backward

The `prices` table stores **forward** returns:

```
return[t] = (close[t + h] - close[t]) / close[t]      h = 1, 7, 30 calendar days
```

The whole point of the project is to ask whether news on date `t` says something
about what the market does *after* `t`. A backward return
(`close[t] - close[t-1]`) would instead compare news against a move that had
already happened, which manufactures correlation that is not predictive.

`t + h` resolves to the first trading day on or after that calendar date, so
weekends and holidays land on the next session. Bars with no bar far enough in
the future keep `NULL` returns — their future has not happened yet, and filling
it in would be look-ahead bias.

Returns are derived data, so they are recomputed from the stored closes rather
than edited by hand:

```bash
python scripts/recompute_returns.py            # every symbol
python scripts/recompute_returns.py AAPL MSFT  # only these
```
