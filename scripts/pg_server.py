#!/usr/bin/env python3
"""Manage the bundled local PostgreSQL instance used for development.

The server is provided by the `pgserver` pip package, which ships real
PostgreSQL binaries inside a wheel (no system install, no Docker). The data
directory lives outside the repo (~/.financial_sentiment/pgdata) so paths
with spaces (e.g. "Applied Entretiens") never reach pg_ctl, and the server
survives independent of this repository.

Commands:
    start     ensure the server is running and the `financial_sentiment` DB exists
    stop      stop the server
    status    print whether the server is up and its DATABASE_URL
    uri       print the connection string for the app database
    psql SQL  run a query via the bundled psql
"""
import argparse
import os
from pathlib import Path

from _bootstrap import add_root_to_path

# Allow running as `python scripts/pg_server.py` from the project root.
add_root_to_path()

import pgserver  # noqa: E402
import psycopg    # noqa: E402

DEFAULT_PGDATA = Path.home() / ".financial_sentiment" / "pgdata"
DB_NAME = "financial_sentiment"


def _server(pgdata: Path) -> "pgserver.PostgresServer":
    # cleanup_mode=None keeps the server alive after this process exits so it can
    # be reached by the API / migration in later tool calls.
    return pgserver.get_server(str(pgdata), cleanup_mode=None)


def _app_uri(pgdata: Path) -> str:
    return f"postgresql://postgres:@/{DB_NAME}?host={pgdata}"


def _remove_stale_pid(pgdata: Path) -> None:
    """Drop a postmaster.pid left behind by a crashed server."""
    pid = pgdata / "postmaster.pid"
    if not pid.exists():
        return
    try:
        lines = pid.read_text().splitlines()
        if not lines:
            pid.unlink(missing_ok=True)
            return
        pid_num = int(lines[0])
        os.kill(pid_num, 0)  # raises ProcessLookupError if the process is dead
    except (ProcessLookupError, ValueError, PermissionError, OSError):
        pid.unlink(missing_ok=True)


def cmd_start(args) -> int:
    pgdata = Path(args.pgdata)
    _remove_stale_pid(pgdata)
    s = _server(pgdata)
    s.ensure_pgdata_inited()
    s.ensure_postgres_running()
    # Create the application database if it does not exist yet.
    admin_uri = s.get_uri()  # maintenance `postgres` database
    with psycopg.connect(admin_uri) as conn:
        conn.autocommit = True
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (DB_NAME,))
        if not cur.fetchone():
            cur.execute(f'CREATE DATABASE "{DB_NAME}"')
    print("PostgreSQL is running.")
    print(f"DATABASE_URL={_app_uri(pgdata)}")
    return 0


def cmd_stop(args) -> int:
    s = _server(Path(args.pgdata))
    s.cleanup()
    print("PostgreSQL stopped.")
    return 0


def cmd_status(args) -> int:
    pgdata = Path(args.pgdata)
    uri = _app_uri(pgdata)
    try:
        with psycopg.connect(uri) as conn:
            conn.execute("SELECT 1")
        up = True
    except Exception:
        up = False
    print("status:", "running" if up else "stopped")
    print(f"DATABASE_URL={uri}")
    return 0 if up else 1


def cmd_uri(args) -> int:
    print(_app_uri(Path(args.pgdata)))
    return 0


def cmd_psql(args) -> int:
    s = _server(Path(args.pgdata))
    s.ensure_postgres_running()
    print(s.psql(args.command))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--pgdata", default=str(DEFAULT_PGDATA),
        help="PostgreSQL data directory (default: ~/.financial_sentiment/pgdata)",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("start", "stop", "status", "uri"):
        sub.add_parser(name)
    p = sub.add_parser("psql")
    p.add_argument("command", help="SQL to run")
    args = parser.parse_args()
    return globals()[f"cmd_{args.command}"](args)


if __name__ == "__main__":
    raise SystemExit(main())
