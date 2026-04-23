#!/usr/bin/env python3
"""Back up MotherDuck tables to local Parquet files.

The backup target is intentionally file-based and append-free: each run writes a
timestamped directory under ``var/backup/parquet`` by default. Parquet keeps the
backup portable for DuckDB, pandas, and future analytics workflows.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import duckdb
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from kis_portfolio.config import (  # noqa: E402
    get_data_dir,
    get_motherduck_database,
    get_motherduck_token,
    resolve_project_path,
)


TABLES = (
    "price_history",
    "exchange_rate_history",
    "portfolio_snapshots",
    "overseas_asset_snapshots",
    "asset_overview_snapshots",
    "asset_holding_snapshots",
    "instrument_master",
    "instrument_classification_overrides",
    "order_history",
    "trade_profit_history",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export MotherDuck portfolio tables to timestamped Parquet backups."
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Backup root directory. Relative paths are resolved from the project root. Default: var/backup/parquet",
    )
    parser.add_argument(
        "--database",
        default=None,
        help="MotherDuck database name. Default: MOTHERDUCK_DATABASE or kis_portfolio",
    )
    parser.add_argument(
        "--keep",
        type=int,
        default=0,
        help="Keep only the most recent N backup directories. Default 0 keeps all backups.",
    )
    return parser.parse_args()


def quote_sql_string(value: Path) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def backup_tables(con: duckdb.DuckDBPyConnection, output_dir: Path) -> dict:
    output_dir.mkdir(parents=True, exist_ok=False)
    manifest = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "format": "parquet",
        "tables": {},
    }

    for table in TABLES:
        row_count = con.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
        parquet_path = output_dir / f"{table}.parquet"
        con.execute(
            f"COPY (SELECT * FROM {table}) TO {quote_sql_string(parquet_path)} (FORMAT PARQUET)"
        )
        manifest["tables"][table] = {
            "rows": row_count,
            "path": parquet_path.name,
        }

    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    return manifest


def prune_old_backups(backup_root: Path, keep: int) -> list[Path]:
    if keep <= 0:
        return []

    backups = sorted(
        [path for path in backup_root.iterdir() if path.is_dir()],
        key=lambda path: path.name,
        reverse=True,
    )
    removed = []
    for path in backups[keep:]:
        for child in path.iterdir():
            child.unlink()
        path.rmdir()
        removed.append(path)
    return removed


def main() -> int:
    load_dotenv(ROOT / ".env")
    args = parse_args()

    token = get_motherduck_token()
    if not token:
        print("MOTHERDUCK_TOKEN is required for backup.", file=sys.stderr)
        return 2

    database = args.database or get_motherduck_database()
    backup_root = resolve_project_path(args.output_dir, get_data_dir() / "backup" / "parquet")
    run_dir = backup_root / datetime.now().strftime("%Y%m%d_%H%M%S")

    conn_str = f"md:{database}?motherduck_token={token}"
    con = duckdb.connect(conn_str)
    try:
        manifest = backup_tables(con, run_dir)
    finally:
        con.close()

    removed = prune_old_backups(backup_root, args.keep)

    print(f"Backup written: {run_dir}")
    for table, info in manifest["tables"].items():
        print(f"- {table}: {info['rows']} rows -> {info['path']}")
    if removed:
        print("Pruned old backups:")
        for path in removed:
            print(f"- {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
