"""FastAPI application entry point."""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .routes import (
    analysis_router,
    backtest_router,
    equities_router,
    pipeline_router,
)


_STATIC_DIR = Path(__file__).resolve().parent.parent.parent.parent / "api" / "static"


def create_app() -> FastAPI:
    app = FastAPI(
        title="Financial Sentiment Pipeline",
        description="Fetch, score, and analyze financial news sentiment.",
        version="0.1.0",
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

    if _STATIC_DIR.is_dir():
        app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

        @app.get("/")
        def index() -> FileResponse:
            return FileResponse(str(_STATIC_DIR / "index.html"))

        @app.get("/analysis.html")
        def analysis_page() -> FileResponse:
            return FileResponse(str(_STATIC_DIR / "analysis.html"))

    return app


app = create_app()
