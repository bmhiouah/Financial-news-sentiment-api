# syntax=docker/dockerfile:1
#
# Financial Sentiment Pipeline - API + CLI image.
#
#   docker build -f config/Dockerfile -t financial-sentiment .
#   docker compose up --build
#
# The image runs the FastAPI app (`/`, `/docs`, `/analysis.html`). The same image
# also serves as the CLI: `docker compose run --rm api financial-sentiment --help`.

FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HOME=/home/app \
    # FinBERT weights (~440 MB) are downloaded on first use; mount a volume here
    # so they survive container restarts.
    HF_HOME=/home/app/.cache/huggingface

WORKDIR /app

# curl = container healthcheck, libpq5 = runtime library for psycopg.
RUN apt-get update \
 && apt-get install --no-install-recommends -y curl libpq5 \
 && rm -rf /var/lib/apt/lists/*

# Install dependencies first: this layer is cached and only rebuilds when
# config/requirements.txt changes, not on every code edit. The manifest lands
# as ./requirements.txt inside the image, so the pip command below is unchanged.
COPY config/requirements.txt ./
# CPU-only torch. Pulling torch from PyPI instead drags in ~2 GB of CUDA
# libraries that a CPU-only inference container never uses. Keep the version in
# sync with config/requirements.txt.
RUN pip install "torch==2.13.0" --index-url https://download.pytorch.org/whl/cpu \
 && pip install -r requirements.txt

# OpenBB generates its command tree (`obb.news`, `obb.equity`, ...) at install
# time into site-packages/openbb/package. It has to succeed here, while root
# still owns site-packages. Without this check a missing package only shows up
# at runtime as "'App' object has no attribute 'news'".
RUN python -c "from openbb import obb; assert hasattr(obb, 'news'); assert hasattr(obb, 'equity')"

# Install the package itself. --no-deps because config/requirements.txt already pinned
# the runtime dependencies, and re-resolving them here could upgrade torch back
# to the CUDA build. The installed `financial-sentiment` console script is the
# image's CLI; scripts/ also holds a launcher for running from a plain checkout.
COPY pyproject.toml ./
COPY financial_sentiment ./financial_sentiment
COPY scripts ./scripts
RUN pip install --no-deps .

# The command tree is baked into the image now, so stop OpenBB from trying to
# regenerate it at import time (which would need write access to site-packages).
# Must come after the install above: setting it earlier skips the build entirely.
ENV OPENBB_AUTO_BUILD=false

# Non-root user. OpenBB reads its provider API keys from
# $HOME/.openbb_platform/user_settings.json, which docker-compose bind-mounts
# from the host.
RUN useradd --create-home --uid 10001 app \
 && mkdir -p "$HF_HOME" \
 && chown -R app:app /app "$HOME"
USER app

EXPOSE 8000

# Repository.init() runs at startup, so /pipeline/status only answers once the
# database is reachable and the schema exists.
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/pipeline/status || exit 1

CMD ["uvicorn", "financial_sentiment.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
