# Financial Sentiment Pipeline

Fetch financial news and historical prices, run FinBERT sentiment analysis, and visualize the results.

## Quick Start

```bash
pip install -r requirements.txt

# Fetch data + sentiment
python main.py --symbols AAPL MSFT --start-date 2024-01-01 --end-date 2024-01-31 --analyze

# Re-run skips API calls for data already in database
python main.py --symbols AAPL MSFT --start-date 2024-01-01 --end-date 2024-01-31 --analyze

# Text-based sentiment vs returns analysis
python analysis.py
```

## Usage

```bash
python main.py --symbols AAPL GOOGL MSFT --start-date 2026-07-01 --end-date 2026-08-28 --analyze
```

- `--symbols` - stock symbols
- `--start-date` / `--end-date` - date range
- `--analyze` - run FinBERT sentiment on headlines

## Smart Deduplication

Before fetching, the pipeline checks `data/news.db`. If the requested date range for a symbol is already present, the API call is skipped. To force a fresh fetch, delete `data/news.db`.

## Notebook

Open `notebooks/demo.ipynb` to inspect the database and visualize price lines with sentiment markers.

## Project Structure

```
├── main.py            # CLI entrypoint
├── provider.py        # OpenBB wrapper
├── analyzer.py        # FinBERT scorer
├── database.py        # SQLite storage
├── analysis.py        # sentiment vs returns
├── requirements.txt
├── README.md
├── ReadmeV1.md
├── notebooks/
│   └── demo.ipynb
└── data/
    └── news.db
```

## Database Schema

**news**
- `symbol`, `date`, `headline`, `text`, `source`, `url`
- `sentiment_label`, `confidence`
- `finbert_score` (-1 to +1)

**prices**
- `symbol`, `date`, `open`, `high`, `low`, `close`, `volume`
