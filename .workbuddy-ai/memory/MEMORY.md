# Project memory — Applied AI project 2 (Financial Sentiment Pipeline)

## Setup
- Python with all deps: `/Users/badremhiouah/miniconda3/bin/python3`
  (`PYTHONPATH=src`). Plain `python3` is missing fastapi/openbb/pandas.
- Start the API: `/Users/badremhiouah/miniconda3/bin/python3 scripts/run_api.py`
  (default `http://127.0.0.1:8000`, UI at `/analysis.html`, docs at `/docs`).
- Shell has an HTTP proxy: use `curl --noproxy '*'` for localhost, else 502.
- Background processes die at the end of a tool call — start server + curl + kill
  inside one Bash invocation.

## Architecture (kept simple on purpose)
- `src/financial_sentiment/` — `repository` (SQLite `data/news.db`), `providers`
  (OpenBB / Finnhub), `sentiment` (FinBERT / Groq / vLLM), `pipeline`, `analysis`,
  `strategy/` (data, portfolio, trade, strategy, backtester, metrics, comparison,
  optimizer), `api/` (FastAPI: routes `equities`, `pipeline`, `analysis`, `backtest`).
- `Backtester.run(equity, df=None)` — pass `df` to run several strategies on one
  identical copy of the data (used by `StrategyComparator`).
- Equity curve convention: `virtual_capital` = cash + liquidation value of open
  trades; everything is liquidated on the last bar.

## Conventions
- Analyse tab is **single-equity** (radio list); other charts take one symbol.
- Strategy comparison: Simple (sentiment) vs Benchmark (Buy & Hold), 4 metrics
  (Total Return, CAGR, Max Drawdown, Sharpe) in `strategy/metrics.py`.
- Max Drawdown is stored **negative**; all four metrics are "higher is better".
- Don't over-engineer: the user prefers small, readable additions that reuse the
  existing architecture over new abstractions.
