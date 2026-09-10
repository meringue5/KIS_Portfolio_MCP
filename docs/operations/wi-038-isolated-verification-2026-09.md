# WI-038 isolated dividend ledger verification — 2026-09-10

> Work Item: `WI-038`
> Execution scope: `isolated`
> Production effects: `none`
> Implementation commit: `6910824a906d22199d1e12e506e4c33a35e5002b`

## Result

WI-038 implemented the approved ADR-026 boundary in repository code and a fresh local DuckDB only. Dividend action,
account entitlement and reversible receipt-link identity/revision ledgers are separate. The immutable
`silver.cash_flow_events` row remains the monetary SSOT; dividend tables store relations, sourced amount-component
revisions and rebuildable monthly projections rather than an independent receipt amount ledger.

Migration `0015_dividend_ledger.sql` is additive and has SHA-256
`ff25cdc5c47b192ea45a8b7f807ffdc1eaee67e3cd9ffe4446c9d3227d79d378`. It adds 7 tables and 5 views, taking the
governed V2 catalog to 95 objects: 71 tables and 24 views. It does not drop, rename or update an existing object.

## Verified boundaries

- Fresh migration applies through 0015, second apply is a no-op, and the migration ledger checksum remains enforced.
- A non-empty legacy `silver.dividend_events` foundation aborts 0015 and leaves its rows and migration history intact.
- Silver action publish requires an exact governed issuer/instrument, dividend observation and hash-matched private
  object manifest. Credential-shaped metadata is rejected.
- Source gaps do not manufacture quantity, gross, tax, net or a cash receipt. Candidate links do not enter the monthly
  received model.
- Receipt links require a dividend-classified cash event at the selected knowledge cutoff. Account and currency must
  match; many-to-many allocations cannot exceed the immutable cash amount and cannot mix allocated and unallocated
  links.
- Link reversal appends a revision. A query before the correction still returns the receipt while a later cutoff and
  the current projection exclude it; the original cash amount remains unchanged.
- Gross, tax and net are stored only when provided by source evidence. Missing components stay absent and monthly
  coverage remains partial rather than treating unknown as zero.
- Routine/backfill plans stop above 64/320 physical calls or 10 pages per partition. Capacity stops above 1 GiB of
  private source objects or 500,000 Silver rows.
- Partial quality cannot advance a partition watermark, and a passing watermark cannot move backwards.
- Governed Parquet export and a fresh DuckDB restore reproduce dividend identities and current views.

## Recovery and rollback manifest

This isolated phase created no production state to roll back. Before production activation, rollback is:

1. Keep `pipeline.dividend-ledger-v1`, Scheduler, source adapters and public consumers inactive.
2. Do not apply migration 0015 to production, or if a separately approved future release has applied it, stop all new
   writers and keep the additive objects as an abandoned version while V1/main writers and cash consumers continue.
3. Do not drop the new objects or rewrite cash/action history. Any cleanup or mapping is a separately approved
   destructive Work Item after backup and consumer inventory.
4. Restore only from the governed V2 manifest and verify every table row count plus every rebuild view on a fresh
   database before any recovery is accepted.

The fail-closed legacy preflight is the release blocker: any non-zero legacy row or unknown consumer requires a new
mapping/reconciliation Work Item instead of automatic adoption.

## Cost and release guardrail

- External source calls: 0
- Live DB reads/writes or migration: 0
- New stored production bytes: 0
- Credential, Secret Manager or IAM changes: 0
- Cloud Run, Scheduler, public MCP or Telegram changes: 0
- Production release/cutover/cleanup: 0

The approved 64/320 call ceilings, 10-page partition cap and 1 GiB/500,000-row stop lines are implemented as planning
guards only. They do not activate or authorize a provider call, schedule, database migration or consumer.

## Verification evidence

- Focused migration and WI-038 suite: `10 passed`.
- Filing/dividend/warehouse/package integration selection: `33 passed`.
- `bash scripts/check.sh quick`: passed.
- `bash scripts/check.sh full`: `539 passed`, one existing Authlib deprecation warning.

No KIS/OpenDART network call, account statement, live dividend value, secret or production resource was used.
