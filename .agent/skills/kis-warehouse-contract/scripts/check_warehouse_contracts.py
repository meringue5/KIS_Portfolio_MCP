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
    docs = text("docs/data-pipeline.md") + "\n" + text("docs/backup.md")

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
        if table not in backup:
            failures.append(f"backup script missing table: {table}")
        if table not in docs:
            failures.append(f"pipeline/backup docs missing table: {table}")

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
