---
id: WI-021
title: Collect bounded three-year trade and cash history
status: proposed
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

- `none`.

## Evidence

- Pending.

## Closeout

- Result: proposed; depends on WI-020.
- Remaining risk: broker retention and historical gaps.
- Follow-up Work Item: WI-022.
