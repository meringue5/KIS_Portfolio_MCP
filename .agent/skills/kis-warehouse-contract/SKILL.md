---
name: kis-warehouse-contract
description: Use when changing DuckDB or MotherDuck schemas, the governed data catalog, repositories, analytics SQL, snapshots, order/profit storage, backups, auth/token metadata, or data pipeline docs.
---

# KIS Warehouse Contract

Use this skill for DB schema, repository, analytics, backup, and pipeline changes.

## Workflow

1. Read `docs/data-catalog.md` first. It owns object purpose, grain, logical layer, sensitivity, backup policy, and the physical schema migration plan.
2. Read `docs/data-pipeline.md`, `docs/backup.md`, `docs/security-and-secrets.md` when the change touches their responsibility, plus relevant `src/kis_portfolio/db/` files.
3. Run:

   ```bash
   uv run python .agent/skills/kis-warehouse-contract/scripts/check_warehouse_contracts.py
   ```

4. For live DB inspection, run the bundled client. It prints table counts,
   latest timestamps, account types, and null aggregate counts without account ids
   or secrets:

   ```bash
   uv run python .agent/skills/kis-warehouse-contract/scripts/inspect_portfolio_db.py
   ```

   For the complete current-database object/column catalog and drift report:

   ```bash
   uv run python .agent/skills/kis-warehouse-contract/scripts/inspect_portfolio_db.py --inventory
   ```

   After known branch/live drift is reconciled, use `--fail-on-drift` in release checks.

5. Run DB/analytics tests:

   ```bash
   uv run pytest tests/test_analytics.py tests/test_package_smoke.py
   ```

6. Update the machine registry, DDL/migration, repository tests, and owning docs together.

## Rules

- `src/kis_portfolio/db/catalog.py` is the machine-readable allowlist. No managed table or view may exist in DDL without a catalog entry.
- `docs/data-catalog.md` is the human governance authority. Other docs link to it instead of maintaining competing full inventories.
- Always scope MotherDuck inspection by `table_catalog=current_database()` and schema. A `main`-only filter mixes attached databases and shared datasets.
- Current physical objects remain in `main` until the versioned migration plan is implemented. New designs must declare one target: `bronze`, `silver`, `gold`, `control`, or `security`.
- Objects found only in the live database are drift. Report them; do not adopt, query, back up, or delete them until ownership and contract are established.
- `portfolio_snapshots`, `order_history`, and `trade_profit_history` are append-only raw observations.
- `overseas_asset_snapshots` is append-only overseas raw/aggregate feeder storage.
- `asset_overview_snapshots` is the canonical total-asset aggregate store.
- `asset_holding_snapshots` is the normalized holding row store for canonical snapshots.
- `market_calendar` is an upserted control/reference table for market open/close decisions.
- `price_history` and `exchange_rate_history` are cache tables with insert-ignore/upsert behavior.
- Curated views and analytics must not mutate raw tables.
- `asset_overview_daily_snapshots` must remain derived from canonical snapshots, not ad hoc recomputation.
- Raw token values and app secrets must never enter MotherDuck tables. If token cache is stored in DB, it must use a dedicated encrypted cache table and never leak via analytics tables, logs, or MCP responses.
- Parquet backup tables must be derived from the governed catalog and the backup docs must stay aligned.

## References

- Read `references/warehouse-contracts.md` for the current DB contract.
