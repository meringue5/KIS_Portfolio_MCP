#!/usr/bin/env python3
"""Export governed V2 MotherDuck tables as schema-preserving Parquet files."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path

import duckdb
from dotenv import load_dotenv

from kis_portfolio.config import PROJECT_ROOT, get_data_dir, get_motherduck_database, get_motherduck_token
from kis_portfolio.services.v2_recovery import TABLES, export_v2_backup


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir")
    args = parser.parse_args()
    load_dotenv(PROJECT_ROOT / ".env")
    token = get_motherduck_token()
    if not token:
        raise RuntimeError("MOTHERDUCK_TOKEN is required")
    stamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    root = Path(args.output_dir).expanduser().resolve() if args.output_dir else get_data_dir() / "backup" / "v2-parquet" / stamp
    con = duckdb.connect(f"md:{get_motherduck_database()}?motherduck_token={token}")
    try:
        export_v2_backup(con, root, database=get_motherduck_database())
    finally:
        con.close()
    print(f"V2 backup written: {root}")
    print(f"tables={len(TABLES)} object_bytes_included=false")


if __name__ == "__main__":
    main()
