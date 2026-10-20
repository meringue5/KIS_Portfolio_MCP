---
id: WI-064
title: Eliminate duplicate current trade events without erasing source history
status: closed
type: defect
owner: owner
decision_refs: DEC-009, DEC-010, DEC-015
requirement_refs: DEC-009, DEC-010
milestone_ref: MS-008
delivery_refs: none
parent_work_item: none
depends_on: WI-063
discovered_from: WI-063
supersedes: none
rollback_of: none
execution_scope: closed owner-accepted production identity repair; documentation synchronization only
production_effects: applied migration 0022 and updated the two existing trade Job images; source/history and all other operating paths preserved
architecture_impact: none; repair the existing approved executed-order natural key using source-proven aliases, without a new SSOT or grain
data_impact: preserve all observations and revisions; correct only canonical current-event projection and evidence
security_impact: no new public identifiers or raw provider payloads
cost_impact: DB-only diagnosis and projection work expected
user_visible_impact: yes
real_use_acceptance: required
real_use_evidence_refs: governance/project/evidence/wi064/codex-production-acceptance-2026-10-18.json; governance/project/evidence/wi064/production-data-audit-2026-10-18.json
stabilization_window: immediate corrected OAuth positive/partial/error and source/reference reconciliation completed on 2026-10-18; owner acceptance recorded in accepted-closeout-2026-10-21.json
stabilization_exit_refs: governance/project/evidence/wi064/protected-production-release-2026-10-18.json; governance/project/evidence/wi064/codex-production-acceptance-2026-10-18.json; governance/project/evidence/accepted-closeout-2026-10-21.json
rollback_plan: restore reviewed pre-0022 trade/lot read views while preserving all source/revision rows and migration history; restore exact prior trade Job exports if necessary
---

# WI-064 — Eliminate duplicate current trade events without erasing source history

## Problem and evidence

The WI-063 direct Codex OAuth populated-window check returned four current RIA trade rows for 2026-08-25, but the
rows formed two pairs with the same account, market, instrument, execution timestamp, side, quantity, price and
currency while differing in `trade_event_id` and `knowledge_at`. A read-only production aggregate on 2026-09-30
found 19 such duplicate business-key groups in `silver.trade_events_current`.

This is not evidence that source history should be deleted. It is evidence that the current-event identity and
revision projection need a separate review before a user-facing ledger can be called economically deduplicated.

## Classification and contract

- Initial classification: independent data-correctness defect discovered during WI-063 real-use acceptance.
- Contract: Bronze observations and revisions remain append-only; a current Silver read must not double-count one
  economic event merely because it was observed again.
- Approval: diagnosis may be read-only; implementation starts only after WI-063 is no longer the active Work Item.

## Scope

- Include: prove whether duplicates are repeat observations or legitimately distinct fills; define stable business
  identity, revision ordering and reconciliation evidence; repair the current projection and MCP fixture.
- Exclude: deleting Bronze observations, guessing trades from positions, or silently collapsing distinct executions.

## Acceptance criteria

- [x] Every candidate duplicate group is classified from governed source fields without exposing account numbers.
- [x] Repeated observations resolve to one current economic event while legitimate equal-price fills remain distinct.
- [x] Historical and populated-window MCP results reconcile to the corrected Silver projection.
- [x] Direct Codex OAuth positive/partial/error scenarios and full repository gate pass.

## Change impact

- Architecture: likely Silver identity/projection correction, not a new source producer.
- Data/schema/backup: append-only inputs retained; any view or migration change follows warehouse governance.
- Security/privacy: aggregate evidence only.
- MCP/API compatibility: row counts may decrease where repeated observations were double-counted.
- Deployment/rollback: additive projection/migration with prior view definition retained.
- Cost/SLO: DB-only read path; no additional KIS calls.

## Plan

1. Trace duplicate groups through Bronze, normalized revisions and current-view partition keys.
2. Freeze a fixture that distinguishes repeated observation from identical legitimate fills.
3. Implement and replay the smallest governed Silver correction.
4. Verify through the owner-authenticated Codex MCP connection.

## Sub-items

- `none`.

## Stabilization plan

- Observation: aggregate duplicate count and representative populated windows before/after correction.
- Signals: input observation count, classified economic-event count, revision selection and MCP row count.
- Rollback: restore the prior current projection; never delete source observations.
- Exit: zero unexplained duplicate groups plus owner acceptance of direct MCP evidence.

## Real-use acceptance

- Actual client: owner-authenticated Codex OAuth MCP.
- Positive: populated historical window returns reconciled unique current events.
- Partial: an uncovered account/window remains explicit.
- Error: invalid request stays owner-debuggable without raw identifiers.

## Evidence

- Direct MCP RIA query for 2026-08-25 returned four rows representing two identical business-key pairs.
- Production aggregate on 2026-09-30 counted 19 duplicate business-key groups.

## Historical closeout checkpoint (superseded 2026-10-21)

- Result: production repair and immediate actual OAuth validation complete; stabilizing pending explicit owner acceptance.
- Remaining risk: source evidence with incomplete/ambiguous broker identity stays separate; unrelated cash fee candidates and historical lower-bound coverage limitations remain explicit. Owner review of corrected actual-client result is pending.
- Follow-up Work Item: none.

- 2026-10-18: owner explicitly requested fixing WI-064 within its existing outcome. WI-063 is stabilizing; MS-005 is closed. WI-072 is blocked with preservation/resume conditions, making WI-064 the sole implementation WIP. Existing unrelated checkout changes remain unstaged and preserved. Implementation authorization does not bypass production release approval.


### 2026-10-18 implementation and validation

- Owner explicitly prioritized the existing WI-064; no new Work Item/sub-item was created. Classify as a defect:
  `dataset.trade-event` already defines the executed-order natural key. Its patch contract v1.1.1 clarifies the
  physical alias implementation without changing natural key, source, retention, trust boundary or public schema.
- Reconfirmed live 300 current rows, 19 candidate groups/38 rows (RIA 17, ISA 1, pension 1); all eight normalized
  source order fields present/equal in every pair. Old 3-component and collected 5-component broker identifiers differ.
- Migration 0022 derives unambiguous source-proven legacy/current identity aliases and repairs current trade/lot
  views. Historical IDs, revisions, raw payloads and all stored references remain intact. Latest revision is chosen
  within source identity before latest knowledge across proven aliases; missing/ambiguous evidence never merges.
- Repository correction fixes the base-event PK conflict on revision >1, keeps immutable base facts and appends
  later changed aggregate revisions. Replay is idempotent; stale knowledge cannot overwrite newer facts; conflicting
  explicit revisions/same-knowledge corrections fail. Correction/replay regression fixtures are synthetic.
- Production backup was exported privately and restored locally at prefix 0021. Rehearsal applies only 0022:
  current rows 300→281, duplicate candidates 19→0, alias links 19, current compatibility lots 19→19. All 79 data-table
  count/hash fingerprints match. Threads/links 19 each, journal revisions 3, canonical reconstructed lots and
  allocation sets/revisions 0; no stored reconstruction is silently rebuilt.
- Pre/post fresh restore, historical ID resolution and local transactional rollback to 300 rows verified.
  Private object bytes are not part of table backup; no object metadata/content is changed by this repair.
- Cash check: 77 events, no links to legacy imported observations. Nine same-economics groups (all fee) are a
  separate incomplete-identity classification: eight have identical source bytes but distinct record/ordinal IDs;
  source rows lack broker order identity. They cannot be collapsed by this trade alias rule. Keep the cash monetary
  SSOT/77 rows intact; no claim that same cash amount or bytes proves duplicate economic events.
- Actual Codex OAuth baseline still returns four rows/quality pass for the two RIA orders; request
  `166c22f174674d0fb2bbb34dba977713`. Actual uncovered 2026-10-17..18 returns partial coverage gap
  (`c9c8caab05894ab9b13d3345bf5a1a32`); reversed dates return invalid_request
  (`ff574f1a0b614b44b03dda9f40e515a9`). These are baseline evidence, not corrected-production acceptance.
- An exploratory 2020 empty query returns pass because current coverage tracks only the upper watermark; request
  `17fa5da18ff144a789d43c7f461f4fde`. Route this lower-bound coverage limitation to the existing WI-063 collection
  coverage outcome; it is not evidence that 2020 history is complete and does not change this identity repair scope.
- Local production-backup read-port replay returns the expected two RIA events. See
  [rehearsal](../../governance/project/evidence/wi064/local-rehearsal-2026-10-18.json),
  [read-port evidence](../../governance/project/evidence/wi064/local-read-port-2026-10-18.json), and
  [reviewable production plan](../operations/wi-064-identity-repair-2026-10-18.md).
- Protected release runner and normal GitHub Actions `wi064` target prepare pre/post private GCS backup/fresh
  restore, preflight clone verification, migration-only source-preserving reconciliation and prior-view rollback.
  Only the existing two trade Job images are updated, with exact Job export rollback on failure. Remote OAuth,
  routes, schedules, held/watchlist operating paths and source activation are unchanged.

- Final isolated gate 2026-10-18: quick passed; full passed **885 tests**, one preexisting Authlib deprecation warning. Protected runner also executed end-to-end on the actual production-backup local clone with an in-memory object store: 281 current rows/19 aliases, 79 table fingerprints preserved, complete pre/post 80-object backup/fresh-restore rounds. This is not a production/GCS or OAuth release claim. Status `verified` leaves production approval and corrected actual-client/owner acceptance open; it does not close WI-064.

- Owner approved remaining WI-064 integration and production reflection in this chat on 2026-10-18. Proceed through the normal isolated PR/CI/master production workflow; preserve unrelated work and collect actual corrected OAuth evidence before closeout.

- Isolated integration on latest master `1565464` passed the full gate: **876 tests**, one existing Authlib warning. Shared-tree 885 included unrelated isolated tests; only WI-064 code/contracts/evidence are included in this release branch. Original checkout/index were not modified by integration.


### Production release and actual client evidence — 2026-10-18

- Owner approved the remaining normal PR/CI/production work in this chat. Isolated [PR #166](https://github.com/meringue5/KIS_Portfolio_MCP/pull/166)
  merged as `dca956d791ae30bfc547dd5bedecaf3ab7674449`; PR CI `39105134552` and master CI `39105324853` passed.
- Normal protected [workflow 39105328346](https://github.com/meringue5/KIS_Portfolio_MCP/actions/runs/39105328346)
  succeeded. Execution `kis-portfolio-wi064-mhb6n` applied only `0022`; all 79 managed data-table fingerprints were
  preserved, with complete pre/post private 80-object backup/upload/download/fresh restore. Exact aggregate evidence:
  [protected release](../../governance/project/evidence/wi064/protected-production-release-2026-10-18.json).
- Deployed image digest `sha256:8c7be494048e10168ee273795fc9ce5cf12ae152478bf7b1a3248a6daf7300f6` matches both
  existing trade Jobs and release SHA/run/source labels. Their non-image runtime specs (args/env/secrets/service
  account/task settings) are exactly preserved. Remote generation/routes and all eight Scheduler definitions,
  targets and states are unchanged. No KIS collection, notification or watchlist activation was triggered.
- Independent direct production audit: 300→281 current rows; 19 proven aliases; zero duplicate candidates; all
  262 uninvolved current events are byte-value equivalent; 12 separately captured source/reference table fingerprints
  match pre-release. Bronze 43,455, base trade/revision rows 300 each, cash facts/classifications 77 each,
  compatibility lots/threads/links 19 each, journal revisions 3. All historical source/revision IDs resolve;
  existing current lot rows are exactly preserved. [Data audit](../../governance/project/evidence/wi064/production-data-audit-2026-10-18.json)
  and [resource audit](../../governance/project/evidence/wi064/production-resources-2026-10-18.json).
- Actual approved Codex OAuth: RIA 2026-08-25 now returns **2** current rows with pass
  (`73b10b6a1a524a9b9306194ad2d356f0`); uncovered 2026-10-17..18 returns partial
  (`1d95518152484d3ca71ed75142c4e01c`); reversed dates retain owner-debug invalid_request
  (`5275f62fc0f549b1bd590c4c53e85a04`). [Actual-client evidence](../../governance/project/evidence/wi064/codex-production-acceptance-2026-10-18.json).
- The operational defect is corrected and immediately verified. Keep `stabilizing`, not `closed`, until the owner
  accepts the corrected actual-client result. No new Work Item or derived ticket replaces WI-064.

- Live inventory `--fail-on-unregistered-drift` passed: zero missing managed objects, alias view managed, four exact registered legacy drift exceptions and zero review blockers. No drift adoption/deletion. [Inventory evidence](../../governance/project/evidence/wi064/production-inventory-2026-10-18.json).

- Post-release evidence full gate passed again: **876 tests**, one existing Authlib warning; original shared checkout quick gate also passed after synchronizing only WI-064 evidence/status. No unrelated source changes were committed or discarded.

## Closeout

- Classification: maintenance of the existing outcome's acceptance record, authorized by the owner to publish
  the already accepted closure and proceed to the remaining review sequence. No new implementation work.
- [Owner acceptance and actual-client replay](../../governance/project/evidence/accepted-closeout-2026-10-21.json)
  is the final disposition; earlier intake/stabilizing paragraphs above remain historical checkpoints.
- No production migration, source collection, monetary update, notification or deployment was required for this
  record synchronization. The dirty shared checkout and unrelated work remain untouched.

- Result: closed; protected 0022 repair, source/reference preservation and actual OAuth positive/partial/error
  passed. Owner recognized reflection complete on 2026-10-18 and authorized record publication on 2026-10-21.
- Current independent replay: RIA 2026-08-25 exactly two rows/pass; before-start 2020 empty window partial;
  reversed range invalid_request. WI-063 coverage correction is independently accepted and closed.
