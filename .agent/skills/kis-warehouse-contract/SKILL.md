---
name: kis-warehouse-contract
description: Use when changing DuckDB or MotherDuck schemas, repositories, analytics SQL, portfolio snapshots, price/exchange history, trade profit storage, backups, token audit metadata, or data pipeline docs.
---

# KIS Warehouse Contract

Use this skill for DB schema, repository, analytics, backup, and pipeline changes.

## Workflow

1. Read `docs/data-pipeline.md`, `docs/backup.md`, and relevant `src/kis_portfolio/db/` files.
2. Run:

   ```bash
   uv run python .agent/skills/kis-warehouse-contract/scripts/check_warehouse_contracts.py
   ```

3. For live DB inspection, run the bundled client. It prints table counts,
   latest timestamps, account types, and null aggregate counts without account ids
   or secrets:

   ```bash
   uv run python .agent/skills/kis-warehouse-contract/scripts/inspect_portfolio_db.py
   ```

4. Run DB/analytics tests:

   ```bash
   uv run pytest tests/test_analytics.py tests/test_package_smoke.py
   ```

5. Update docs whenever schema, view, backup, or repository behavior changes.

## Rules

- `portfolio_snapshots`, `order_history`, and `trade_profit_history` are append-only raw observations.
- `overseas_asset_snapshots` is append-only overseas raw/aggregate feeder storage.
- `asset_overview_snapshots` is the canonical total-asset aggregate store.
- `asset_holding_snapshots` is the normalized holding row store for canonical snapshots.
- `market_calendar` is an upserted control/reference table for market open/close decisions.
- `price_history` and `exchange_rate_history` are cache tables with insert-ignore/upsert behavior.
- Curated views and analytics must not mutate raw tables.
- `asset_overview_daily_snapshots` must remain derived from canonical snapshots, not ad hoc recomputation.
- Raw token values and app secrets must never enter MotherDuck tables. If token cache is stored in DB, it must use a dedicated encrypted cache table and never leak via analytics tables, logs, or MCP responses.
- Parquet backup docs and backup script must stay aligned with core tables.

## References

- Read `references/warehouse-contracts.md` for the current DB contract.
