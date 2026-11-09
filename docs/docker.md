# Docker

`docker-compose.yml` runs two services: `db` (PostgreSQL 16) and `api` (this app,
built from `config/Dockerfile`). The build context is the repository root, which
lets the Dockerfile copy `financial_sentiment/`, `scripts/`, `pyproject.toml` and
`config/requirements.txt` in one pass. The CLI launcher lives in `scripts/`, so
it is already included.

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

The image can also be built directly:

```bash
docker build -f config/Dockerfile -t financial-sentiment .
```

## Using the image as a CLI

The same image is also the CLI and the maintenance scripts:

```bash
docker compose run --rm api financial-sentiment --help
docker compose run --rm api financial-sentiment \
    --symbols AAPL MSFT --start-date 2026-07-01 --end-date 2026-08-28 --analyze
docker compose run --rm api python scripts/backfill_equities.py
docker compose run --rm api python scripts/score_llm.py --limit 100
```

## Provider API keys

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

## Notes on the image

- **CPU-only torch.** Torch is installed from `download.pytorch.org/whl/cpu`
  first; pulling it from PyPI instead adds ~2 GB of unused CUDA libraries. Keep
  the version in `config/Dockerfile` in sync with `config/requirements.txt`.
- **FinBERT weights** (~440 MB) download on the first scored headline and are
  stored in the `hf-cache` volume, so they survive restarts. To pre-warm them:
  `docker compose run --rm api python -c "from financial_sentiment.sentiment import FinBERTScorer; FinBERTScorer().score('warm up')"`.
- The app runs as a non-root user (`app`, uid 10001).
- `OPENBB_AUTO_BUILD=false` skips OpenBB's import-time package rebuild.
- The container healthcheck hits `/pipeline/status`, which only answers once the
  database is reachable and the schema exists.
- `.dockerignore` keeps `.env`, tool caches, `docs/`, `assets/` and `README.md`
  out of the build context.

See [Configuration](configuration.md) for the Docker-specific environment
variables and the environment template.
