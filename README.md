# Financial Sentiment Pipeline

> **Can we extract sentiment from financial news and turn it into a measurable
> market signal?**

![Project overview: headlines in, evidence out](Project_Overview_final.png)


Fetch financial news and prices from OpenBB (and Finnhub), score headlines with
FinBERT, store everything in PostgreSQL, and explore the results through a web UI
and a REST API.

```
OpenBB / Finnhub  ->  news  ->  FinBERT sentiment  ->  PostgreSQL  ->  API + UI
```

## Quick start

### With Docker (recommended)

```bash
cp .env.example .env        # optional: add GROQ_API_KEY
docker compose up --build   # API on :8000, PostgreSQL on :5432
```

Open `http://127.0.0.1:8000/`. The database schema is created on startup, so
there is no migration step. See [Docker](#docker) for details.

### Without Docker

```bash
pip install -r requirements.txt
pip install -r requirements-dev.txt   # adds the bundled local PostgreSQL

# 1. point the app at a database (see "Database" below)
echo "DATABASE_URL=postgresql://postgres:@/financial_sentiment?host=$HOME/.financial_sentiment/pgdata" > .env

# 2. start the bundled local PostgreSQL (skip if you already run one)
python scripts/pg_server.py start

# 3. fetch news + prices and score the headlines
python main.py --symbols AAPL MSFT --start-date 2026-07-01 --end-date 2026-08-28 --analyze

# 4. explore
python scripts/run_api.py          # http://127.0.0.1:8000
python -m financial_sentiment.analysis
```

## Docker

`docker-compose.yml` runs two services: `db` (PostgreSQL 16) and `api` (this
app, built from the `Dockerfile`).

```bash
docker compose up --build          # foreground
docker compose up -d --build       # detached
docker compose logs -f api
docker compose down                # stop, keep the volumes
docker compose down -v             # stop and delete the database
```

| | |
|---|---|
| UI | http://127.0.0.1:8000 |
| API docs | http://127.0.0.1:8000/docs |
| PostgreSQL | `localhost:5432` (`postgres` / `postgres` / `financial_sentiment`) |

The same image is also the CLI and the maintenance scripts:

```bash
docker compose run --rm api financial-sentiment --help
docker compose run --rm api financial-sentiment \
    --symbols AAPL MSFT --start-date 2026-07-01 --end-date 2026-08-28 --analyze
docker compose run --rm api python scripts/backfill_equities.py
docker compose run --rm api python scripts/score_llm.py --limit 100
```

### Provider API keys

OpenBB stores its keys in `~/.openbb_platform/user_settings.json` (`obb.user.credentials`),
**not** in environment variables. Compose bind-mounts your host `~/.openbb_platform`
into the container, so the keys you already configured work unchanged. Without
that mount OpenBB starts with empty credentials: `yfinance` still works (it needs
no key), but Finnhub/FMP/tiingo will fail and the pipeline reports them as warnings.

To seed credentials inside a container instead, run once and follow the prompt:

```bash
docker compose run --rm api python -c "
from openbb import obb
obb.user.credentials.finnhub_api_key = 'your_key'
obb.user.credentials.save()"
```

### Notes on the image

- **CPU-only torch.** Torch is installed from `download.pytorch.org/whl/cpu`
  first; pulling it from PyPI instead adds ~2 GB of unused CUDA libraries. Keep
  the version in the Dockerfile in sync with `requirements.txt`.
- **FinBERT weights** (~440 MB) download on the first scored headline and are
  stored in the `hf-cache` volume, so they survive restarts. To pre-warm them:
  `docker compose run --rm api python -c "from financial_sentiment.sentiment import FinBERTScorer; FinBERTScorer().score('warm up')"`.
- The app runs as a non-root user (`app`, uid 10001).
- `OPENBB_AUTO_BUILD=false` skips OpenBB's import-time package rebuild.
- The container healthcheck hits `/pipeline/status`, which only answers once the
  database is reachable and the schema exists.

## Database

PostgreSQL is the only backend. The app needs nothing but a connection string,
so it works against a local instance, Docker or a managed service.

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

## CLI

```bash
python main.py --symbols AAPL GOOGL --start-date 2026-07-01 --end-date 2026-08-28 --analyze
python main.py --symbols AAPL --start-date 2026-07-01 --end-date 2026-08-28 --analyze --source openbb
python main.py --symbols AAPL --start-date 2026-07-01 --end-date 2026-08-28 --analyze \
    --source finnhub --finnhub-sources CNBC Reuters

# after `pip install .` (or inside the container) the same CLI is installed as:
financial-sentiment --symbols AAPL --start-date 2026-07-01 --end-date 2026-08-28 --analyze
```

| Flag | Meaning |
|---|---|
| `--symbols` | tickers to fetch |
| `--start-date` / `--end-date` | `YYYY-MM-DD` window |
| `--analyze` | run FinBERT on the fetched headlines |
| `--source` | `openbb`, `finnhub` or `both` (default) |
| `--finnhub-sources` | restrict Finnhub to these publishers (default: all) |
| `--force-refresh` | re-fetch prices even when the window is already covered |

### Coverage guards

Before every API call the pipeline checks what is already stored:

- **prices** are skipped when the stored range covers the requested window
  (`--force-refresh` overrides this).
- **news** is always re-fetched (no provider guarantees it returned everything)
  but de-duplicated by URL *before* scoring, so a repeat run costs API calls and
  no FinBERT work.

Finnhub also paginates backwards automatically: its free tier caps a response at
~250 items, so the provider walks the end date backwards until a short page
shows the window is drained.

## Web UI and API

```bash
python scripts/run_api.py            # http://127.0.0.1:8000
python scripts/run_api.py --port 9000
python scripts/run_api.py --reload   # dev mode
```

Open `http://127.0.0.1:8000/` for the UI and `http://127.0.0.1:8000/docs` for the
interactive OpenAPI docs.

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/equities/symbols?q=apple&limit=500&offset=0` | Search the ticker universe |
| `GET` | `/equities/count` | Total tickers stored |
| `GET` | `/pipeline/status` | Coverage (news / price / scored rows) |
| `POST` | `/pipeline/run` | Fetch + score for symbols and a date range |
| `GET` | `/analysis/available-symbols` | Symbols with both prices and scored news |
| `GET` | `/analysis/date-range` | Min/max date available |
| `GET` | `/analysis/correlation` | Sentiment vs forward returns, per symbol |
| `GET` | `/analysis/price-sentiment` | Price line + daily sentiment markers |
| `GET` | `/analysis/finbert-vs-llm` | FinBERT vs LLM scores on the same headlines |
| `GET` | `/analysis/distribution` | Sentiment x log-return heatmap + correlation bars |
| `GET` | `/analysis/news` | Stored articles for one symbol |
| `POST` | `/backtest/run` | Backtest the sentiment strategy |
| `POST` | `/backtest/compare` | Sentiment strategy vs buy & hold |
| `POST` | `/backtest/optimize` | Grid-search the strategy parameters |

```jsonc
// POST /pipeline/run
{
  "symbols": ["AAPL", "MSFT"],
  "start_date": "2026-07-01",
  "end_date": "2026-08-28",
  "sources": ["openbb", "finnhub"],
  "finnhub_sources": null,   // null = keep every publisher
  "analyze": true,
  "force_refresh": false
}
```

## Project structure

```
src/financial_sentiment/
├── config.py            # Settings + .env loading
├── domain.py            # NewsItem, PriceBar, SentimentResult, Coverage, Equity
├── repository.py        # PostgreSQL schema and queries (the only SQL in the project)
├── pipeline.py          # orchestration: fetch -> score -> persist
├── cli.py               # argparse -> Pipeline
├── analysis.py          # sentiment vs forward-return correlation
├── providers/           # data ingestion
│   ├── base.py          # NewsProvider / PriceProvider contracts
│   ├── openbb.py        # OpenBB news + prices (provider fallback list)
│   └── finnhub.py       # Finnhub news (staging table, backward pagination)
├── sentiment/
│   ├── base.py          # SentimentScorer contract
│   ├── finbert.py       # FinBERT (ProsusAI/finbert)
│   └── groq.py          # optional LLM scorer, writes the llm_* columns
├── strategy/            # sentiment-driven backtester
│   ├── data.py          # loads the (price, sentiment) series for one symbol
│   ├── trade.py         # Trade, Side
│   ├── portfolio.py     # capital, stop-loss / stop-win
│   ├── strategy.py      # threshold + buy-and-hold strategies
│   ├── backtester.py    # the tick loop
│   ├── metrics.py       # total return, CAGR, max drawdown, Sharpe
│   ├── comparison.py    # sentiment strategy vs benchmark
│   └── optimizer.py     # coarse-then-refine parameter search
└── api/                 # FastAPI app
    ├── main.py, deps.py, schemas.py
    ├── routes/          # equities, pipeline, analysis, backtest
    └── static/          # web UI

scripts/
├── pg_server.py         # start/stop the bundled local PostgreSQL (no Docker)
├── run_api.py           # start the API (no Docker)
├── backfill_equities.py # populate the ticker universe
└── score_llm.py         # backfill Groq LLM sentiment

main.py                  # CLI entry point (`python main.py`)
Dockerfile               # API + CLI image (CPU-only torch, non-root)
docker-compose.yml       # api + PostgreSQL 16
.dockerignore
```

## Programmatic use

```python
from datetime import datetime
from financial_sentiment import Pipeline

results = Pipeline.default().run(
    symbols=["AAPL", "MSFT"],
    start=datetime(2026, 7, 1),
    end=datetime(2026, 8, 28),
    sources=("openbb", "finnhub"),
    finnhub_sources=None,   # None = every publisher, or ["CNBC"]
    analyze=True,
    force_refresh=False,
)
```

Backtesting is a separate import so the package root stays light:

```python
from financial_sentiment.strategy import (
    Backtester, Portfolio, SentimentThresholdStrategy, StrategyComparator,
)

portfolio = Portfolio(initial_capital=100, trade_size=20,
                      stop_loss=-0.05, stop_win=0.10)
strategy = SentimentThresholdStrategy(buy_threshold=0.2, sell_threshold=-0.2)
df = Backtester(portfolio, strategy).run(symbol="AAPL")
# df = date, open, high, low, close, volume, sentiment_score
#      + capital, virtual_capital, open_long, open_short
```

- `capital` is available cash; `virtual_capital` adds the liquidation value of
  open positions. All positions are closed on the final bar, so the two agree.
- A strategy must produce **>= 5 signals**; otherwise `run()` raises
  `InsufficientSignalsError` before trading.
- `StrategyComparator` loads the series once and passes the same DataFrame to
  both the sentiment strategy and a buy & hold benchmark, so the comparison
  cannot diverge on data or assumptions.
- `StrategyOptimizer` grid-searches `(stop_loss, stop_win, buy_threshold,
  sell_threshold)` on total P&L, refining around the best candidates.

## LLM (Groq) sentiment backfill

`GroqSentimentScorer` produces a FinBERT-shaped result (positive / negative /
neutral probabilities, a label and a compound score in [-1, +1]) and stores it in
the `llm_*` columns. FinBERT stays the primary scorer; this is a comparison path.

```bash
export GROQ_API_KEY="gsk_..."      # or add it to .env
python scripts/score_llm.py                  # score every row with llm_score IS NULL
python scripts/score_llm.py --limit 500
python scripts/score_llm.py --delay 0.1      # rate-limit guard
python scripts/score_llm.py --batch-size 25  # DB write granularity (default 50)
```

The script is idempotent and resumable: only rows with `llm_score IS NULL` are
scored, and results are flushed every `--batch-size` rows.

## Configuration

Every setting is read from the environment, then `<project_root>/.env`, then the
defaults in `config.py` (see `.env.example`):

| Variable | Default |
|---|---|
| `DATABASE_URL` | `postgresql:///financial_sentiment` |
| `FINANCIAL_SENTIMENT_FINBERT_MODEL` | `ProsusAI/finbert` |
| `FINANCIAL_SENTIMENT_POS_THRESHOLD` / `_NEG_THRESHOLD` | `0.2` / `-0.2` |
| `FINANCIAL_SENTIMENT_PRICE_PROVIDERS` | `fmp,yfinance,tiingo` |
| `FINANCIAL_SENTIMENT_NEWS_PROVIDERS` | `,yfinance` |
| `FINANCIAL_SENTIMENT_FINNHUB_PAGE_LIMIT` / `_MAX_PAGES` | `200` / `40` |

The OpenBB provider lists are ordered fallbacks: the first provider that returns
rows wins, so a ticker missing from a paid tier is rescued by a free one. An
empty entry means "let OpenBB pick its own priority".

## Database schema

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

### Forward returns, not backward

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
