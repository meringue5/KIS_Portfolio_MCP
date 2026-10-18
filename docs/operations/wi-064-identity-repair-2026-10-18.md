# WI-064 identity repair — review and release plan

Status: verified locally; no production migration or deployment performed.
Owner requested the existing WI-064 be fixed on 2026-10-18. No successor ticket replaces it.

## Approved boundary and repair

The approved `dataset.trade-event` natural key already identifies one executed order within account/market/product,
instrument, source date, branch/order and exchange. Migration 0022 fixes two encodings of that key; it adds a
rebuild-only evidence view rather than changing the key/SSOT or deleting observations. Complete immutable KIS source
proof plus one-to-one linkage is required. Missing/ambiguous identifiers and genuinely different orders stay separate.
Within each source, revision ordering remains revision-first; across proven source aliases, latest knowledge wins.
The selected public trade ID remains an actual revision ID; source anchor is the legacy identity used by old lots.
All historical IDs and table rows remain addressable. Base compatibility lots retain original observed terms;
canonical reconstructed lot/allocation revisions are not rebuilt by a view migration.

`record_trade` now preserves the immutable base row when appending a correction, accepts matching explicit replay,
rejects conflicting explicit history and appends newer changed order-query aggregates instead of silently ignoring
them. Bronze content-addressed observation idempotency is unchanged; this is not a new source-observation cadence.

## Verified evidence

- Live source recheck: 300 current rows, 19 duplicate candidates/38 rows; all eight source proof fields match.
- Complete private local backup at prefix 0021: 79 exported tables; original/raw object bytes are a separate policy.
- Fresh local pre/post restore: 300→281 current rows, 19→0 duplicate candidates, 19 proven aliases; all 79 data-table
  count/hash fingerprints unchanged. Compatibility lots 19→19; thread/lot links 19 each, journal revisions 3;
  canonical reconstructed lots/allocations 0. Historical revision and source IDs resolve.
- Transactional view rollback restores 300 rows without source changes, then rollback of the test transaction leaves
  the corrected 281-row projection. Post-0022 backup restores the same result.
- Production-backup local warehouse read port returns exactly two RIA events on 2026-08-25; current approved Codex
  OAuth still returns four. Local replay is not claimed as corrected OAuth acceptance.
- Actual baseline partial (2026-10-17..18) and invalid-period error are recorded with request IDs in
  [Codex baseline](../../governance/project/evidence/wi064/codex-baseline-2026-10-18.json).
- Cash: 77 immutable rows; no legacy-observation links. Nine same-economics fee groups remain untouched. Eight have
  equal payload bytes but different source row/ordinal IDs and no broker order identity, so uniqueness cannot be
  decided by amount or bytes. No trade-settlement identity mapping is inferred from these fees.
- Lower-bound coverage limitation: 2020 empty query incorrectly looks covered because coverage has only an upper
  watermark. Existing WI-063 owns coverage; identity repair does not assert earlier complete history.

## Production execution (owner approved 2026-10-18)

Use only the reviewed, CI-verified WI-064 change set. Existing uncommitted WI-068/071/072/073/074 material must remain
preserved and must not be accidentally bundled into a release/commit. The working checkout itself is not a production
source. Stage/integrate only WI-064 hunks; resolve any integration dependency explicitly before merging to master.
No local dirty-source deployment is permitted by the Release Ops skill.

1. Review migration 0022, source-evidence rules, repository correction, regression fixtures and this plan. Integrate
   the isolated change through the normal PR/CI path; record exact SHA and immutable image digest.
2. On the approved master SHA, run the existing `Deploy Cloud Run` workflow with `target=wi064`. It uses the normal
   `production` environment gate. No workflow has been dispatched in this session.
3. The prepared deploy target snapshots exact existing domestic/overseas trade Job definitions, deploys the bounded
   one-off `kis-portfolio-wi064` migration Job (2 GiB, 3600s, zero task retries) with existing Secret Manager/SA scope,
   and runs `kis-portfolio-batch run-wi064-release --project <configured-project> --bucket <existing-private-bucket>`.
4. The protected runner requires prefix 0021/0022, immutable provenance and zero preexisting canonical reconstruction
   outputs. It uploads/downloads and fresh-restores the complete pre-backup, rehearses 0022 against that copy,
   checks every data-table fingerprint, applies only checksum migration 0022, verifies expected aliases/counts,
   and uploads/downloads/fresh-restores a post-backup. Unexpected state stops the release before updating producers.
   Concurrent source changes cause reconciliation failure; choose a reviewed quiet window rather than changing schedules.
5. Only after this succeeds, update the two existing trade Job images to the same tested digest. Keep args, secret
   bindings, schedules, Remote service/routes/OAuth, portfolio and watchlist activation untouched. No trade Job is
   executed by this target and no KIS backfill or notification is sent.
6. Immediately call the approved Codex OAuth MCP: RIA 2026-08-25 must return 2 rows; each of the 19 source-proven
   duplicate groups must reconcile to one current event, all unrelated orders/revisions must remain. Reproduce the
   coverage-gap partial and reversed-period error; compare source/reference hashes, cash 77 and lot/thread/journal
   references again. CI or Job success is not this actual-client evidence.
7. Record release/job IDs, SHA/digest, private backup index hashes, live inventory and direct OAuth request IDs in
   WI-064. Move to stabilizing/closed only after evidence and explicit owner acceptance; no clock-only waiting gate.

## Rollback and deliberate resume

- Before migration, restore/rehearsal failure performs no live DDL. After migration, verification failure restores the
  prior two read-view definitions in one transaction, retaining all data, alias view and applied migration ledger.
- After a producer-image failure, restore each attempted Job from its exact captured export, including labels/config;
  a successfully verified corrected DB projection remains valid and is not silently reverted with application images.
- For an accepted post-release view rollback, restore only the prior `trade_events_current`/`purchase_lots_current`
  definitions from the reviewed pre-0022 state. Never remove source/revision records or erase migration ledger rows.
- A failed/rolled-back projection is an explicit recovery state: the normal migration runner will not silently rerun
  an applied version. Review preserved pre/post evidence and deliberately reapply the checksum-pinned 0022 SQL (or a
  reviewed forward correction), then repeat restore, fingerprint and direct-client checks. Do not blindly retry.

Reproduce the local source-preservation rehearsal with:

```bash
uv run python scripts/rehearse_wi064.py <private-0021-backup> \
  --workspace <new-private-local-directory> --evidence <aggregate-evidence-json>
```

Evidence contains counts/booleans and opaque request IDs; no raw orders, accounts, credentials or private locators.

Final quick/full gate passed: **885 tests**, one preexisting Authlib warning. End-to-end protected runner on the production-backup local clone with a memory object store also verified 281 rows/19 aliases and complete pre/post 80-object backup/restore. This verifies execution logic, not real GCS, production migration or post-release OAuth acceptance.

Owner authorization in this chat: "네 나머지 반영을 이어가주세요" (2026-10-18). This authorizes the reviewed WI-064 PR/CI/master production workflow and immediate actual-client acceptance; it does not authorize unrelated release scope.
