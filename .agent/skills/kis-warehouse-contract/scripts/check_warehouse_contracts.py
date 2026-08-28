#!/usr/bin/env python3
"""Check DuckDB/MotherDuck schema and repository contracts."""

from __future__ import annotations

import re
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

from kis_portfolio.db.catalog import (  # noqa: E402
    DATA_OBJECTS,
    V2_DATA_OBJECTS,
    backup_table_names,
    v2_backup_table_names,
)


def text(path: str) -> str:
    return (ROOT / path).read_text()


def function_block(source: str, name: str) -> str:
    start = source.find(f"def {name}")
    if start < 0:
        return ""
    next_def = source.find("\ndef ", start + 1)
    if next_def < 0:
        return source[start:]
    return source[start:next_def]


def main() -> int:
    failures: list[str] = []
    schema = text("src/kis_portfolio/db/schema.py")
    repo = text("src/kis_portfolio/db/repository.py")
    backup = text("scripts/backup_motherduck.py")
    v2_backup = text("scripts/backup_v2_motherduck.py")
    docs = text("docs/data-pipeline.md") + "\n" + text("docs/backup.md")
    catalog_doc = text("docs/data-catalog.md")
    v2_migrations = "\n".join(
        path.read_text()
        for path in sorted((ROOT / "src/kis_portfolio/platform/sql").glob("*.sql"))
    )

    schema_tables = set(re.findall(
        r"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+([a-zA-Z_][a-zA-Z0-9_]*)",
        schema,
        flags=re.IGNORECASE,
    ))
    schema_views = set(re.findall(
        r"CREATE\s+OR\s+REPLACE\s+VIEW\s+([a-zA-Z_][a-zA-Z0-9_]*)",
        schema,
        flags=re.IGNORECASE,
    ))
    catalog_tables = {item.name for item in DATA_OBJECTS if item.object_type == "table"}
    catalog_views = {item.name for item in DATA_OBJECTS if item.object_type == "view"}

    if len(DATA_OBJECTS) != len({item.name for item in DATA_OBJECTS}):
        failures.append("catalog registry contains duplicate object names")
    if schema_tables != catalog_tables:
        failures.append(
            "schema/catalog table mismatch: "
            f"schema_only={sorted(schema_tables - catalog_tables)}, "
            f"catalog_only={sorted(catalog_tables - schema_tables)}"
        )
    if schema_views != catalog_views:
        failures.append(
            "schema/catalog view mismatch: "
            f"schema_only={sorted(schema_views - catalog_views)}, "
            f"catalog_only={sorted(catalog_views - schema_views)}"
        )

    if len(V2_DATA_OBJECTS) != len({item.qualified_name for item in V2_DATA_OBJECTS}):
        failures.append("V2 catalog registry contains duplicate qualified object names")
    for item in V2_DATA_OBJECTS:
        if item.physical_schema != item.layer or item.target_schema != item.layer:
            failures.append(f"invalid V2 physical/layer schema for {item.qualified_name}")
        if item.object_type == "table":
            marker = f"CREATE TABLE IF NOT EXISTS {item.qualified_name}"
        else:
            marker = f"CREATE OR REPLACE VIEW {item.qualified_name}"
        if marker.lower() not in v2_migrations.lower():
            failures.append(f"V2 migration missing catalog object: {item.qualified_name}")
        if f"`{item.qualified_name}`" not in catalog_doc:
            failures.append(f"data catalog document missing V2 object: {item.qualified_name}")

    valid_layers = {"bronze", "silver", "gold", "control", "security"}
    valid_sensitivity = {"internal", "confidential", "restricted"}
    for item in DATA_OBJECTS:
        if item.layer not in valid_layers or item.target_schema != item.layer:
            failures.append(f"invalid layer/target schema for catalog object: {item.name}")
        if item.sensitivity not in valid_sensitivity:
            failures.append(f"invalid sensitivity for catalog object: {item.name}")
        if f"`{item.name}`" not in catalog_doc:
            failures.append(f"data catalog document missing managed object: {item.name}")

    for table in [
        "portfolio_snapshots",
        "overseas_asset_snapshots",
        "asset_overview_snapshots",
        "asset_holding_snapshots",
        "market_calendar",
        "instrument_master",
        "instrument_classification_overrides",
        "order_history",
        "trade_profit_history",
        "price_history",
        "exchange_rate_history",
    ]:
        if table not in schema:
            failures.append(f"schema missing table/view reference: {table}")
        if table not in docs:
            failures.append(f"pipeline/backup docs missing table: {table}")

    if "TABLES = backup_table_names()" not in backup:
        failures.append("backup script must derive TABLES from the governed data catalog")
    if "TABLES = v2_backup_table_names()" not in v2_backup:
        failures.append("V2 backup script must derive TABLES from the governed V2 data catalog")
    backup_doc = text("docs/backup.md")
    for table in backup_table_names():
        if table not in backup_doc:
            failures.append(f"backup docs missing catalog-approved table: {table}")
    for table in v2_backup_table_names():
        if table not in backup_doc:
            failures.append(f"backup docs missing V2 catalog-approved object: {table}")

    if "CREATE OR REPLACE VIEW portfolio_daily_snapshots" not in schema:
        failures.append("schema must define portfolio_daily_snapshots curated view")
    if "CREATE OR REPLACE VIEW asset_overview_daily_snapshots" not in schema:
        failures.append("schema must define asset_overview_daily_snapshots curated view")

    portfolio_insert = function_block(repo, "insert_portfolio_snapshot")
    if "INSERT INTO portfolio_snapshots" not in portfolio_insert:
        failures.append("insert_portfolio_snapshot must append INSERT INTO portfolio_snapshots")
    if "OR REPLACE" in portfolio_insert.upper() or "ON CONFLICT" in portfolio_insert.upper():
        failures.append("portfolio_snapshots insert must not replace/upsert raw observations")

    trade_insert = function_block(repo, "insert_trade_profit")
    if "INSERT INTO trade_profit_history" not in trade_insert:
        failures.append("insert_trade_profit must append INSERT INTO trade_profit_history")
    if "OR REPLACE" in trade_insert.upper() or "ON CONFLICT" in trade_insert.upper():
        failures.append("trade_profit_history insert must not replace/upsert raw observations")

    order_insert = function_block(repo, "insert_order_history")
    if "INSERT INTO order_history" not in order_insert:
        failures.append("insert_order_history must append INSERT INTO order_history")
    if "OR REPLACE" in order_insert.upper() or "ON CONFLICT" in order_insert.upper():
        failures.append("order_history insert must not replace/upsert raw observations")

    if "INSERT OR IGNORE INTO price_history" not in repo:
        failures.append("price_history should retain INSERT OR IGNORE cache semantics")
    if "INSERT OR IGNORE INTO exchange_rate_history" not in repo:
        failures.append("exchange_rate_history should retain INSERT OR IGNORE cache semantics")
    for function_name, table in [
        ("insert_overseas_asset_snapshot", "overseas_asset_snapshots"),
        ("insert_asset_overview_snapshot", "asset_overview_snapshots"),
        ("upsert_market_calendar_rows", "market_calendar"),
    ]:
        block = function_block(repo, function_name)
        if f"INSERT INTO {table}" not in block:
            failures.append(f"{function_name} must append INSERT INTO {table}")
    if "ON CONFLICT (market, trade_date) DO UPDATE" not in function_block(repo, "upsert_market_calendar_rows"):
        failures.append("market_calendar should retain upsert semantics keyed by market/date")

    schema_lower = schema.lower()
    forbidden_secret_columns = ["access_token", "app_secret", "appsecret", "kis_app_secret"]
    for marker in forbidden_secret_columns:
        if re.search(rf"\b{re.escape(marker)}\b", schema_lower):
            failures.append(f"schema contains forbidden secret marker: {marker}")

    if failures:
        print("Warehouse contract check failed:")
        for item in failures:
            print(f"- {item}")
        return 1

    print("Warehouse contract check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
