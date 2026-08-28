---
id: WI-022
title: Reconstruct positions lots and sell allocations
status: proposed
type: change
owner: owner
decision_refs: ADR-021, ADR-023, V2-ADR-006, V2-ADR-010, V2-ADR-016
requirement_refs: DEC-009..014, DEC-038, DEC-041, DEC-044
milestone_ref: MS-002
delivery_refs: V2-W0304, V2-W0305
parent_work_item: none
depends_on: WI-010, WI-021
architecture_impact: completes approved ledger projections and reversible allocation boundaries
data_impact: corrected position episodes, purchase lots and append-only sell-allocation revisions
security_impact: confidential trade facts remain internal
cost_impact: bounded batch reconstruction only
---

# WI-022 — Reconstruct positions lots and sell allocations

## Problem and evidence

Current migrated lots are partial and cannot explain opening history or sell allocation. Verified three-year events
must be replayed without silently rewriting the preserved migration artifacts.

## Classification and contract

- `change`; source events remain immutable and corrections are append-only.
- A sell never creates a purchase lot; ambiguous allocations enter review state.

## Scope

- Include position episodes, lots, candidate links, sell allocations and reconciliation.
- Exclude thread risk policy and investment-return metrics.

## Acceptance criteria

- [ ] quantities reconcile or carry explicit exception/quality states.
- [ ] ambiguous or missing opening history remains reviewable and reversible.
- [ ] restore and idempotent replay evidence pass.

## Change impact

- Additive Silver/Control revisions; no destructive V1 rewrite.

## Plan

1. Define reconstruction and allocation boundaries.
2. Replay verified history in isolation.
3. Apply only reconciled projections and preserve exceptions.

## Sub-items

- `none`.

## Evidence

- Pending.

## Closeout

- Result: proposed; depends on WI-021.
- Remaining risk: owner review for ambiguous opening positions.
- Follow-up Work Item: WI-023 and WI-024.
