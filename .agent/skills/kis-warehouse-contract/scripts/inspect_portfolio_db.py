#!/usr/bin/env python3
"""Inspect KIS Portfolio DuckDB/MotherDuck state without exposing secrets."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def repo_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "pyproject.toml").exists() and (parent / "src").exists():
            return parent
    raise RuntimeError("Could not locate repo root")


ROOT = repo_root()
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def load_env() -> None:
    try:
        from dotenv import load_dotenv
    except Exception:
        return
    load_dotenv(ROOT / ".env")


def row_dict(cursor, row) -> dict:
    return {desc[0]: value for desc, value in zip(cursor.description, row)}


def fetch_one(con, query: str) -> dict:
    cursor = con.execute(query)
    return row_dict(cursor, cursor.fetchone())


def fetch_all(con, query: str) -> list[dict]:
    cursor = con.execute(query)
    return [row_dict(cursor, row) for row in cursor.fetchall()]


def json_safe(value):
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def inspect() -> dict:
    load_env()
    import duckdb

    from kis_portfolio.db import get_connection
    from kis_portfolio.db.catalog import object_by_name, v2_object_by_qualified_name
    from kis_portfolio.db.schema import init_schema
    from kis_portfolio.platform.migrations import MigrationRunner

    con = get_connection()
    database = con.execute("SELECT current_database()").fetchone()[0]
    catalog = {f"main.{name}": item for name, item in object_by_name().items()}
    catalog.update(v2_object_by_qualified_name())
    object_rows = fetch_all(con, """
        SELECT t.table_catalog,
               t.table_schema,
               t.table_name,
               t.table_type,
               COUNT(c.column_name) AS column_count
        FROM information_schema.tables AS t
        LEFT JOIN information_schema.columns AS c
          ON c.table_catalog = t.table_catalog
         AND c.table_schema = t.table_schema
         AND c.table_name = t.table_name
        WHERE t.table_catalog = current_database()
          AND t.table_schema NOT IN ('information_schema', 'pg_catalog')
        GROUP BY t.table_catalog, t.table_schema, t.table_name, t.table_type
        ORDER BY t.table_schema, t.table_type, t.table_name
    """)
    column_rows = fetch_all(con, """
        SELECT table_schema,
               table_name,
               column_name,
               data_type,
               is_nullable,
               ordinal_position
        FROM information_schema.columns
        WHERE table_catalog = current_database()
          AND table_schema NOT IN ('information_schema', 'pg_catalog')
        ORDER BY table_schema, table_name, ordinal_position
    """)
    columns_by_object: dict[tuple[str, str], list[dict]] = {}
    for row in column_rows:
        columns_by_object.setdefault((row["table_schema"], row["table_name"]), []).append({
            "name": row["column_name"],
            "type": row["data_type"],
            "nullable": row["is_nullable"] == "YES",
        })

    expected_con = duckdb.connect(":memory:")
    try:
        init_schema(expected_con)
        MigrationRunner(expected_con).apply()
        expected_column_rows = fetch_all(expected_con, """
            SELECT table_schema,
                   table_name,
                   column_name,
                   data_type,
                   ordinal_position
            FROM information_schema.columns
            WHERE table_schema NOT IN ('information_schema', 'pg_catalog')
            ORDER BY table_name, ordinal_position
        """)
    finally:
        expected_con.close()
    expected_columns_by_object: dict[str, dict[str, str]] = {}
    for row in expected_column_rows:
        qualified = f"{row['table_schema']}.{row['table_name']}"
        expected_columns_by_object.setdefault(qualified, {})[row["column_name"]] = row["data_type"]

    inventory = []
    actual_managed_names = set()
    unmanaged_objects = []
    managed_column_drift = []
    for row in object_rows:
        qualified = f"{row['table_schema']}.{row['table_name']}"
        expected = catalog.get(qualified)
        actual_type = "view" if row["table_type"] == "VIEW" else "table"
        is_managed = bool(
            expected
            and row["table_schema"] == expected.physical_schema
            and actual_type == expected.object_type
        )
        actual_columns = columns_by_object.get((row["table_schema"], row["table_name"]), [])
        column_drift = None
        if is_managed:
            expected_columns = expected_columns_by_object.get(qualified, {})
            actual_column_types = {column["name"]: column["type"] for column in actual_columns}
            missing_columns = sorted(set(expected_columns) - set(actual_column_types))
            extra_columns = sorted(set(actual_column_types) - set(expected_columns))
            type_mismatches = sorted(
                f"{name}:{expected_columns[name]}!={actual_column_types[name]}"
                for name in set(expected_columns) & set(actual_column_types)
                if expected_columns[name] != actual_column_types[name]
            )
            if missing_columns or extra_columns or type_mismatches:
                column_drift = {
                    "schema": row["table_schema"],
                    "name": row["table_name"],
                    "missing_columns": missing_columns,
                    "extra_columns": extra_columns,
                    "type_mismatches": type_mismatches,
                }
                managed_column_drift.append(column_drift)
        item = {
            **row,
            "managed": is_managed,
            "logical_layer": expected.layer if is_managed else None,
            "target_schema": expected.target_schema if is_managed else None,
            "columns": actual_columns,
            "column_drift": column_drift,
        }
        inventory.append(item)
        if is_managed:
            actual_managed_names.add(qualified)
        else:
            unmanaged_objects.append({
                "schema": row["table_schema"],
                "name": row["table_name"],
                "type": actual_type,
            })

    missing_managed_objects = sorted(set(catalog) - actual_managed_names)
    tables = {
        "portfolio_snapshots": """
            SELECT COUNT(*) AS rows,
                   COUNT_IF(total_eval_amt IS NULL) AS null_total_eval_amt,
                   COUNT(DISTINCT account_type) AS account_types,
                   MAX(snapshot_at) AS latest_at
            FROM portfolio_snapshots
        """,
        "portfolio_daily_snapshots": """
            SELECT COUNT(*) AS rows,
                   COUNT_IF(total_eval_amt IS NULL) AS null_total_eval_amt,
                   COUNT(DISTINCT account_type) AS account_types,
                   MAX(snapshot_at) AS latest_at
            FROM portfolio_daily_snapshots
        """,
        "overseas_asset_snapshots": """
            SELECT COUNT(*) AS rows,
                   MAX(snapshot_at) AS latest_at,
                   ROUND(MAX(total_asset_amt_krw), 0) AS max_total_asset_amt_krw
            FROM overseas_asset_snapshots
        """,
        "asset_overview_snapshots": """
            SELECT COUNT(*) AS rows,
                   MAX(snapshot_at) AS latest_at,
                   ROUND(MAX(total_eval_amt_krw), 0) AS max_total_asset_krw
            FROM asset_overview_snapshots
        """,
        "asset_overview_daily_snapshots": """
            SELECT COUNT(*) AS rows,
                   MAX(snapshot_at) AS latest_at,
                   ROUND(MAX(total_eval_amt_krw), 0) AS max_total_asset_krw
            FROM asset_overview_daily_snapshots
        """,
        "asset_holding_snapshots": """
            SELECT COUNT(*) AS rows,
                   COUNT(DISTINCT exposure_type) AS exposure_types,
                   MAX(snapshot_at) AS latest_at
            FROM asset_holding_snapshots
        """,
        "instrument_master": """
            SELECT COUNT(*) AS rows,
                   COUNT(DISTINCT market) AS markets,
                   MAX(updated_at) AS latest_at
            FROM instrument_master
        """,
        "instrument_classification_overrides": """
            SELECT COUNT(*) AS rows,
                   COUNT(DISTINCT exposure_type) AS exposure_types,
                   MAX(updated_at) AS latest_at
            FROM instrument_classification_overrides
        """,
        "price_history": """
            SELECT COUNT(*) AS rows,
                   MAX(date) AS latest_market_date,
                   MAX(created_at) AS latest_at
            FROM price_history
        """,
        "exchange_rate_history": """
            SELECT COUNT(*) AS rows,
                   MAX(date) AS latest_rate_date,
                   MAX(created_at) AS latest_at
            FROM exchange_rate_history
        """,
        "trade_profit_history": """
            SELECT COUNT(*) AS rows,
                   MAX(fetched_at) AS latest_at
            FROM trade_profit_history
        """,
    }
    result = {
        "database": database,
        "inventory": inventory,
        "drift": {
            "missing_managed_objects": missing_managed_objects,
            "unmanaged_objects": unmanaged_objects,
            "managed_column_drift": managed_column_drift,
        },
        "tables": {name: fetch_one(con, query) for name, query in tables.items()},
    }
    result["portfolio_by_account_type"] = fetch_all(con, """
        SELECT account_type,
               COUNT(*) AS rows,
               COUNT_IF(total_eval_amt IS NULL) AS null_total_eval_amt,
               MAX(snapshot_at) AS latest_at
        FROM portfolio_snapshots
        GROUP BY account_type
        ORDER BY account_type
    """)
    result["daily_by_account_type"] = fetch_all(con, """
        SELECT account_type,
               COUNT(*) AS rows,
               MAX(snapshot_at) AS latest_at
        FROM portfolio_daily_snapshots
        GROUP BY account_type
        ORDER BY account_type
    """)
    result["overview_classification_counts"] = fetch_all(con, """
        SELECT exposure_type,
               COUNT(*) AS rows,
               ROUND(SUM(value_krw), 0) AS value_krw,
               MAX(snapshot_at) AS latest_at
        FROM asset_holding_snapshots
        GROUP BY exposure_type
        ORDER BY value_krw DESC NULLS LAST, exposure_type
    """)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    parser.add_argument(
        "--inventory",
        action="store_true",
        help="Print the current database object/column inventory and managed-object drift.",
    )
    parser.add_argument(
        "--fail-on-drift",
        action="store_true",
        help="Exit non-zero when managed objects are missing or live object/column drift exists.",
    )
    args = parser.parse_args()

    result = inspect()
    drift_found = any(result["drift"].values())
    if args.json:
        print(json.dumps(result, ensure_ascii=False, default=json_safe, indent=2))
        return int(args.fail_on_drift and drift_found)

    if args.inventory:
        print(f"KIS Portfolio DB inventory: database={result['database']}")
        for item in result["inventory"]:
            status = "managed" if item["managed"] else "UNMANAGED"
            layer = f", layer={item['logical_layer']}->{item['target_schema']}" if item["managed"] else ""
            print(
                f"- {item['table_schema']}.{item['table_name']}: "
                f"type={item['table_type']}, columns={item['column_count']}, status={status}{layer}"
            )
            columns = ", ".join(
                f"{column['name']}:{column['type']}{'' if column['nullable'] else '!'}"
                for column in item["columns"]
            )
            print(f"  columns: {columns}")
        print("drift")
        print(
            "  missing_managed_objects="
            + ",".join(result["drift"]["missing_managed_objects"])
        )
        print(
            "  unmanaged_objects="
            + ",".join(
                f"{item['schema']}.{item['name']}"
                for item in result["drift"]["unmanaged_objects"]
            )
        )
        print(
            "  managed_column_drift="
            + ";".join(
                f"{item['schema']}.{item['name']}"
                f"[missing={','.join(item['missing_columns'])};"
                f"extra={','.join(item['extra_columns'])};"
                f"types={','.join(item['type_mismatches'])}]"
                for item in result["drift"]["managed_column_drift"]
            )
        )
        return int(args.fail_on_drift and drift_found)

    print(f"KIS Portfolio DB inspection: database={result['database']}")
    for name, row in result["tables"].items():
        parts = ", ".join(f"{key}={json_safe(value)}" for key, value in row.items())
        print(f"- {name}: {parts}")
    print("portfolio_by_account_type")
    for row in result["portfolio_by_account_type"]:
        print("  - " + ", ".join(f"{key}={json_safe(value)}" for key, value in row.items()))
    print("drift")
    print(
        "  missing_managed_objects="
        + ",".join(result["drift"]["missing_managed_objects"])
    )
    print(
        "  unmanaged_objects="
        + ",".join(
            f"{item['schema']}.{item['name']}"
            for item in result["drift"]["unmanaged_objects"]
        )
    )
    print(
        "  managed_column_drift="
        + ";".join(
            f"{item['schema']}.{item['name']}"
            f"[missing={','.join(item['missing_columns'])};"
            f"extra={','.join(item['extra_columns'])};"
            f"types={','.join(item['type_mismatches'])}]"
            for item in result["drift"]["managed_column_drift"]
        )
    )
    return int(args.fail_on_drift and drift_found)


if __name__ == "__main__":
    raise SystemExit(main())
