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
- `WI-022-S02` — additive position-episode, lot-revision, allocation and exception schema (`closed`).
- `WI-022-S03` — deterministic trade and corporate-action replay with inferred-opening handling (`closed`).
  - [x] canonical trades and governed action effects replay in stable effective order.
  - [x] inferred opening is reverse-adjusted across complete quantity effects and never receives a fabricated cost.
  - [x] zero balance closes an episode and a later buy opens a new stable episode.
  - [x] missing coverage, source gaps, ambiguous order and insufficient opening quantity fail closed.
  - [x] the replay is deterministic, pure and persists no S02 object.
- `WI-022-S04` — append-only sell allocation, reconciliation, idempotency and restore proof (`closed`).
  - [x] only reconciled S03 plans publish episode, lot and whole sell-allocation revisions atomically.
  - [x] stable identities are immutable and a repeated replay hash creates no duplicate revision or slice.
  - [x] blocked plans publish only a reviewable Control exception; later passing evidence resolves it append-only.
  - [x] persisted current projections reconcile with the replay plan and transaction failure leaves no partial publish.
  - [x] a complete governed V2 Parquet export restores the reconstructed current projections in fresh DuckDB.
- `WI-022-S05` — aggregate-only production read-only dry-run and impact report (`closed`).
  - [x] production inspection is read-only and emits no account, order, lot or raw source identity.
  - [x] the report pins reconstruction window/cutoff, schema state, partition count and deterministic plan hash.
  - [x] status, blocker and projected episode/lot/allocation/exception counts reconcile at aggregate level.
  - [x] missing migration/input/coverage or quantity mismatch blocks Silver projection rather than fabricating it.
  - [x] repeated inspection of the same cutoff produces the same reviewed execution hash.
- `WI-022-S06` — separately approved bounded production apply and recovery evidence (`in_progress`).
  - [ ] tested `master` builds one immutable image for migration and apply jobs.
  - [ ] migration through `0010` and the exact S05 hash/count gate pass before publication.
  - [ ] private pre-backup is uploaded, hash-downloaded and restored before any reconstruction write.
  - [ ] only the 57 approved Control exceptions publish; V1 and Silver reconstruction rows remain unchanged.
  - [ ] identical replay is a no-op and post-backup isolated restore matches live aggregate evidence.

## Evidence

- `docs/design/wi-022-s01-reconstruction-contract.md` fixes the position-episode boundary, separate evidence/outcome
  quality axes, fail-closed precedence and explicit-lot > explicit-thread FIFO > inferred FIFO allocation order.
- `dataset.position-episode`, `dataset.purchase-lot-state`, `dataset.sell-allocation` and
  `pipeline.position-lot-reconstruction-v2` are approved logical contracts; S02 still owns physical objects.
- The pure domain module and nine tests cover non-secret deterministic partition identity, exact replay, inferred
  opening, source/action blockers, negative residual, scoped FIFO, explicit-selector failure and insufficient lots.
- `bash scripts/check.sh quick` passed; `bash scripts/check.sh full` passed with 326 tests and the existing Authlib
  deprecation warning. No source call, database write, live migration or external send occurred.
- Migration `0010_position_lot_reconstruction.sql` adds seven backed-up identity/revision tables and four rebuild
  current views without altering the WI-010 `purchase_lots` artifact or existing allocation slices.
- The V2 catalog now governs 59 objects: 47 tables and 12 views. Forty-six table/object metadata contracts are in the
  complete V2 recovery allowlist; the four new current projections are rebuilt from versioned tables.
- Constraint and current-view fixtures reject actual lots without a buy reference and allocation quantity mismatch,
  select whole latest revisions and preserve resolved exception history.
- Thirteen focused migration/schema/recovery/corporate-action tests passed. `bash scripts/check.sh quick` and
  `bash scripts/check.sh full` passed with 329 tests and the existing Authlib deprecation warning.
- No live MotherDuck migration, source call, replay, scheduler change or external send occurred.
- `position_replay.py` performs exact reverse boundary derivation and deterministic forward replay without a source or
  repository dependency. Ten synthetic tests cover input-order stability, FIFO, inferred opening, split adjustment,
  governed successor identity, episode close/re-entry and fail-closed evidence/order/quantity boundaries.
- `docs/design/wi-022-s03-deterministic-replay.md` fixes the algorithm, local episode quality and S04 persistence
  handoff. `bash scripts/check.sh quick` and `bash scripts/check.sh full` passed with 339 tests and the existing Authlib
  deprecation warning. No source call, database write, live migration, scheduler change or external send occurred.
- `position_reconstruction_warehouse.py` verifies input and candidate projection hashes, immutable identities, complete
  allocation scope and quantity reconciliation before publishing all episode/lot/allocation revisions in one
  transaction. Blocked plans remain Control exceptions and later passing evidence resolves them append-only.
- Seven S04 repository fixtures prove identical replay reuse, changed-input whole revisions, exception open/resolve,
  inferred opening without fabricated cost, transaction rollback, tamper rejection and complete V2 Parquet restore.
  Twenty focused S02~S04 tests passed. `bash scripts/check.sh quick` and `bash scripts/check.sh full` passed with 346
  tests and the existing Authlib deprecation warning. No source call, production database write, live migration,
  scheduler change, GCS upload or external send occurred.
- `position_reconstruction_runtime.py` reads the passing production current-position and canonical-trade boundaries,
  evaluates each account/instrument partition and returns only aggregate counts plus a deterministic logical-input hash.
  Its public report contains no account, instrument, order, lot or source-observation identity.
- Two identical read-only MotherDuck inspections of `2023-08-28T00:00:00+09:00` through the already elapsed
  `2026-08-28T18:00:00+09:00` cutoff produced execution hash
  `43b1269058f649823cd46e25acbabaea18f5f850d85513736f68595ba7e77a34`: 57 partitions, 22 current-held,
  56 with trade history, 282 canonical trade inputs and zero source calls/writes.
- Production has no passing corporate-action coverage rows for this window. All 57 partitions therefore remain
  `not_assessed` and are approved only for append-only Control exceptions; projected Silver episode, lot and allocation
  counts are all zero. This is a fail-closed result, not a claim that no corporate action occurred.
- `docs/design/wi-022-s05-production-dry-run.md` records the reviewed aggregate impact and S06 exact-input gate.

## Closeout

- Result: in progress; S01~S05 are closed and S06 is active.
- Remaining risk: owner review for ambiguous opening positions.
- Follow-up sub-item: WI-022-S06 bounded append-only production apply and recovery proof.
