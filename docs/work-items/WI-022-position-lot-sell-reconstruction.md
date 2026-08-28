---
id: WI-022
title: Reconstruct positions lots and sell allocations
status: in_progress
type: change
owner: owner
decision_refs: ADR-021, ADR-023, V2-ADR-006, V2-ADR-010, V2-ADR-016
requirement_refs: DEC-009..014, DEC-038, DEC-041, DEC-044
milestone_ref: MS-002
delivery_refs: V2-W0304, V2-W0305
parent_work_item: none
depends_on: WI-010, WI-021, WI-036
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

- `WI-022-S01` — reconstruction boundary, quality-state and FIFO allocation contract (`closed`).
  - [x] evidence provenance and reconstruction outcome remain separate axes.
  - [x] missing corporate-action coverage and source gaps fail closed without inferred official history.
  - [x] FIFO is deterministic within account, instrument and position episode and never creates a buy lot from a sell.
  - [x] the contract is pure and performs no source call, warehouse write or production mutation.
- `WI-022-S02` — additive position-episode, lot-revision, allocation and exception schema (`proposed`).
- `WI-022-S03` — deterministic trade and corporate-action replay with inferred-opening handling (`proposed`).
- `WI-022-S04` — append-only sell allocation, reconciliation, idempotency and restore proof (`proposed`).
- `WI-022-S05` — aggregate-only production read-only dry-run and impact report (`proposed`).
- `WI-022-S06` — separately approved bounded production apply and recovery evidence (`proposed`).

## Evidence

- `docs/design/wi-022-s01-reconstruction-contract.md` fixes the position-episode boundary, separate evidence/outcome
  quality axes, fail-closed precedence and explicit-lot > explicit-thread FIFO > inferred FIFO allocation order.
- `dataset.position-episode`, `dataset.purchase-lot-state`, `dataset.sell-allocation` and
  `pipeline.position-lot-reconstruction-v2` are approved logical contracts; S02 still owns physical objects.
- The pure domain module and nine tests cover non-secret deterministic partition identity, exact replay, inferred
  opening, source/action blockers, negative residual, scoped FIFO, explicit-selector failure and insufficient lots.
- `bash scripts/check.sh quick` passed; `bash scripts/check.sh full` passed with 326 tests and the existing Authlib
  deprecation warning. No source call, database write, live migration or external send occurred.

## Closeout

- Result: in progress; WI-010, WI-021 and repository-local WI-036 dependencies are closed.
- Remaining risk: owner review for ambiguous opening positions.
- Follow-up Work Item: WI-023 and WI-024.
