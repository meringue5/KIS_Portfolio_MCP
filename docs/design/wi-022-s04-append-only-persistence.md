# WI-022-S04 — Append-only Reconstruction Persistence

## Scope and side-effect boundary

This sub-item publishes an S03 `PositionReplayPlan` into the S02 reconstruction ledger. The only allowed side effect
is one transaction against an explicitly supplied DuckDB/MotherDuck-compatible connection. Repository-local tests use
fresh DuckDB only. Production MotherDuck migration, source reads, batch activation and schedule changes remain outside
S04; S05 is aggregate-only read-only impact analysis and S06 is the separately approved bounded production apply.

No new dataset, object, source, provider, retention or backup policy is introduced. S04 implements the already approved
`dataset.position-episode`, `dataset.purchase-lot-state`, `dataset.sell-allocation` and
`pipeline.position-lot-reconstruction-v2` contracts using migration `0010` and the existing complete V2 backup
allowlist.

## Two-hash publish gate

The plan carries two independent deterministic hashes:

- `replay_hash` covers governed inputs, window, coverage evidence and source gaps;
- `projection_hash` covers the assessment and every candidate episode, lot state, allocation header and slice.

The repository recomputes the projection hash before opening a transaction. A candidate altered after deterministic
replay is rejected even when its input replay hash is unchanged. The repository also recomputes the non-secret
partition key from the request and checks plan/request current quantity, account, lineage, episode, lot and allocation
scope.

## Atomic publish and append-only identity

Stable episode and lot identity rows are inserted once. Existing identity fields must match exactly; the repository
never mutates them or adopts a conflicting identity. State changes append a new revision only when the replay/content
hash changes and `knowledge_at` advances. Repeating an identical plan reuses all existing revisions and slices.

One transaction performs the following operations:

1. insert or verify position episode identities;
2. append episode revisions;
3. insert or verify purchase-lot identities;
4. append lot state revisions with their last effective cause;
5. append one whole sell-allocation header revision and all of its slices;
6. resolve prior open exceptions for the same partition when the plan is reconciled;
7. query current views and compare their quantities, state, causes and slices with the plan;
8. commit only after all comparisons pass.

Any constraint, identity, monotonic-knowledge or reconciliation failure rolls back the complete candidate publish.
There is no partial episode/lot/allocation state.

## Reconciliation contract

A publishable plan must have `reconstructed` or `inferred_opening` status, no blocker and
`eligible_for_reconciled_projection=true`. Exactly one open episode exists for a positive current position and none for
zero. Open episode quantity equals the request current quantity, and each episode quantity equals the sum of its lot
remaining quantities. Lot quantity is non-negative and cannot exceed effective quantity. An actual lot cites a buy;
an inferred opening has no fabricated unit cost.

Each sell has one complete allocation candidate. Header requested quantity equals allocated plus unallocated quantity,
unallocated quantity is zero, slice sum equals allocated quantity, and every slice remains inside its episode.
Corporate-action successor history may make a historical sell instrument differ from the cutoff target, so the header
stores the sell event's instrument rather than replacing it with the current symbol.

## Exception lifecycle

A non-publishable S03 plan creates no Silver candidate fact. It appends a non-secret Control exception identity and an
`open` revision containing the blocker, replay hash and optional coverage quality reference. An identical blocked plan
is idempotent. A later reconciled plan for the partition appends a `resolved` revision referencing the passing replay;
the open evidence is preserved rather than overwritten or deleted.

## Recovery proof and handoff

The repository test exports the complete governed V2 Parquet allowlist, restores it into a fresh DuckDB, rebuilds the
current views through versioned migrations and verifies episode quantity, lot remainder and allocation slices. This is
local recovery evidence, not a production backup or external GCS upload.

S05 may inspect production inputs and report only aggregate plan/exception counts. S06 must use the exact approved
plan, pre-backup, bounded transaction and post-backup/restore verification before production data is accepted.
