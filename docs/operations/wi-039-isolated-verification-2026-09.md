# WI-039 isolated macro profile verification — 2026-09-10

> Work Item: `WI-039`
> Execution scope: `isolated`
> Production effects: `none`
> Implementation commit: `03ab6690d403440f4d9b1650c7f319ec26174d6a`

## Result

WI-039 implemented the approved ADR-027 boundary in repository code and fresh local DuckDB databases only. The runtime
registry is exactly the five ECOS and twelve FRED/ALFRED series in `collection.macro-profile-v1` 2.0.0. Every series
remains inactive, preserves source owner, provider identity, unit, frequency, seasonal adjustment, rights and
attribution, and fails closed before future source I/O without an explicit production activation.

Migration `0016_macro_profile.sql` is additive and has SHA-256
`91c057e1702d76a5b44f4db6dcdb92684306f04c68dc03d5c5792e52c41555e6`. It adds 3 tables and 2 views, taking the
governed V2 catalog to 100 objects: 74 tables and 26 views. It does not drop, rename or update an existing object.

## Verified boundaries

- Fresh migration applies through 0016, second apply is a no-op, and a non-empty legacy macro foundation aborts before
  any automatic adoption or deletion.
- Definition projection is immutable and exact. Unknown series IDs, provider identity drift, unit/frequency/seasonal
  drift and duplicate provider identity fail closed.
- FRED/ALFRED revisions retain provider realtime start/end and day precision. Both `system_as_of` and labeled
  `retrospective_source_as_of` exclude future or expired vintages.
- ECOS revisions use observed content with `knowledge_at=fetched_at`; they do not fabricate a provider publication
  time or realtime interval. Retrospective source-as-of therefore returns no eligible ECOS row.
- Provider missing markers remain null with `missing_reason=provider_missing`; they are never converted to zero.
- YoY percent, period delta, quarterly annualized growth, yield-curve state and VIX regime use Decimal formulas and
  explicit missing, zero-denominator, non-positive and exact 20/30/40 boundaries.
- FRED routine/backfill plans stop above 32/256 calls; ECOS stops above 16/96; every series partition stops above ten
  pages. Capacity enters review at 80% and stops above 512 MiB Bronze, 500,000 Silver or 100,000 Gold rows.
- Only a matching passing quality result advances its partition watermark, and a cursor cannot move backwards.
- Governed Parquet export and a fresh DuckDB restore reproduce exact definitions and Gold snapshots and compile the
  current and as-of views.

## Recovery and rollback manifest

This isolated phase created no production state to roll back. Before production activation, rollback is:

1. Keep `pipeline.macro-profile-v2`, all 17 source definitions, source adapters, Scheduler and public consumers
   inactive.
2. Do not apply migration 0016 to production. If a separately approved future release applies it, stop new writers and
   preserve its additive objects as an abandoned version while existing V1/main consumers continue.
3. Do not drop new objects, rewrite revisions, invent ECOS release intervals or collapse the two query clocks. Any
   cleanup, mapping or profile supersession requires a separately approved destructive or corrective Work Item.
4. Restore only from the complete governed V2 manifest and verify every table count and rebuild view on a fresh
   database before accepting recovery.

The fail-closed legacy preflight is the release blocker: any legacy macro row or unknown consumer requires explicit
mapping and reconciliation rather than automatic adoption.

## Cost and release guardrail

- External ECOS/FRED/ALFRED/Cboe calls: 0
- Live DB reads, writes or migration: 0
- New production storage: 0 bytes
- Credential, Secret Manager or IAM changes: 0
- Cloud Run, Scheduler, public MCP or Telegram changes: 0
- Production release, backfill, cleanup or cutover: 0

The implemented call and capacity ceilings are inactive planning guards. They do not activate or authorize a provider
call, credential, schedule, database migration, consumer or release.

## Verification evidence

- Focused migration and WI-039 suite: `12 passed`.
- Macro/migration/metric/backup-recovery/warehouse integration selection: `21 passed`.
- `bash scripts/check.sh quick`: passed.
- `bash scripts/check.sh full`: `549 passed`, one existing Authlib deprecation warning.

No account data, production macro value, raw provider response, secret or production resource was used. Both JSON
fixtures are conspicuously synthetic and marked fixture-only.
