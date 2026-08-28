---
id: WI-048
title: Transition remaining V1 main consumers to archive or compatibility views
status: proposed
type: architecture
owner: owner
decision_refs: ADR-018, ADR-021, ADR-023
requirement_refs: DEC-036, DEC-045, DEC-047
milestone_ref: MS-004
delivery_refs: V2-W0803
parent_work_item: none
depends_on: WI-046
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

- `none`.

## Evidence

- Pending.

## Closeout

- Result: proposed.
- Remaining risk: deletion remains separately approved.
- Follow-up Work Item: WI-050.
