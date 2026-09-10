# WI-041 isolated forward outlook verification — 2026-09-10

> Work Item: `WI-041`
> Execution scope: `isolated`
> Production effects: `none`
> Implementation commit: `d25fd12193cae5c19c3a483bcce4936928f6c2ce`

## Result

WI-041 implemented only the owner-approved Alpha Vantage personal-use, normalized, forward-collected secondary path.
It did not implement or weaken the unresolved licensed historical `dataset.consensus-snapshot`. The source, dedicated
collection, dataset and pipeline contracts load as one exact approved-inactive runtime bundle; production source access
fails before I/O.

Migration `0017_alpha_consensus_forward.sql` is additive and has SHA-256
`006c2ebff15328b91c9a7ad76b652c0767db7d54d526d6c1f4e6b2771904c51a`. It adds 1 restricted Silver table and 1
rebuildable view, taking the governed V2 catalog to 102 objects: 75 tables and 27 views. It does not drop, rename or
update an existing object.

## Verified boundaries

- The runtime registry requires the exact four approved Alpha contract IDs/version, official EARNINGS_ESTIMATES
  endpoint, secondary/free role, restricted Parquet dataset and dedicated source/output links.
- The isolated adapter accepts only conspicuously marked synthetic fixtures. It requires the sampled 18-field estimate
  allowlist, exact requested symbol and typed EPS/revenue ranges; unexpected fields and invalid strings fail closed.
- Provider `Information`, rate-limit and error envelopes produce generic partial/failed reasons. Their free-text body is
  not copied into a DTO, database, lineage, quality evidence or backup.
- Silver stores issuer, provider forecast date, horizon, metric, range, analyst count, supported EPS rolling attributes,
  U.S. session and fetched-at knowledge. There is no raw payload, provider-message or credential column.
- Only exact positive `NASD / equity / overseas_direct / USD` held issuers with passing identity quality are eligible.
  Duplicate issuer/symbol mappings and more than eight calls fail before any future I/O.
- System-as-of reads exclude future fetched snapshots. Revision calculation requires two actual monotonic fetches;
  provider 7/30/60/90-day attributes remain explicitly non-historical. User/model scenarios cannot use the provider
  consensus origin.
- Quarterly terms evidence, 4-current/8-hard/account-wide-25 call bounds, 15-second serial spacing, no same-run retry,
  500,000-row/512 MiB stop lines and owner-only consumers are enforced as inactive guards.
- Partial held-scope coverage cannot advance the U.S. session watermark. Missing issuer refs and the unsupported
  historical-PIT/raw-retention flags stay explicit in Control quality evidence.
- Three-year retention is a read-only candidate planner. No row, backup or object is deleted in this Work Item.
- Governed private Parquet export and fresh local DuckDB restore reproduce four synthetic normalized rows and compile
  the latest projection.

## Recovery and rollback manifest

This isolated phase created no production state to roll back. Before production activation, rollback is:

1. Keep `pipeline.alpha-vantage-consensus-forward-v1`, its source, collection, dataset, Secret accessor, Scheduler and
   every MCP consumer inactive.
2. Do not apply migration 0017 to production. If a separately approved release later applies it, stop source access and
   writers first; preserve the additive table/view as an abandoned version while existing V1 and historical-consensus
   gaps remain unchanged.
3. Do not rewrite fetched-at, turn rolling comparison attributes into backdated snapshots, copy raw payloads, or merge
   Alpha into the unresolved canonical historical dataset.
4. Treat terms expiry/revocation, shape drift, over-eight holdings or partial coverage as a kill switch. Retention apply,
   cleanup, migration reversal or deletion requires a separate destructive Work Item and verified private backup.
5. Restore only a complete governed V2 manifest into a fresh database and verify every table row count and rebuild view
   before accepting recovery.

## Cost and release guardrail

- External Alpha/KIS/provider calls: 0
- Research or runtime Secret access and IAM changes: 0
- Live DB reads, writes or migration: 0
- New production storage: 0 bytes
- Cloud Run, Scheduler, private/public MCP or Telegram changes: 0
- Production release, backfill, retention apply, cleanup or cutover: 0

The 4-current/8-hard/account-wide-25 free-tier call plan, 15-second spacing and capacity ceilings are planning guards.
They authorize no source call, credential access, schedule, migration, consumer or paid plan.

## Verification evidence

- Focused migration and WI-041 suite: `12 passed`.
- WI-041 plus filing/metric/migration/warehouse/backup-recovery integration selection: `31 passed`.
- `bash scripts/check.sh quick`: passed.
- `bash scripts/check.sh full`: `556 passed`, one existing Authlib deprecation warning.

No account number, held symbol, API key, real estimate, raw provider response or production resource was used. The only
provider-shaped values are conspicuously synthetic fixtures.
