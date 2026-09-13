# WI-048 isolated V1 main-consumer transition evidence

Date: 2026-09-13 KST
Scope: repository, fixture and local verification only
Production effects: none

## Outcome

V2 runtime no longer uses `main` as a reference, price or FX fallback. Migration `0019` owns the market calendar,
instrument master and owner-approved classification overrides in `control`. Existing V2 `silver.price_bars_daily` and
`silver.fx_rates_daily` remain the only governed historical price/FX stores.

The transition helper is preservation-first: its default is a counts-only plan, apply is explicit, source rows are
never updated or deleted, target writes are idempotent, and source-minus-target reconciliation must be zero before
commit. `governance/project/v1-main-transition.toml` denies both production apply and deletion in this isolated stage
and records the restore action for every copied object.

## Read-only live inventory

The warehouse inventory was read without changing MotherDuck. It reported no missing managed V2 objects. The retained
unmanaged V1 objects were `main.cash_flow` (0 rows), `main.trade_journal` (0 rows), and the broken zero-row
`main.asset_return_daily` view. The known V1 `main.asset_overview_daily_snapshots` quality-column drift was also still
present. These are archive/disposition evidence, not V2 objects, and WI-048 did not adopt, repair, or delete them.

## Local verification

- migration `0019` fresh apply and no-op rerun
- counts-only plan with zero writes
- explicit fixture copy with all source rows preserved
- source-minus-target reconciliation of zero for all three reference tables
- identical second apply with no duplicates
- all three target tables present in the V2 complete Parquet backup allowlist
- version-aware fresh recovery through migration `0019`
- affected runtime and transition suite: 38 passed
- transition plus recovery suite: 6 passed
- repository quick gate: passed, including Project OS, data governance, architecture, warehouse and exact 18-tool MCP
  surface checks
- repository full gate: 674 passed with one existing Authlib deprecation warning

## Production stop line

This evidence does not authorize a live migration or copy. Production completion still requires a private pre-backup,
explicit migration `0019`, counts-only plan review, bounded copy/reconciliation, external-consumer zero-use evidence,
post-backup/fresh restore and the full repository gate. Any mismatch leaves V2 serving fail-closed at the schema-version
gate. No V1 table, view, backup, history, Cloud Run resource, Scheduler, IAM role or secret may be deleted by WI-048.
