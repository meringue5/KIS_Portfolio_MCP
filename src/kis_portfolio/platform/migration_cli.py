"""Explicit V2 migration CLI. It never falls back from MotherDuck to local."""

from __future__ import annotations

import argparse
from pathlib import Path

import duckdb

from kis_portfolio.platform.migrations import MigrationRunner


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply explicit KIS Portfolio V2 migrations")
    parser.add_argument("--database", required=True, help="DuckDB path or explicit md: connection string")
    parser.add_argument("--through")
    args = parser.parse_args()
    if not args.database.startswith("md:"):
        Path(args.database).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(args.database)
    try:
        executed = MigrationRunner(con).apply(through=args.through)
        print(f"V2 migrations applied: {executed or 'no-op'}")
    finally:
        con.close()


if __name__ == "__main__":
    main()
