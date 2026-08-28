#!/usr/bin/env python3
"""Restore a V2 Parquet manifest into a fresh local DuckDB and verify counts/views."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import duckdb

from kis_portfolio.db.catalog import v2_backup_table_names, v2_object_by_qualified_name
from kis_portfolio.platform.migrations import MigrationRunner


def _quote(path: Path) -> str:
    return "'" + str(path).replace("'", "''") + "'"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("backup_dir")
    parser.add_argument("--database", default=":memory:")
    args = parser.parse_args()
    backup_dir = Path(args.backup_dir).expanduser().resolve()
    manifest = json.loads((backup_dir / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("manifest_version") != 2:
        raise RuntimeError("unsupported V2 backup manifest")
    manifest_tables = set(manifest.get("tables", {}))
    expected_tables = set(v2_backup_table_names())
    if manifest_tables != expected_tables:
        missing = sorted(expected_tables - manifest_tables)
        extra = sorted(manifest_tables - expected_tables)
        raise RuntimeError(f"incomplete V2 backup manifest: missing={missing}, extra={extra}")
    if args.database != ":memory:":
        database_path = Path(args.database).expanduser().resolve()
        if database_path.exists():
            raise RuntimeError("restore target must not already exist")
        database_path.parent.mkdir(parents=True, exist_ok=True)
        connection_string = str(database_path)
    else:
        connection_string = ":memory:"
    allowed = v2_object_by_qualified_name()
    con = duckdb.connect(connection_string)
    restored = 0
    try:
        MigrationRunner(con).apply()
        for qualified, record in manifest["tables"].items():
            if qualified not in allowed or allowed[qualified].object_type != "table":
                raise RuntimeError(f"manifest contains unmanaged V2 table: {qualified}")
            path = backup_dir / record["path"]
            con.execute(f"INSERT INTO {qualified} SELECT * FROM read_parquet({_quote(path)})")
            actual = con.execute(f"SELECT count(*) FROM {qualified}").fetchone()[0]
            if actual != record["rows"]:
                raise RuntimeError(f"row-count mismatch for {qualified}: {actual} != {record['rows']}")
            restored += 1
        for qualified, item in allowed.items():
            if item.object_type == "view":
                con.execute(f"SELECT count(*) FROM {qualified}").fetchone()
    finally:
        con.close()
    print(f"V2 restore verified: tables={restored} target={args.database}")
    if not manifest.get("object_bytes_included"):
        print("warning: restricted/raw object bytes require a separate private object restore")


if __name__ == "__main__":
    main()
