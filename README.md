# Financial Sentiment Pipeline

Fetch financial news and historical prices, run FinBERT sentiment analysis, and visualize the results.

## Quick Start

```bash
pip install -r requirements.txt

# Single entry point: fetch data + sentiment for the requested range
python main.py --symbols AAPL MSFT --start-date 2024-01-01 --end-date 2024-01-31 --analyze

# Re-running the same range skips API calls for already-covered data
python main.py --symbols AAPL MSFT --start-date 2024-01-01 --end-date 2024-01-31 --analyze

# Backfill returns
python scripts/backfill_returns.py

# Text-based sentiment vs returns analysis
python -m financial_sentiment.analysis
```

## Usage

```bash
# Fetch from both OpenBB and Finnhub, default CNBC filter, run FinBERT
python main.py --symbols AAPL GOOGL MSFT --start-date 2026-07-01 --end-date 2026-08-28 --analyze

# Finnhub only, with custom source filter
python main.py --symbols AAPL MSFT --start-date 2026-07-01 --end-date 2026-08-28 --analyze \
    --source finnhub --finnhub-sources CNBC Reuters

# OpenBB only
python main.py --symbols AAPL --start-date 2026-07-01 --end-date 2026-08-28 --analyze --source openbb
```

- `--symbols` - stock symbols
- `--start-date` / `--end-date` - date range
- `--analyze` - run FinBERT sentiment on headlines
- `--source` - `openbb`, `finnhub`, or `both` (default)
- `--finnhub-sources` - list of sources to keep (default: `CNBC`). When Finnhub's free-tier
  news depth limit is reached, the provider paginates backward automatically
  (oldest fetched date -> next page end-date).
- `--force-refresh` - re-fetch from APIs even when the requested range is already
  covered in the database (default: skip covered symbols to avoid API cost).

## Coverage Guards (avoid unnecessary API calls)

The pipeline checks `data/news.db` before every API call:

- **prices** (one row per trading day): skipped when MIN(date) <= start and MAX(date) >= end.
- **news** / **finnhub_news** (sparse): skipped when at least one row exists for
  the symbol within `[start, end]`.

Use `--force-refresh` to override and re-fetch anyway. A unique index on
`prices(symbol, date)` and `news(symbol, url)` de-duplicates overlapping
fetches.

## Smart Deduplication

Before fetching, the pipeline checks `data/news.db`. If the requested date range for a symbol is already present, the API call is skipped. To force a fresh fetch, delete `data/news.db`.

## Notebook

Open `notebooks/demo.ipynb` to inspect the database and visualize price lines with sentiment markers.

## Project Structure

```
├── data/
│   └── news.db
├── notebooks/
│   └── demo.ipynb
├── scripts/
│   ├── run_pipeline.py        # thin shim -> financial_sentiment.cli
│   └── backfill_returns.py
├── src/
│   └── financial_sentiment/
│       ├── __init__.py        # public API
│       ├── config.py          # Settings dataclass
│       ├── domain.py          # NewsItem, PriceBar, SentimentResult, Coverage
│       ├── repository.py      # SQLite-backed Repository
│       ├── pipeline.py        # Pipeline orchestrator
│       ├── cli.py             # argparse -> Pipeline
│       ├── analysis.py        # CorrelationAnalyzer
│       ├── providers/
│       │   ├── base.py        # NewsProvider, PriceProvider ABCs
│       │   ├── openbb.py      # OpenBB implementations
│       │   └── finnhub.py     # Finnhub implementation (with backward pagination)
│       ├── sentiment/
│       │   ├── base.py        # SentimentScorer ABC
│       │   ├── finbert.py     # FinBERTScorer
│       │   └── vllm.py        # VLLMScorer
│       └── strategy.py        # future: trading strategies & backtesting
├── main.py                    # single entry point
├── requirements.txt
└── README.md
```

## Programmatic API

```python
from datetime import datetime
from financial_sentiment import Pipeline

results = Pipeline.default().run(
    symbols=["AAPL", "MSFT", "GOOGL"],
    start=datetime(2026, 7, 1),
    end=datetime(2026, 8, 28),
    sources=("openbb", "finnhub"),
    finnhub_sources=["CNBC"],
    analyze=True,        # run FinBERT on fetched headlines
    force_refresh=False, # set True to bypass the coverage check
)
```

## Trading Strategy & Backtester

```python
from financial_sentiment import (
    Backtester, Portfolio, SentimentThresholdStrategy,
)

portfolio = Portfolio(
    initial_capital=100, trade_size=20,
    stop_loss=-0.05, stop_win=0.10,
)
strategy = SentimentThresholdStrategy(
    buy_threshold=0.2, sell_threshold=-0.2,
)
df = Backtester(portfolio, strategy).run(equity="AAPL")
# `df` is the original price DataFrame enriched with:
#   capital, virtual_capital, open_long, open_short
```

- `capital` is the available cash (open trades are funded from it).
- `virtual_capital` = `capital` + the liquidation value of every open trade
  at the current price.
- On the final trading day all open trades are liquidated, so the last
  `capital` equals the last `virtual_capital`.
- A strategy must produce **>= 5 buy/sell signals** on the loaded data;
  otherwise `run()` raises `InsufficientSignalsError` before any trades
  are placed.

OOP layout (`src/financial_sentiment/strategy/`):

- `Trade`, `Side` — position model; return is signed so positive always means profit.
- `Portfolio` — capital, `open_trade`, `close_stops` (fires on `stop_loss` / `stop_win`), replenishes capital with `size * (1 + return)` on close. Exposes `virtual_capital` (cash + liquidation value of open trades).
- `SentimentThresholdStrategy` — `signal(score) -> Side | None`, plus a vectorized `signal_series(...)`.
- `DataLoader` — returns a price DataFrame (date, open, high, low, close, volume, sentiment_score) joined from `prices` and `news` by `(symbol, date)`.
- `Backtester` — tick loop: mark-to-market, close stops, open new trade on signal. On the **final tick** it liquidates all remaining open trades so the last `capital` cell equals the last `virtual_capital`. Returns the enriched price DataFrame.

The `notebooks/demo.ipynb` notebook contains a worked example: it picks a
random existing equity, runs the strategy, displays the enriched DataFrame,
and plots `virtual_capital` over time with a secondary panel showing the
number of open long/short trades per tick.

## Strategy Parameter Optimisation

`StrategyOptimizer` searches the `(stop_loss, stop_win, buy_threshold,
sell_threshold)` space with a coarse grid followed by a refinement pass
around the top-K coarse candidates. The objective is total P&L
(`final_capital - initial_capital`) on the requested training window.

```python
from datetime import datetime
from financial_sentiment import StrategyOptimizer

result = StrategyOptimizer().optimize(
    equity="AAPL",
    start=datetime(2026, 7, 29),
    end=datetime(2026, 8, 28),
)
print(result.best.params, result.best.pnl)
```

Exposed at the package root: `StrategyOptimizer`, `OptimizationResult`,
`TrialResult`, `DEFAULT_COARSE_GRID`.

## LLM (Groq) Sentiment Backfill

`GroqSentimentScorer` produces a FinBERT-style sentiment for each
headline (positive / negative / neutral probabilities, label, and a
compound score in [-1, +1]). The DB stores these in dedicated
`llm_*` columns on `news` and `finnhub_news`.

Set the API key once and backfill rows that already have a FinBERT
score but no LLM score yet:

```bash
export GROQ_API_KEY="gsk_..."   # https://console.groq.com/keys
python scripts/score_llm.py             # score all pending rows
python scripts/score_llm.py --limit 500 --delay 0.1   # cap + rate-limit
```

`scripts/score_llm.py` is idempotent: re-running it only scores rows
whose `llm_score` is still NULL.

The `notebooks/demo.ipynb` notebook includes a section that loads
rows with both scores and produces a FinBERT vs LLM scatter plot,
plus a per-symbol sign-agreement bar chart.

## Database Schema

**news**
- `symbol`, `date`, `headline`, `text`, `source`, `url`
- `sentiment_label`, `confidence`
- `finbert_score` (-1 to +1)

**prices**
- `symbol`, `date`, `open`, `high`, `low`, `close`, `volume`
- `daily_return`, `weekly_return`, `monthly_return`
