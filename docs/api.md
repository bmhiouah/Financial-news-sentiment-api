# API & web UI

Start the API locally (no Docker) with:

```bash
python scripts/run_api.py            # http://127.0.0.1:8000
python scripts/run_api.py --port 9000
python scripts/run_api.py --reload   # dev mode
```

Open `http://127.0.0.1:8000/` for the UI and `http://127.0.0.1:8000/docs` for the
interactive OpenAPI docs. `http://127.0.0.1:8000/analysis.html` is the analysis
dashboard.

## Endpoints

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

## Request example

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

`/pipeline/status` doubles as the container healthcheck: it only answers once the
database is reachable and the schema exists. See [Backtesting](backtesting.md)
for what the `/backtest/*` endpoints return and
[CLI](cli.md) for the equivalent command-line flags.
