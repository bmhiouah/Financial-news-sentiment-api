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
- `src/financial_sentiment/` — `repository` (PostgreSQL via `psycopg` 3.x;
  `DATABASE_URL` from `.env`; bundled `pgserver` keeps data in
  `~/.financial_sentiment/pgdata`), `providers` (OpenBB / Finnhub), `sentiment`
  (FinBERT / Groq / vLLM), `pipeline`, `analysis`, `strategy/` (data, portfolio,
  trade, strategy, backtester, metrics, comparison, optimizer), `api/`
  (FastAPI: routes `equities`, `pipeline`, `analysis`, `backtest`).
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
- For non-technical writeups/overviews: **objective, professional, third-person tone**.
  No "I", no conversational filler; talk less, let the charts carry the content.
  **No verdicts on the underlying research question** — stick to what the project
  *demonstrates* and its *limitations* (data, scope). User explicitly rejected a
  "verdict" panel and asked for flaws & axes of improvement instead. The honest
  framing is "rough idea, not a verdict" — the data quality (free APIs, delayed,
  no intraday ticks) is the binding constraint, not the model.
- **Plots**: never invent charts. Use the actual plots the project produces. For
  this project that's `Correlation by Equity` (Pearson r grouped bars at 1d/1w/1m)
  and `Price + News Sentiment` (markers on a price line, sized by |score|,
  coloured by sign), not stylised sparklines.

## Posters / images
- For non-technical overview posters, hand-author the HTML and render with
  Chrome headless — `ImageGen` garbles required copy.
  `"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless=new
  --hide-scrollbars --no-sandbox --force-device-scale-factor=2
  --window-size=1600,2100 --screenshot=out.png file://…/page.html`
- Set the window **tall enough** for the full page; 1300px cropped the bottom
  of the overview poster. Probe actual content height first if unsure.
- No `inkscape` / `convert` on this box. `rsvg-convert` (miniconda) and
  `qlmanage` are available; Chrome is the most reliable for HTML→PNG.
