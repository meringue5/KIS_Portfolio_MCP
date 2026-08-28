# WI-022-S01 — Position Reconstruction and FIFO Allocation Contract

## Scope and side-effect boundary

This sub-item fixes the pure decision contract used by later WI-022 schema, replay and production stages. It consumes
only governed `dataset.trade-event`, `dataset.portfolio-position-observation` and
`dataset.corporate-action-event` facts. It performs no KIS call, warehouse write, live migration, scheduler change or
external send.

The contract owns three derived datasets: `dataset.position-episode`, `dataset.purchase-lot-state` and
`dataset.sell-allocation`. Physical objects and repositories are deferred to S02.

## Two independent quality axes

Evidence provenance and reconstruction outcome must not share one field.

| Axis | Values | Meaning |
| --- | --- | --- |
| evidence provenance | `actual`, `manual`, `inferred_opening` | where a lot or correction fact came from |
| reconstruction outcome | `reconstructed`, `inferred_opening`, `provisional`, `not_assessed`, `reconciliation_exception` | whether the replay can support a reconciled projection |

An actual trade can therefore participate in a provisional reconstruction. Conversely, an `inferred_opening` lot is
allowed only as an explicitly labelled residual; it never becomes an actual execution.

Outcome precedence is fail closed:

1. Negative residual, failed corporate-action coverage or ambiguous event order is `reconciliation_exception`.
2. Missing corporate-action coverage is `not_assessed`.
3. A named broker/source gap is `provisional`.
4. With passing coverage and no gap, a positive current-minus-replayed residual is `inferred_opening`.
5. Exact quantity reconciliation is `reconstructed`.

Only the last two outcomes are eligible for a reconciled projection. Current broker average cost may help reconcile
the boundary, but it is never backdated as the execution price of an inferred opening.

## Position episode boundary

A position episode is one continuous non-zero holding interval for one account and canonical instrument. Balance
returning to zero closes the episode; a later buy opens a new episode. Lot or sell allocation cannot cross account,
instrument or episode. A governed corporate-action identity effect may carry an episode to a successor instrument;
matching names or symbols without that effect cannot.

The partition identity hashes contract version, account, instrument and the explicit reconstruction window. The
public key therefore contains no account or instrument value.

## Sell allocation precedence

Allocation uses the following precedence without fallback:

1. Explicit lot selection: allocate only the selected open lots, FIFO by `(opened_at, lot_id)`.
2. Explicit thread selection: allocate only the thread's open lots using the same FIFO order.
3. No selection: allocate all open lots in the position episode by FIFO and mark the result for owner/LLM review.

An unavailable explicit selector is an error rather than permission to broaden scope. Insufficient quantity may
produce a partial candidate plus `reconciliation_exception`, but cannot create a buy lot, negative remaining quantity
or hidden allocation. Every later correction is a whole append-only allocation revision.

## Deferred boundaries

- S02 defines additive Silver/Control physical objects, current views, backup and restore allowlists.
- S03 replays canonical trades and governed corporate-action effects and creates explicit inferred openings.
- S04 persists append-only allocation revisions and proves reconciliation, idempotency and restore.
- S05 only reads production aggregates and emits an impact report.
- S06 applies the exact approved plan after pre-backup and verifies post-backup recovery.
