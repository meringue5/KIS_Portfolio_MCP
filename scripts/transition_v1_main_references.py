#!/usr/bin/env python3
"""Plan or apply the bounded local V1-reference transition for WI-048."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import duckdb

from kis_portfolio.services.v1_main_transition import transition_v1_reference_data


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", required=True, help="explicit local DuckDB path")
    parser.add_argument("--apply", action="store_true", help="write only control reference tables")
    args = parser.parse_args()
    path = Path(args.database).expanduser().resolve()
    connection = duckdb.connect(str(path), read_only=not args.apply)
    try:
        result = transition_v1_reference_data(connection, apply=args.apply)
    finally:
        connection.close()
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
