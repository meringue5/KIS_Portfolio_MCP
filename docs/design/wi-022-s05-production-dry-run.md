# WI-022-S05 production read-only dry-run

## Decision

The production planner is an aggregate-only, read-only gate between deterministic reconstruction and a separately
managed apply. It performs no broker call and no warehouse write. Its public report contains no account, instrument,
order, lot, trade-event, quality-result or source-observation identity.

The execution hash covers the fixed time window and each partition's deterministic partition, replay, projection,
assessment and blocker values. It intentionally excludes the current schema migration number: applying the additive
S02 physical objects before S06 must not alter the logical input identity.

## Reviewed production input

- start: `2023-08-28T00:00:00+09:00`
- cutoff: `2026-08-28T23:59:59+09:00`
- observed schema version: `0008`
- execution hash: `b0dfeb93e376520a0a864390276bf65620e2627b05cac834f139f8972e79ba96`
- partitions: 57
- current-held partitions: 22
- partitions with canonical trade history: 56
- trade-only partitions: 35
- canonical trade rows: 282
- passing corporate-action coverage rows: 0
- source calls: 0
- warehouse writes: 0

Two independent inspections of the same cutoff returned the same execution hash and aggregate counts.

## Fail-closed impact

All 57 partitions are `not_assessed` with `corporate_action_coverage_not_assessed`. The reviewed S06 boundary is
therefore:

- Silver position-episode projections: 0
- Silver purchase-lot-state projections: 0
- Silver sell-allocation projections: 0
- append-only Control reconstruction exceptions: 57

This is not evidence that the instruments had no corporate action. It is evidence that the governed date-range
coverage needed to make that statement has not been published. S06 may apply the additive physical migration and
publish the 57 review exceptions only when the execution hash and all aggregate counts still match this report.
Any new trade, position, coverage, replay or projection input changes the hash and stops the apply before a write.

## Recovery handoff

S06 must run from tested `master` using an immutable image digest and Git SHA. It must create and independently
download/restore private pre- and post-apply complete V2 backups, prove an idempotent second replay, reconcile live and
restored aggregate state and emit only aggregate evidence. V1 objects remain untouched.
