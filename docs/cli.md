# CLI

After `pip install -e .` (or inside the container) the CLI is installed as
`financial-sentiment`. From a plain source checkout, `scripts/main.py` runs the
same `financial_sentiment.cli:main` function without an editable install; it uses
the shared `scripts/_bootstrap.py` path helper, like the other scripts.

```bash
python scripts/main.py --symbols AAPL GOOGL --start-date 2026-07-01 --end-date 2026-08-28 --analyze
python scripts/main.py --symbols AAPL --start-date 2026-07-01 --end-date 2026-08-28 --analyze --source openbb
python scripts/main.py --symbols AAPL --start-date 2026-07-01 --end-date 2026-08-28 --analyze \
    --source finnhub --finnhub-sources CNBC Reuters

# installed entry point (identical CLI)
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

## Coverage guards

Before every API call the pipeline checks what is already stored:

- **prices** are skipped when the stored range covers the requested window
  (`--force-refresh` overrides this).
- **news** is always re-fetched (no provider guarantees it returned everything)
  but de-duplicated by URL *before* scoring, so a repeat run costs API calls and
  no FinBERT work.

Finnhub also paginates backwards automatically: its free tier caps a response at
~250 items, so the provider walks the end date backwards until a short page
shows the window is drained.

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

See [Architecture](architecture.md) for the module layout and
[API & web UI](api.md) for the HTTP equivalents.
