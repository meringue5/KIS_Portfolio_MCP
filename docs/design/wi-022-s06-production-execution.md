# WI-022-S06 — Bounded production execution and recovery

## Decision

The approved reconstruction apply is a dedicated, manually dispatched Cloud Run target. It is not part of `all` and
has no Scheduler. GitHub Actions accepts only tested `master`, builds one image, resolves its digest and deploys both
the additive migration and apply jobs from that immutable image. Both jobs use one task, parallelism one, zero
automatic retries and the normal `production` environment approval.

The fixed production envelope is:

- start: `2023-08-28T00:00:00+09:00`;
- already elapsed cutoff: `2026-08-28T18:00:00+09:00`;
- execution hash: `43b1269058f649823cd46e25acbabaea18f5f850d85513736f68595ba7e77a34`;
- 57 partitions: 22 current-held, 56 with trade history and 35 trade-only;
- 22 current-position rows, 282 canonical trade rows and zero passing action-coverage rows;
- zero eligible Silver projections and 57 append-only Control exceptions;
- private recovery bucket and immutable image/Git provenance supplied by the managed environment.

## Fail-closed order

1. Deploy and execute `kis-portfolio-migrate --motherduck --through 0010` with the immutable image.
2. Require MotherDuck mode, migration `0010`, a past timezone-aware cutoff and immutable image/Git provenance.
3. Rebuild the plan and compare hash plus every reviewed S05 aggregate before any backup or write.
4. Export the complete governed V2 allowlist, upload it to private GCS, download it by exact URI/hash and restore a
   fresh pre-apply DuckDB.
5. Persist each partition through the S04 append-only repository. The reviewed production input can create only open
   Control exceptions; a blocked plan cannot contain or publish Silver facts.
6. Reconcile every approved partition, then apply the identical plan again and require zero new revision or
   resolution rows.
7. Export/upload/download/restore a post-apply backup and run the same plan and aggregate reconciliation on the
   isolated restored DuckDB.
8. Require live/restore equality, the one-hour recovery bound and the MotherDuck Lite storage bound, then store an
   aggregate-only evidence document in the private recovery prefix.

Any hash, input count, outcome count, migration, backup, restore, idempotency or reconciliation drift exits non-zero.
The CLI redacts exception details. It emits only hashes, counts, private recovery references and release provenance;
it emits no account, instrument, order, lot, trade-event or source-observation identity.

The 57 exceptions are the correct current data product: they preserve the unassessed corporate-action dependency for
later review without inventing opening quantity, cost basis or sell allocation. Activating governed action coverage
later requires a new S05 hash and a separately reviewed reconstruction apply; it does not rewrite this evidence.
