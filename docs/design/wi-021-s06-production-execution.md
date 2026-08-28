# WI-021-S06 — One-off production execution and recovery

## Decision

The approved three-year trade/cash backfill runs as dedicated, manually dispatched Cloud Run Jobs. They are never
included in the `all` deployment target and have no Scheduler. GitHub Actions builds once from tested `master`, resolves
the image digest and deploys a schema migration task followed by the recovery/backfill task. Both use one task,
parallelism one and zero automatic retries; the backfill has a four-hour hard timeout.

The fixed production envelope is:

- range and cutoff: `2023-08-28..2026-08-28`, as-of `2026-08-28`;
- plan hash: `0755656ed8151a91`;
- budget hash: `0a4abf9b795f9d73`;
- 131 callable partitions and six explicit known gaps;
- at most 400 KIS business-page reservations;
- private recovery bucket: `grand-forge-279904-kis-portfolio-private`;
- immutable `KIS_RELEASE_IMAGE_DIGEST` and `KIS_RELEASE_GIT_SHA` evidence.

## Fail-closed order

The release first executes `kis-portfolio-migrate --motherduck --through 0008`. This is an explicit, additive,
checksum-verified migration Job using the same immutable image; it is idempotent and cannot adopt later migrations.
Only after it succeeds does `run-wi021-s06` perform one serial process:

1. Rebuild the deterministic plan and verify database mode, hashes and partition count before opening the warehouse.
2. Export the complete governed V2 allowlist to a private pre-backup directory.
3. Upload the pre-backup to private GCS, download it by exact index URI/hash and restore it to a fresh local DuckDB.
4. Only after step 3 succeeds, execute the existing guarded, resumable KIS backfill.
5. Reconcile 131 terminal partitions, 393 successful stages, call budgets, quality, lineage, watermark and
   Bronze/Silver event counts; verify that WI-021 created no purchase lot.
6. Export and upload a post-backup, download by exact hash and restore it to another fresh local DuckDB.
7. Run the same aggregate reconciliation on the isolated restore and require exact equality with live evidence.
8. Persist an aggregate-only evidence JSON to the private recovery prefix and emit its URI/hash.

Any failure exits non-zero. Normal output contains counts, status, hashes and governed object row deltas only. The CLI
suppresses upstream exception text so credentials, account/order identifiers and raw broker payloads cannot enter the
workflow log. If the backfill succeeds but later recovery verification fails, a deliberate rerun uses the S03 run
ledger and reuses completed partitions; Cloud Run itself never retries automatically.

## Release and execution

The production action is the `wi021-s06` manual target in `.github/workflows/deploy-cloud-run.yml`. It requires the
normal `production` environment approval and refuses non-`master` source. The workflow deploys the immutable migration
and recovery Jobs, waits for migration `0008`, and then executes the recovery/backfill Job with `--wait`. No local or
branch-source Cloud Run deployment is an approved path.

The current Mac could reach MotherDuck over HTTPS and through the authenticated web UI, while native DuckDB 1.5.2 and
1.5.4 clients repeatedly failed during MotherDuck session creation. The same Secret Manager token was confirmed by
hash equality and the scheduled Cloud Run jobs using it completed successfully. This is why S06 uses the normal
managed release path instead of weakening authentication, rotating a working token or bypassing the recovery gate.
