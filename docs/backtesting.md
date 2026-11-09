# Backtesting

Backtesting is a separate import so the package root stays light. The strategy
package lives in `financial_sentiment/strategy/` and powers the `/backtest/*`
endpoints described in [API & web UI](api.md).

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

## Strategy modules

| Module | Role |
|---|---|
| `data.py` | loads the (price, sentiment) series for one symbol |
| `trade.py` | `Trade`, `Side` |
| `portfolio.py` | capital, stop-loss / stop-win |
| `strategy.py` | threshold and buy-and-hold strategies |
| `backtester.py` | the tick loop |
| `metrics.py` | total return, CAGR, max drawdown, Sharpe |
| `comparison.py` | sentiment strategy vs benchmark |
| `optimizer.py` | coarse-then-refine parameter search |

Endpoints: `POST /backtest/run`, `POST /backtest/compare` and
`POST /backtest/optimize`.
