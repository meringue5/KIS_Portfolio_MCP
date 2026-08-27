"""Explicit V2 migration CLI. It never falls back from MotherDuck to local."""

from __future__ import annotations

import argparse
from pathlib import Path

import duckdb
from dotenv import load_dotenv

from kis_portfolio.config import PROJECT_ROOT, get_motherduck_database, get_motherduck_token
from kis_portfolio.platform.migrations import MigrationRunner


def main() -> None:
    load_dotenv(PROJECT_ROOT / ".env")
    parser = argparse.ArgumentParser(description="Apply explicit KIS Portfolio V2 migrations")
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--database", help="local DuckDB path")
    target.add_argument("--motherduck", action="store_true", help="use configured MotherDuck DB/token without exposing the token in argv")
    parser.add_argument("--through")
    args = parser.parse_args()
    if args.motherduck:
        token = get_motherduck_token()
        if not token:
            raise RuntimeError("--motherduck requires MOTHERDUCK_TOKEN")
        database = get_motherduck_database()
        connection_string = f"md:{database}?motherduck_token={token}"
        target_label = f"md:{database}"
    else:
        path = Path(args.database).expanduser().resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        connection_string = str(path)
        target_label = str(path)
    con = duckdb.connect(connection_string)
    try:
        executed = MigrationRunner(con).apply(through=args.through)
        print(f"V2 migrations target={target_label} applied: {executed or 'no-op'}")
    finally:
        con.close()


if __name__ == "__main__":
    main()
