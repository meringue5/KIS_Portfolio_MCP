---
id: WI-021
title: Collect bounded three-year trade and cash history
status: in_progress
type: change
owner: owner
decision_refs: ADR-021, ADR-023, V2-ADR-006, V2-ADR-010, V2-ADR-012
requirement_refs: DEC-009..014, DEC-030, DEC-038, DEC-041, DEC-044
milestone_ref: MS-002
delivery_refs: V2-W0403
parent_work_item: none
depends_on: WI-016, WI-020
architecture_impact: extends the approved managed broker-history pipeline without a new service
data_impact: bounded Bronze landing and canonical trade/cash history with reversible links
security_impact: confidential broker history; aggregate-only operational evidence
cost_impact: bounded scale-to-zero backfill under explicit call and row budgets
---

# WI-021 — Collect bounded three-year trade and cash history

## Problem and evidence

Correct source semantics exist for current broker history, but continuous three-year trade/cash coverage required for
reconstruction and return analysis has not been collected or reconciled.

## Classification and contract

- `change`; production backfill remains a separate operational gate.
- Raw source observations remain immutable and canonical links reversible.

## Scope

- Include bounded domestic/overseas collection, pagination, quality, lineage and reconciliation dry-run.
- Exclude inferred lot allocation and return metrics.

## Acceptance criteria

- [ ] call/page budgets fail closed and resumable partitions are idempotent.
- [ ] known source gaps remain explicit.
- [ ] approved live backfill, restore and aggregate reconciliation evidence exist before closeout.

## Change impact

- Existing managed Job pattern; no always-on service or public MCP change.

## Plan

1. Plan partitions and source budgets.
2. Add pipeline evidence and dry-run reconciliation.
3. Apply only the separately approved bounded backfill.

## Sub-items

- `WI-021-S01` — deterministic three-year backfill planner and source-boundary partitions (`closed`).
  - [x] every callable partition is bounded, ordered and has a stable non-secret key.
  - [x] domestic partitions never cross the KIS old/recent route boundary.
  - [x] unsupported IRP recent history and unavailable cash-history sources remain explicit gaps.
  - [x] the planner performs no source call, database write or inferred cash-event creation.

## Evidence

- `src/kis_portfolio/services/trade_cash_backfill.py` is a pure planner with a stable versioned partition key;
  `plan-trade-cash-backfill-v2` exposes the public manifest without source or warehouse access.
- The deterministic five-account `2023-08-28..2026-08-28` reference plan has 137 partitions: 131 callable and six
  named gaps. Its page-cap projection is planning metadata and no execution budget is enforced in S01.
- `tests/test_trade_cash_backfill_planner.py` covers exact coverage, boundary splits, IRP/domestic-cash gaps,
  credential exclusion, input-order determinism, virtual-source gaps and the read-only CLI.
- `bash scripts/check.sh quick`: passed with 83 governed contracts.
- `bash scripts/check.sh full`: 278 tests passed; all Project OS, data governance, architecture, warehouse and MCP
  surface gates passed. One existing Authlib deprecation warning remains.

## Closeout

- Result: WI-021-S01 closed; parent WI-021 remains in progress and no production source or database was changed.
- Remaining risk: broker retention and historical gaps.
- Follow-up: call/page budget enforcement, resumable execution, reconciliation and separately approved live backfill
  remain inside WI-021 before WI-022 can start.
