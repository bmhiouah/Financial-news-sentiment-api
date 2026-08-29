from typing import Tuple
from transformers import pipeline

from provider import get_news
from database import init_db, save_news, update_sentiment


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


def finbert_score(text: str) -> Tuple[float, str]:
    if not text:
        return 0.0, "neutral"
    try:
        results = _get_analyzer()(text[:512])
        pos = neg = neu = 0.0
        for r in results:
            label = r["label"].lower()
            score = float(r["score"])
            if label == "positive":
                pos = score
            elif label == "negative":
                neg = score
            elif label == "neutral":
                neu = score
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


def vllm_score(text: str, endpoint: str = "http://localhost:8000/v1/chat/completions") -> Tuple[float, str]:
    if not text:
        return 0.0, "neutral"
    try:
        import requests
        prompt = (
            "Rate the financial sentiment of the following text on a scale from -1 (very negative) "
            "to +1 (very positive). Return only a JSON object like {\"score\": 0.5, \"label\": \"positive\"}.\n\n"
            f"Text: {text[:1000]}"
        )
        response = requests.post(
            endpoint,
            json={
                "model": "default",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.0,
            },
            timeout=30,
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        import json
        data = json.loads(content)
        score = float(data.get("score", 0.0))
        score = max(-1.0, min(1.0, score))
        label = data.get("label", "neutral")
        if score > 0.2:
            label = "positive"
        elif score < -0.2:
            label = "negative"
        else:
            label = "neutral"
        return score, label
    except Exception:
        return 0.0, "neutral"


def analyze():
    news = get_news(
        symbols=["AAPL", "MSFT"],
        start_date=datetime(2024, 1, 1),
        end_date=datetime(2024, 1, 31),
        limit=10,
    )
    init_db()
    save_news(news)

    for item in news:
        text = item.get("text") or item.get("headline", "")
        fb_score, fb_label = finbert_score(text)
        vllm_score_val, vllm_label = vllm_score(text)
        update_sentiment(item["url"], fb_label, fb_score, vllm_score_val, vllm_label)

    print(f"Analyzed {len(news)} articles")
