"""FastAPI application entry point."""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from ..repository import Repository
from .routes import (
    analysis_router,
    backtest_router,
    equities_router,
    pipeline_router,
)

STATIC_DIR = Path(__file__).resolve().parent / "static"


@asynccontextmanager
async def _lifespan(app: FastAPI):
    # Ensure the schema exists. It is idempotent and every write is an
    # upsert, so restarting the app never clobbers data.
    Repository().init()
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="Financial Sentiment Pipeline",
        description="Fetch, score, and analyze financial news sentiment.",
        version="0.1.0",
        lifespan=_lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(equities_router)
    app.include_router(pipeline_router)
    app.include_router(analysis_router)
    app.include_router(backtest_router)

    if STATIC_DIR.is_dir():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

        @app.get("/")
        def index() -> FileResponse:
            return FileResponse(str(STATIC_DIR / "index.html"))

        @app.get("/analysis.html")
        def analysis_page() -> FileResponse:
            return FileResponse(str(STATIC_DIR / "analysis.html"))

    return app


app = create_app()
