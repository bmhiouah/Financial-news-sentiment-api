# Sentiment scoring

Headlines are scored with **FinBERT** (`ProsusAI/finbert`) as the primary scorer.
`financial_sentiment/sentiment/` holds the scorer contract (`base.py`), the
FinBERT implementation (`finbert.py`) and the optional Groq LLM scorer
(`groq.py`). Scores land in `sentiment_label`, `confidence` and `finbert_score`
on the `news` table; see [Database](database.md).

## LLM (Groq) sentiment backfill

`GroqSentimentScorer` produces a FinBERT-shaped result (positive / negative /
neutral probabilities, a label and a compound score in [-1, +1]) and stores it in
the `llm_*` columns. FinBERT stays the primary scorer; this is a comparison path.
It requires `GROQ_API_KEY` in `.env` (see [Configuration](configuration.md)).

```bash
export GROQ_API_KEY="gsk_..."      # or add it to .env
python scripts/score_llm.py                  # score every row with llm_score IS NULL
python scripts/score_llm.py --limit 500
python scripts/score_llm.py --delay 0.1      # rate-limit guard
python scripts/score_llm.py --batch-size 25  # DB write granularity (default 50)
```

The script is idempotent and resumable: only rows with `llm_score IS NULL` are
scored, and results are flushed every `--batch-size` rows.

`/analysis/finbert-vs-llm` compares the two scorers on the same headlines — see
[API & web UI](api.md).
