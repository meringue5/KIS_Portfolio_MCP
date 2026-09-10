# WI-037 isolated filing implementation evidence — 2026-09-10

> execution scope: isolated
> production effects: none
> result: repository implementation verified; governed contracts remain approved and runtime inactive

## Delivered boundary

- Migration `0014_filing_actual_revision_ledger.sql` creates additive issuer alias, filing identity/revision,
  financial fact revision and concept-mapping objects. It preserves the 0001 legacy foundations and aborts before
  DDL if either contains rows.
- OpenDART and SEC fixture normalizers retain provider identity, original taxonomy/context, exact object hash and dual
  clocks. OpenDART day-grain availability advances to the next KST midnight; SEC acceptance keeps second precision.
- Silver publish requires an exact governed observation, matching private object manifest and a validity-applicable
  official `corp_code` or zero-padded CIK alias. Ticker/name heuristics are not an authority path.
- Filing and fact writes are content-addressed append-only revisions. Only explicit verified correction targets
  supersede; candidate corrections remain visible and partial.
- `system_as_of` and labeled `retrospective_source_as_of` queries select independently. Reviewed concept mappings are
  joined at query cutoff and never overwrite immutable source facts.
- Call-plan validation enforces approved OpenDART 100/250 and SEC 64/320 ceilings. A partition watermark can advance
  only from matching persisted quality evidence and cannot move backward.

## Recovery, safety and cost evidence

- Filing objects reject non-official hosts, unapproved media, credential-shaped metadata, encrypted archives,
  traversal paths, objects above 50 MiB, expanded archives above 200 MiB or 2,000 members.
- The private fixture object round-trip verifies SHA-256 bytes. The complete governed V2 Parquet allowlist restores
  the new filing revision rows into a fresh DuckDB; object bytes remain a separately declared private-object duty.
- The machine and human catalogs agree on 83 V2 objects: 64 tables and 19 views. New table backup policies are derived
  from `V2_DATA_OBJECTS`; no live inventory was adopted or changed.
- No external request, OpenDART key, KIS account credential, production DB connection, GCS operation, Cloud Run,
  Scheduler, IAM/Secret, public MCP or Telegram path was used.

## Verification

- `uv run pytest tests/test_v2_migrations.py tests/test_v2_filing_actuals.py tests/test_v2_recovery.py -q`:
  15 passed.
- `bash scripts/check.sh quick`: Project OS, DGH (162 contracts), Architecture, Warehouse and MCP surface passed.
- `bash scripts/check.sh full`: 532 passed; all shared contracts passed.
- Implementation commit: `1078d67`; current-state-independent Project OS fixture correction: `68877a8`.

## Deferred production gate

Contracts stay `approved`, not `active`. Production migration 0014, OpenDART credential/accessor, live source sample,
backfill, Scheduler/Cloud Run registration and public MCP consumption require the MS-002 `closed` production gate and
a release-phase manifest. Rollback for that later phase is disable accessor/schedule and return to the prior minimum
schema/image; append-only objects and rows are preserved rather than deleted.
