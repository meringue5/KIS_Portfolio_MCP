"""Read-only, redacted preview of scheduled owner-report readiness.

Example: .venv/bin/python scripts/check_owner_report_readiness.py 2026-09-17 kr-1000
This command never creates a pipeline run or contacts Telegram/KIS.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path

import duckdb
from dotenv import dotenv_values


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from kis_portfolio.services.total_asset_digest import inspect_owner_report_readiness  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("logical_date", type=date.fromisoformat)
    parser.add_argument("slot", choices=("kr-1000", "kr-1600"))
    parser.add_argument("--local-db", type=Path, help="Read-only local fixture DB instead of MotherDuck")
    args = parser.parse_args()
    if args.local_db:
        connection_target = str(args.local_db.resolve())
    else:
        file_values = dotenv_values(PROJECT_ROOT / ".env")
        database = os.environ.get("MOTHERDUCK_DATABASE") or file_values.get("MOTHERDUCK_DATABASE")
        token = os.environ.get("MOTHERDUCK_TOKEN") or file_values.get("MOTHERDUCK_TOKEN")
        if not database or not token:
            print(json.dumps({"status": "connection_unavailable", "send_attempted": False}))
            return 2
        connection_target = f"md:{database}?motherduck_token={token}"
    try:
        connection = duckdb.connect(connection_target, read_only=True)
        try:
            result = inspect_owner_report_readiness(
                connection, logical_date=args.logical_date, slot=args.slot,
            )
        finally:
            connection.close()
    except (duckdb.Error, ValueError):
        print(json.dumps({"status": "inspection_failed", "send_attempted": False}))
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["status"] in {"ready", "ready_partial"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
