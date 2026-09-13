---
id: WI-048
title: Transition remaining V1 main consumers to archive or compatibility views
status: closed
type: architecture
owner: owner
decision_refs: ADR-018, ADR-021, ADR-023, ADR-028
requirement_refs: DEC-036, DEC-045, DEC-047, DEC-056
milestone_ref: MS-004
delivery_refs: V2-W0803
parent_work_item: none
depends_on: WI-046
execution_scope: isolated
production_effects: none
architecture_impact: retires the V1 warehouse consumer boundary
data_impact: compatibility/archive transition; no automatic deletion
security_impact: confidential history remains protected
cost_impact: bounded storage and query review
stabilization_window: production transition run plus first owner-observed canonical Remote read after revision 00045
stabilization_exit_refs: GitHub run 34759029400, transition execution kis-portfolio-wi048-s02-ct5p9, owner Remote observation
rollback_plan: forward-recover the additive reference copy or redeploy the last safe V2 digest; never reactivate V1
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

- [x] no V2 writer targets main and external consumers are zero or migrated.
- [x] archive/compatibility data reconciles and restores.
- [x] warehouse/full gates pass with zero unmanaged drift.

## Change impact

- Preservation-first warehouse retirement boundary.

## Plan

1. Inventory consumers. 2. Migrate or preserve compatibility. 3. Reconcile and restore.

## Sub-items

- `WI-048-S01` — isolated V2 reference-control transition, archive disposition and restore contract (`verified`).
- `WI-048-S02` — execute the protected production reference transition and V2-only revision update (`closed`).

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
- Production workflow run `34759029400` completed successfully from master `fdd5935` in 5m51s. Transition execution
  `kis-portfolio-wi048-s02-ct5p9` completed one task in 1m58s: private pre/post backups contained 76/79 objects,
  migration advanced `0018` to `0019`, `control.market_calendar`/`instrument_master`/classification override rows
  reconciled at 365/4,440/0, fresh restore fingerprints matched, and idempotent replay passed. Reported source calls,
  source mutations and deletions were all zero.
- The existing core jobs for `kr-1000`, `kr-1430` and `kr-1600` plus stable Remote now use the same immutable
  `sha256:a35e6899cfe17faa02d42352f4d8eb76dacd8ff71ec1488ceaa4eff2458208ab`. Their labels identify git SHA
  `fdd59355a6a8c3440bd654e67adebe8f5d0447c5` and GitHub run `34759029400`; Remote revision
  `kis-portfolio-remote-00045-kag` serves 100% traffic. Auth/Remote health returned 200, unauthenticated `/mcp`
  returned 401 and protected-resource metadata named the canonical resource.
- Post-transition live inventory has no missing managed objects and confirms all three new `control` references are
  managed. The retained zero-row `main.cash_flow`, `main.trade_journal`, `main.asset_return_daily` objects and known
  V1 daily-view column drift remain explicitly unadopted and undeleted pending the separate WI-049 destructive gate.
- The owner opened a new Claude session after Remote revision `kis-portfolio-remote-00045-kag` and invoked only
  `get-portfolio-overview` once through the canonical `KIS Portfolio` connector. The read succeeded with stored-data
  freshness `available`, snapshot as-of `2026-09-11T07:03:28.099252Z`, and matching top-level and summary quality
  status `pass`. No collection, managed pipeline or write tool was invoked. Portfolio amounts, holdings and account
  identifiers are intentionally excluded from repository evidence.

## Stabilization plan

- Observe one owner-initiated read through the canonical `KIS Portfolio` Remote after revision
  `kis-portfolio-remote-00045-kag`; no V1 comparison or fallback is required.
- Keep the immutable transition run, private pre/post restore evidence, health/auth boundary and live inventory as the
  exit evidence. A client-visible read failure opens a linked corrective sub-item instead of reactivating V1.
- If the additive reference copy or runtime revision regresses, forward-reconcile the copied references or redeploy the
  last safe V2 digest. WI-049 remains the only place permitted to delete retained V1 objects.

## Closeout

- Result: closed by successful owner-observed canonical Remote read after the protected S02 production transition;
  the V2 runtime is the sole canonical operating path.
- Remaining risk: retained V1 objects and classified drift remain preserved until WI-049 receives its separate
  destructive approval. No V1 fallback or rollback requirement remains.
- Follow-up Work Items: WI-049 and WI-050.
