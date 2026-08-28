# Milestone 2 trade/cash backfill — 2026-08

## Release provenance

- GitHub Actions: `33145645614`, success, `2026-08-28T05:43:55Z..06:03:55Z`.
- Reviewed `master`: `224913c8a273de4c4b5871a86c7c4b819f939b08`.
- Immutable image: `sha256:bf02b5582c63408691e2f3ab6bc05d59af26b6900234abbd7a41fa839476d863`.
- Configuration: one task, parallelism one, zero automatic retries, no Scheduler.

## Fail-closed precursor evidence

1. Run `33144993012` failed while deploying because gcloud rejected a duplicate list-valued date argument. The Job
   was not created and no KIS source call occurred. PR 12 made `as-of` derive from the fixed end date.
2. Run `33145316290`, execution `kis-portfolio-wi021-s06-h4v6r`, deployed successfully but stopped with
   `MigrationError` before backup or source initialization because production migration `0008` was absent. PR 13
   added a separate fixed-through migration Job instead of runtime auto-DDL.

Neither attempt wrote backfill rows or consumed a KIS business-page reservation.

## Migration and execution

- Migration execution `kis-portfolio-wi021-s06-migration-gpzc6` applied checksum-verified migration `0008` only and
  completed successfully at `2026-08-28T05:46:15Z`.
- Recovery/backfill execution `kis-portfolio-wi021-s06-8q7q6` completed successfully in 1,036.614 seconds.
- Fixed plan `0755656ed8151a91`, budget `0a4abf9b795f9d73`, range `2023-08-28..2026-08-28`.
- 131 callable partitions succeeded; six governed source gaps remain explicit; no partition was reused.

## Aggregate reconciliation

| Measure | Result |
| --- | ---: |
| Physical KIS calls | 131 / 400 |
| Successful pipeline stages | 393 |
| Quality rows | 262 pass, 0 non-pass |
| Lineage rows | 150 valid, 0 invalid |
| Watermark streams | 11 valid, 0 foreign |
| Bronze outputs | 340 trade observations + 49 cash observations |
| Canonical events | 263 trade + 49 cash |
| Purchase lots | 0 |
| Evidence failures | 0 |

The non-zero warehouse deltas were 389 Bronze observations, 131 pipeline runs, 393 stage runs, 262 quality rows,
150 lineage edges, 11 watermarks, 263 trade events/revisions and 49 cash events/revisions. WI-021 did not infer lots,
threads, allocations or return metrics.

## Recovery evidence

| Recovery point | Objects | Total bytes | Index SHA-256 |
| --- | ---: | ---: | --- |
| Pre-backfill | 37 | 7,756,343 | `6dca05eeb651d2584ec003dd72fc731995ef54a6890ebc8c30d04a19b06ecf9b` |
| Post-backfill | 37 | 8,115,216 | `b1b1412306049500bac20d33fd2578efd0f7b7c9454726f1336151328aa885c7` |

Both indexes exist in the private GCS recovery prefix. Each recovery point was downloaded by exact index URI/hash,
restored into a fresh DuckDB and verified. Post-restore reconciliation exactly matched live aggregate evidence.
The separately stored aggregate evidence SHA-256 is
`3015cab1bcf46130ecf68880ecc349088011d459ecc7fe8947596a187023a2ba`.

The largest recovery point is below 8.2 MB, far below the approved 10 GiB MotherDuck Lite storage bound, and the
1,036.614-second execution is below the four-hour recovery objective.
