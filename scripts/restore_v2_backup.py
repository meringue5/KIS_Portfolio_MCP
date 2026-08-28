#!/usr/bin/env python3
"""Restore a V2 Parquet manifest into a fresh local DuckDB and verify counts/views."""

from __future__ import annotations

import argparse
from pathlib import Path

from kis_portfolio.services.v2_recovery import restore_v2_backup


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("backup_dir")
    parser.add_argument("--database", default=":memory:")
    args = parser.parse_args()
    result = restore_v2_backup(
        Path(args.backup_dir),
        args.database if args.database == ":memory:" else Path(args.database),
    )
    print(f"V2 restore verified: tables={result['tables']} target={args.database}")
    if not result["object_bytes_included"]:
        print("warning: restricted/raw object bytes require a separate private object restore")


if __name__ == "__main__":
    main()
