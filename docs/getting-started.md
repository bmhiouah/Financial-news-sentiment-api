# Getting started

Two supported setups: Docker Compose (recommended) or a local Python environment
with the bundled PostgreSQL server.

## Docker

```bash
cp config/env.example .env        # optional: add GROQ_API_KEY
docker compose up --build         # foreground
docker compose up -d --build      # detached
```

Open `http://127.0.0.1:8000/` for the UI and `http://127.0.0.1:8000/docs` for the
interactive OpenAPI docs. The database schema is created on startup, so there is
no migration step. See [Docker](docker.md) for the full command reference and
image details.

## Local (no Docker)

```bash
pip install -r config/requirements.txt
pip install -r config/requirements-dev.txt   # adds the bundled local PostgreSQL

cp config/env.example .env
python scripts/pg_server.py start            # prints the DATABASE_URL to put in .env
python scripts/pg_server.py status
```

If a PostgreSQL instance is already running, skip the bundled server and point
`DATABASE_URL` in `.env` at it. See [Database](database.md) for the connection
string and schema.

Then fetch, score and explore:

```bash
python scripts/main.py --symbols AAPL MSFT --start-date 2026-07-01 --end-date 2026-08-28 --analyze
python scripts/run_api.py          # http://127.0.0.1:8000
python -m financial_sentiment.analysis
```

## What a run does

1. Fetch prices and news for the requested symbols and date window.
2. De-duplicate headlines by URL before scoring.
3. Score each new headline with FinBERT (and optionally a Groq LLM).
4. Upsert everything into PostgreSQL.
5. Expose the stored data through the analysis endpoints and the web UI.

Every write is an upsert, so restarts and re-runs never clobber data. See
[Architecture](architecture.md) for the module layout and
[CLI](cli.md) for all command flags.

## Next steps

- [Configuration](configuration.md) — environment variables and provider order.
- [Sentiment scoring](sentiment.md) — FinBERT and the optional LLM backfill.
- [Backtesting](backtesting.md) — turning sentiment into a measurable strategy.
