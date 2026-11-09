# Configuration

Every setting is read from the environment, then `<project_root>/.env`, then the
defaults in `financial_sentiment/config.py`. Start from the template:

```bash
cp config/env.example .env
```

The template is `config/env.example`; the real `.env` must stay at the **project
root**, because `config.py` resolves `PROJECT_ROOT` from the package location and
loads `.env` at import time, and Docker Compose reads the same root file for its
`${...}` substitutions. `.env` is git-ignored and excluded from the Docker build
context, so only the template is versioned.

| Variable | Default |
|---|---|
| `DATABASE_URL` | `postgresql:///financial_sentiment` |
| `FINANCIAL_SENTIMENT_FINBERT_MODEL` | `ProsusAI/finbert` |
| `FINANCIAL_SENTIMENT_POS_THRESHOLD` / `_NEG_THRESHOLD` | `0.2` / `-0.2` |
| `FINANCIAL_SENTIMENT_PRICE_PROVIDERS` | `fmp,yfinance,tiingo` |
| `FINANCIAL_SENTIMENT_NEWS_PROVIDERS` | `,yfinance` |
| `FINANCIAL_SENTIMENT_FINNHUB_PAGE_LIMIT` / `_MAX_PAGES` | `200` / `40` |

Under Docker, `docker-compose.yml` overrides `DATABASE_URL` to point at its own
`db` service and reads `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`,
`POSTGRES_PORT` and `API_PORT` from the environment. `GROQ_API_KEY` enables the
optional [LLM scoring](sentiment.md) path.

## Provider fallback order

The OpenBB provider lists are ordered fallbacks: the first provider that returns
rows wins, so a ticker missing from a paid tier is rescued by a free one. An
empty entry means "let OpenBB pick its own priority".

OpenBB credentials are stored in `~/.openbb_platform/user_settings.json`, not in
environment variables — see [Docker](docker.md#provider-api-keys).

## Dependencies

The runtime stack is pinned in `config/requirements.txt`; development tools and
the bundled PostgreSQL live in `config/requirements-dev.txt`:

```bash
pip install -r config/requirements.txt
pip install -r config/requirements-dev.txt
```

See [Getting started](getting-started.md) for the full setup sequence.
