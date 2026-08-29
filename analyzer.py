from transformers import pipeline

_analyzer = None


def _get_analyzer():
    global _analyzer
    if _analyzer is None:
        _analyzer = pipeline(
            "sentiment-analysis",
            model="ProsusAI/finbert",
            truncation=True,
            max_length=512,
        )
    return _analyzer


def score(text: str) -> tuple[float, str]:
    if not text:
        return 0.0, "neutral"
    try:
        results = _get_analyzer()(text[:512])
        pos = neg = neu = 0.0
        for r in results:
            label = r["label"].lower()
            s = float(r["score"])
            if label == "positive":
                pos = s
            elif label == "negative":
                neg = s
            elif label == "neutral":
                neu = s
        continuous = pos - neg
        if continuous > 0.2:
            label = "positive"
        elif continuous < -0.2:
            label = "negative"
        else:
            label = "neutral"
        return continuous, label
    except Exception:
        return 0.0, "neutral"
