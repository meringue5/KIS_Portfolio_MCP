#!/usr/bin/env python3
"""Export governed V2 MotherDuck tables as schema-preserving Parquet files."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

import duckdb
from dotenv import load_dotenv

from kis_portfolio.config import PROJECT_ROOT, get_data_dir, get_motherduck_database, get_motherduck_token
from kis_portfolio.db.catalog import v2_backup_table_names


TABLES = v2_backup_table_names()


def _quote(path: Path) -> str:
    return "'" + str(path).replace("'", "''") + "'"


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
    root.mkdir(parents=True, exist_ok=False)
    con = duckdb.connect(f"md:{get_motherduck_database()}?motherduck_token={token}")
    manifest: dict[str, object] = {
        "manifest_version": 2,
        "created_at": datetime.now(UTC).isoformat(),
        "database": get_motherduck_database(),
        "tables": {},
        "object_bytes_included": False,
    }
    try:
        for qualified in TABLES:
            schema, table = qualified.split(".", 1)
            directory = root / schema
            directory.mkdir(exist_ok=True)
            path = directory / f"{table}.parquet"
            rows = con.execute(f"SELECT count(*) FROM {qualified}").fetchone()[0]
            con.execute(f"COPY (SELECT * FROM {qualified}) TO {_quote(path)} (FORMAT PARQUET)")
            manifest["tables"][qualified] = {"rows": rows, "path": f"{schema}/{table}.parquet"}
    finally:
        con.close()
    (root / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"V2 backup written: {root}")
    print(f"tables={len(TABLES)} object_bytes_included=false")


if __name__ == "__main__":
    main()
