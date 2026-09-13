---
id: WI-048
title: Transition remaining V1 main consumers to archive or compatibility views
status: in_progress
type: architecture
owner: owner
decision_refs: ADR-018, ADR-021, ADR-023, ADR-028
requirement_refs: DEC-036, DEC-045, DEC-047, DEC-056
milestone_ref: MS-004
delivery_refs: V2-W0803
parent_work_item: none
depends_on: WI-046
execution_scope: production
production_effects: additive_reference_migration_and_v2_revision_update
architecture_impact: retires the V1 warehouse consumer boundary
data_impact: compatibility/archive transition; no automatic deletion
security_impact: confidential history remains protected
cost_impact: bounded storage and query review
---

# WI-048 — Transition remaining V1 main consumers to archive or compatibility views

## Problem and evidence

V1 `main` cannot be retired until writer and consumer evidence is zero and history has an explicit disposition.

## Classification and contract

- `architecture` data-consumer cutover with destructive deletion excluded.

## Scope

- Include consumer logging, zero-use evidence, compatibility views/archive status and restore.
- Exclude table drop or history deletion without separate approval.

## Acceptance criteria

- [ ] no V2 writer targets main and external consumers are zero or migrated.
- [ ] archive/compatibility data reconciles and restores.
- [ ] warehouse/full gates pass with zero unmanaged drift.

## Change impact

- Preservation-first warehouse retirement boundary.

## Plan

1. Inventory consumers. 2. Migrate or preserve compatibility. 3. Reconcile and restore.

## Sub-items

- `WI-048-S01` — isolated V2 reference-control transition, archive disposition and restore contract (`verified`).
- `WI-048-S02` — execute the protected production reference transition and V2-only revision update (`in_progress`).

## Evidence

- Activated 2026-09-13 after WI-047 closed the local/setup/public V1 surface. Initial execution is read-only inventory,
  repository compatibility/archive design, fixtures and local restore verification; live table/view mutation or deletion
  is excluded.
- Read-only live inventory found no missing managed V2 objects, three retained zero-row `main` drift objects
  (`cash_flow`, `trade_journal`, `asset_return_daily`) and the previously recorded quality-column drift on the V1 daily
  view. WI-048 neither adopted nor changed these objects.
- `WI-048-S01` added migration `0019` for V2-owned `control.market_calendar`, `control.instrument_master` and
  `control.instrument_classification_overrides`. Production V2 runtime now reads these qualified objects and no longer
  re-ingests V1 `main.price_history` or `main.exchange_rate_history`; existing `silver.price_bars_daily` and
  `silver.fx_rates_daily` remain the canonical history.
- `governance/project/v1-main-transition.toml` is the deletion-denied transition/rollback manifest. The transition
  helper defaults to a read-only aggregate plan and requires an explicit local `--apply`; fixture application preserved
  every source row, reconciled all copied rows and was idempotent. The three new tables are complete V2 Parquet backup
  members and fresh restore is covered by the version-aware recovery gate.
- Isolated verification: transition/recovery suite `6 passed`; transition and affected runtime suite `38 passed`;
  quick Project OS, data governance, architecture, warehouse and 18-tool MCP surface gates passed; full gate
  `674 passed` with one existing Authlib deprecation warning.
- 2026-09-13 owner authorization opened the MS-004 production phase for WI-048. S02 may create private pre/post
  backups, apply additive migration `0019`, copy/reconcile the three retained reference tables and update only the
  existing Remote plus three V2 core Job revisions. It may not delete or mutate V1 source/history, change IAM/Secret,
  alter Scheduler definitions, call KIS sources, send Telegram messages, or activate a new public surface.
- `run-wi048-s02` and the protected `wi048-s02` deploy target now enforce that sequence: one immutable image,
  private pre-backup/fresh restore, additive `0019`, exact reference reconciliation plus idempotent replay, private
  post-backup/fresh restore, then the existing V2 core jobs and stable Remote update. The deploy target reuses existing
  identities and does not contain Scheduler or IAM mutation commands. Focused transition/deploy/Project OS verification
  passed `83` tests; the full gate passed `677` tests with one existing Authlib deprecation warning.

## Closeout

- Result: in progress.
- Remaining risk: production migration `0019`, private pre-backup, exact copy/reconciliation, external-consumer
  observation and post-backup/fresh restore remain unexecuted. Deletion is denied here and remains separately approved.
- Follow-up Work Item: WI-050.
