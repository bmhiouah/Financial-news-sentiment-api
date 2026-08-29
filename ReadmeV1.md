# 📈 Financial Sentiment Pipeline

> **Can sentiment extracted from financial news provide a useful signal for financial markets?**

This project is a hands-on exploration of an **end-to-end Applied AI pipeline** for extracting sentiment from financial news and investigating whether that sentiment contains information that can be related to subsequent market movements.

The goal is not to build a production trading system.
The goal is to understand, experiment, measure, and build a complete AI system from **unstructured text → model inference → quantitative signal → market analysis**.

---

## 🎯 Project Question

Financial markets react to information.

News articles, earnings announcements, analyst commentary, and other financial events can influence how investors perceive a company or the market.

This project asks:

**Can we extract sentiment from financial news and turn it into a measurable market signal?**

We will approach the question experimentally:

```text
                    FINANCIAL NEWS
                          │
                          ▼
                 ┌─────────────────┐
                 │  Text Processing │
                 │  & Preparation   │
                 └────────┬────────┘
                          │
                          ▼
                 ┌─────────────────┐
                 │     FinBERT     │
                 │                 │
                 │ Positive /      │
                 │ Neutral /       │
                 │ Negative        │
                 └────────┬────────┘
                          │
                          ▼
                 ┌─────────────────┐
                 │ Sentiment Signal│
                 │                 │
                 │  Aggregate over │
                 │  time / assets  │
                 └────────┬────────┘
                          │
                          ▼
              ┌───────────────────────┐
              │    Market Data        │
              │                       │
              │ Prices / Returns /    │
              │ Volatility / Volume   │
              └───────────┬───────────┘
                          │
                          ▼
                 ┌─────────────────┐
                 │    Analysis     │
                 │                 │
                 │ Correlation     │
                 │ Predictive power│
                 │ Backtesting     │
                 └─────────────────┘
```

The central loop is:

```text
        News
         │
         ▼
     Sentiment
         │
         ▼
      Signal
         │
         ▼
   Market Response
         │
         ▼
     Evaluation
         │
         └──────────────► Improve
```

---

## 🧠 What Are We Building?

The project will progressively evolve from a simple model experiment into a small end-to-end AI system.

### Stage 1 — NLP Experiment

Start with the smallest useful experiment:

**Financial text → FinBERT → sentiment prediction**

We first want to understand the model itself before introducing APIs, containers, or infrastructure.

### Stage 2 — Financial News Pipeline

Introduce real financial news and build the data-processing pipeline:

```text
News Sources
     │
     ▼
Collection
     │
     ▼
Cleaning
     │
     ▼
Normalization
     │
     ▼
Financial Text
```

### Stage 3 — Sentiment Signals

Turn individual predictions into a time-dependent signal.

For example:

```text
News Article 1 ──► +0.82
News Article 2 ──► +0.64
News Article 3 ──► -0.71
News Article 4 ──► +0.91
                     │
                     ▼
              Aggregate Signal
                     │
                     ▼
                 Market Data
```

### Stage 4 — Market Analysis

Investigate whether the resulting sentiment signal has a relationship with market behavior.

Possible questions include:

* Does positive news precede positive returns?
* Does negative sentiment precede negative returns?
* Does the relationship depend on the time horizon?
* Is the signal stronger for individual companies or broader indices?
* Does sentiment contain information beyond simple market momentum?
* Can a simple strategy based on the signal outperform a baseline?

These are **research questions**, not assumptions.

### Stage 5 — AI Inference API

Expose the sentiment model through **FastAPI**:

```text
                HTTP Request
                     │
                     ▼
             ┌──────────────┐
             │   FastAPI    │
             └──────┬───────┘
                    │
                    ▼
             ┌──────────────┐
             │   FinBERT    │
             └──────┬───────┘
                    │
                    ▼
              JSON Response
```

Example:

```json
{
  "text": "Company X reports stronger than expected earnings",
  "sentiment": "positive",
  "scores": {
    "negative": 0.03,
    "neutral": 0.12,
    "positive": 0.85
  }
}
```

### Stage 6 — Efficient LLM Inference

Experiment with **vLLM** where an LLM is useful for tasks beyond the specialized FinBERT classifier.

This gives us an opportunity to investigate an important engineering question:

> When should we use a specialized model such as FinBERT, and when does a general-purpose LLM make sense?

Rather than using an LLM everywhere, we will compare approaches based on **quality, latency, resource usage, and task suitability**.

### Stage 7 — Containerization

Package the system with **Docker** so that the environment and services become reproducible.

Eventually the architecture may look something like:

```text
                         ┌──────────────┐
                         │    Client    │
                         └──────┬───────┘
                                │
                                ▼
                         ┌──────────────┐
                         │   FastAPI    │
                         │      API     │
                         └──────┬───────┘
                                │
                    ┌───────────┴───────────┐
                    │                       │
                    ▼                       ▼
             ┌─────────────┐        ┌─────────────┐
             │   FinBERT   │        │    vLLM     │
             │ Classifier  │        │ LLM Server  │
             └─────────────┘        └─────────────┘
                    │                       │
                    └───────────┬───────────┘
                                ▼
                         Analysis Pipeline
                                │
                                ▼
                         Market Signals
```

---

# 🛠️ Technology Stack

| Technology               | Role                                        |
| ------------------------ | ------------------------------------------- |
| **Python**               | Main programming language                   |
| **Hugging Face**         | Models, tokenizers and NLP tooling          |
| **FinBERT**              | Financial-domain sentiment analysis         |
| **FastAPI**              | Serving the AI functionality through an API |
| **vLLM**                 | High-throughput LLM inference               |
| **Docker**               | Reproducible environments and deployment    |
| **Pandas / NumPy**       | Data processing and numerical analysis      |
| **SciPy / scikit-learn** | Statistical analysis and experimentation    |
| **Matplotlib**           | Visualization                               |
| **Git**                  | Version control and experiment history      |

The stack will evolve as the project evolves.

---

# 🗂️ Planned Project Structure

The repository will grow organically rather than creating unnecessary folders from day one.

A possible future structure is:

```text
financial-sentiment-pipeline/
│
├── data/
│   ├── raw/
│   └── processed/
│
├── notebooks/
│   └── experiments/
│
├── src/
│   ├── data/
│   ├── preprocessing/
│   ├── models/
│   ├── api/
│   ├── analysis/
│   └── utils/
│
├── tests/
│
├── docker/
│
├── README.md
├── requirements.txt
└── .gitignore
```

**Important:** this is a target architecture, not something we need to create immediately.

We will only introduce components when the project actually needs them.

---

# 🧪 Experimental Philosophy

This project is intentionally built **step by step**.

Each major component should answer a question.

For example:

```text
Question
   │
   ▼
Experiment
   │
   ▼
Implementation
   │
   ▼
Measurement
   │
   ▼
Conclusion
   │
   ▼
Next Decision
```

We care about things such as:

* Model performance
* Inference latency
* Resource consumption
* Data quality
* Signal quality
* Statistical significance
* Reproducibility
* Baseline comparisons
* Failure cases

The objective is therefore not simply:

> "I used FinBERT, FastAPI, vLLM and Docker."

Instead:

> "I experimented with different approaches, measured their behavior, understood their trade-offs, and integrated the useful components into an end-to-end system."

That is the engineering mindset this project is intended to demonstrate.

---

# 🗺️ Roadmap

The roadmap is intentionally flexible. We will update it as we learn.

* [ ] Create the initial Python environment
* [ ] Run the first FinBERT inference
* [ ] Understand tokenization and model outputs
* [ ] Build a minimal sentiment inference module
* [ ] Collect financial news
* [ ] Clean and preprocess the data
* [ ] Store structured news and sentiment data
* [ ] Obtain corresponding market data
* [ ] Align news timestamps with market observations
* [ ] Construct sentiment signals
* [ ] Analyze sentiment vs. market returns
* [ ] Establish simple baselines
* [ ] Perform basic backtesting
* [ ] Build a FastAPI inference service
* [ ] Experiment with vLLM
* [ ] Compare specialized models vs. LLM-based approaches
* [ ] Containerize the system with Docker
* [ ] Add tests and reproducibility improvements
* [ ] Improve the pipeline based on experimental results

---

# 📊 What Would Count as Success?

Success does **not** necessarily mean discovering a profitable trading strategy.

A successful project could demonstrate that:

1. Financial news can be processed automatically.
2. Financial sentiment can be extracted using a domain-specific model.
3. Sentiment can be transformed into a quantitative signal.
4. The signal can be aligned with financial market data.
5. We can rigorously evaluate whether the signal contains useful information.
6. The AI component can be exposed through a real API.
7. The system can be packaged and reproduced using Docker.
8. We understand the limitations and failure modes of the approach.

If the final conclusion is:

> **"Our sentiment signal does not provide meaningful predictive power under these experimental conditions."**

that is still a valuable result.

The experiment is more important than forcing a positive conclusion.

---

# 🚀 Current Status

**Project phase: 🟡 Initialization**

We are starting with the smallest possible experiment:

```text
Financial sentence
       │
       ▼
    FinBERT
       │
       ▼
Sentiment prediction
```

Everything else will be introduced only when we have a reason to introduce it.

---

## 🎯 The Bigger Goal

This project is an opportunity to explore the complete path from **AI model to AI system**:

```text
              MODEL
                │
                ▼
             INFERENCE
                │
                ▼
               API
                │
                ▼
            CONTAINER
                │
                ▼
             PIPELINE
                │
                ▼
             ANALYSIS
                │
                ▼
            EVALUATION
                │
                ▼
             ITERATION
```

**Turning financial news into measurable signals — and learning what happens along the way.**

