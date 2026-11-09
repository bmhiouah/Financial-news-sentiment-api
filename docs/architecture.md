# Architecture

```
OpenBB / Finnhub  ->  news  ->  FinBERT sentiment  ->  PostgreSQL  ->  API + UI
```

Providers fetch headlines and daily bars, the pipeline de-duplicates and scores
them, the repository persists everything with upserts, and the FastAPI layer
serves the analysis and backtest endpoints. All SQL lives in `repository.py`.

## Project structure

```
.
├── README.md                    # short index + documentation links
├── pyproject.toml               # package metadata for `pip install -e .`
├── docker-compose.yml           # api + PostgreSQL 16
├── config/
│   ├── Dockerfile               # API + CLI image (CPU-only torch, non-root)
│   ├── requirements.txt         # pinned runtime stack
│   ├── requirements-dev.txt     # dev tools + bundled local PostgreSQL
│   └── env.example              # template copied to .env at the project root
├── docs/                        # these guides
├── assets/
│   └── Project_overview_final.png
├── scripts/
│   ├── _bootstrap.py            # shared project-root path bootstrap for the scripts
│   ├── main.py                  # CLI launcher for a plain source checkout
│   ├── pg_server.py             # start/stop the bundled local PostgreSQL
│   ├── run_api.py               # start the API (no Docker)
│   ├── backfill_equities.py     # populate the ticker universe
│   ├── recompute_returns.py     # recompute forward returns from stored closes
│   └── score_llm.py             # backfill Groq LLM sentiment
└── financial_sentiment/         # the installed package (flat layout, no src/)
    ├── config.py                # settings + .env loading
    ├── domain.py                # NewsItem, PriceBar, SentimentResult, Coverage, Equity
    ├── repository.py            # PostgreSQL schema and queries (the only SQL)
    ├── pipeline.py              # orchestration: fetch -> score -> persist
    ├── cli.py                   # argparse -> Pipeline
    ├── analysis.py              # sentiment vs forward-return correlation
    ├── providers/
    │   ├── base.py              # NewsProvider / PriceProvider contracts
    │   ├── openbb.py            # OpenBB news + prices (provider fallback list)
    │   └── finnhub.py           # Finnhub news (staging table, backward pagination)
    ├── sentiment/
    │   ├── base.py              # SentimentScorer contract
    │   ├── finbert.py           # FinBERT (ProsusAI/finbert)
    │   └── groq.py              # optional LLM scorer, writes the llm_* columns
    ├── strategy/                # sentiment-driven backtester
    │   ├── data.py              # loads the (price, sentiment) series for one symbol
    │   ├── trade.py             # Trade, Side
    │   ├── portfolio.py         # capital, stop-loss / stop-win
    │   ├── strategy.py          # threshold + buy-and-hold strategies
    │   ├── backtester.py        # the tick loop
    │   ├── metrics.py           # total return, CAGR, max drawdown, Sharpe
    │   ├── comparison.py        # sentiment strategy vs benchmark
    │   └── optimizer.py         # coarse-then-refine parameter search
    └── api/                     # FastAPI app
        ├── main.py, deps.py, schemas.py
        ├── routes/              # equities, pipeline, analysis, backtest
        └── static/              # web UI
```

Hidden root files: `.env` (local secrets, never committed), `.gitignore`,
`.dockerignore`, plus the local `.venv/` and `.git/`. The environment template
lives in `config/env.example` and is copied to `.env` at the project root. The
three visible root files stay there because their consumers look for them by
name at the project root: `pip install -e .` reads `pyproject.toml`,
`docker compose up` reads `docker-compose.yml`, and GitHub renders `README.md`.
`.env` stays too — `config.py` loads `<project_root>/.env` and Compose reads it
for `${...}` substitution.

## Why is the code in `financial_sentiment/`?

The project uses a **flat layout**: the installable package sits directly at the
repository root, with no `src/` wrapper. The folder has to keep this name:

- `[project.scripts] financial-sentiment = "financial_sentiment.cli:main"` and
  `[tool.setuptools.package-data] financial_sentiment = ["api/static/*"]` address
  it by name; `[tool.setuptools.packages.find] include = ["financial_sentiment*"]`
  discovers it at the root.
- Every internal import is relative (`from .pipeline import Pipeline`), so all
  modules must live under one package directory.
- `config.py` resolves `PROJECT_ROOT` as `parents[1]` from
  `financial_sentiment/config.py`, which is what lets `<root>/.env` load from any
  working directory.

Putting the modules straight into a folder called `src/` would make the package
itself be named `src` — `import src.pipeline` collides with every other project
that has a `src` folder, and the console script and package data would break.
The earlier `src/financial_sentiment/` layout avoided that with an extra
container level; the flat layout removes that nesting while keeping the same
package name.

## Further reading

- [Getting started](getting-started.md) — run it.
- [Configuration](configuration.md) — settings and provider order.
- [Database](database.md) — schema and forward returns.
- [Sentiment scoring](sentiment.md) — FinBERT and the LLM comparison path.
- [CLI](cli.md), [API & web UI](api.md), [Backtesting](backtesting.md),
  [Docker](docker.md).
