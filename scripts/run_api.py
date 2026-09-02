#!/usr/bin/env python3
"""Start the Financial Sentiment Pipeline FastAPI app.

Usage:
    python scripts/run_api.py            # default: 127.0.0.1:8000
    python scripts/run_api.py --port 9000
    python scripts/run_api.py --reload   # dev mode with auto-reload
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))


def _check_database() -> None:
    """Fail fast with an actionable message if PostgreSQL is unreachable."""
    try:
        from financial_sentiment.repository import Repository
        Repository().init()
    except Exception as exc:  # noqa: BLE001 - surface any connection error to user
        print("ERROR: could not connect to PostgreSQL.")
        print(f"  {exc}")
        print("Set DATABASE_URL in .env (see README 'Database (PostgreSQL)'),")
        print("or start a local instance with: python scripts/pg_server.py start")
        raise SystemExit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload (dev mode)")
    args = parser.parse_args()

    _check_database()

    import uvicorn
    uvicorn.run(
        "financial_sentiment.api.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        app_dir=str(ROOT / "src"),
    )


if __name__ == "__main__":
    main()
