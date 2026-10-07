---
id: WI-066
title: Quarantine incomplete legacy total-asset history and restore truthful longitudinal analysis
status: stabilizing
type: defect
owner: owner
decision_refs: DEC-003, DEC-005, DEC-006, DEC-015, DEC-030, DEC-038, DEC-045, DEC-046, ADR-023
requirement_refs: DEC-003, DEC-005, DEC-006, DEC-015, DEC-030, DEC-038, DGOV-007, DGOV-008
milestone_ref: MS-008
delivery_refs: none
parent_work_item: none
depends_on: WI-065
discovered_from: WI-065
supersedes: none
rollback_of: none
execution_scope: protected production migration, Remote release and Codex actual-client acceptance complete; owner-Claude replay pending
production_effects: private pre/post backup and fresh restore, view-only migration 0020, and one Remote revision serving stable plus wi046-v2; no source calls or row rewrite
architecture_impact: none; enforce the approved legacy quality contract without changing SSOT, grain, public tools or trust boundaries
data_impact: production migration 0020 replaced only the derived read view; all 3273 portfolio state rows were fingerprint-preserved and retained v1-latest totals remain stored but quarantined
security_impact: none; retain confidential portfolio-data handling and aggregate-only evidence
cost_impact: bounded Cloud Builds, one single-task Cloud Run migration Job at an explicit 2 GiB memory limit, one Remote revision and two private backups capped at 10 GiB each
user_visible_impact: yes
real_use_acceptance: required
real_use_evidence_refs: run 37693993263; Codex current, legacy, unsupported-grain, overview and pipeline calls passed; owner-Claude longitudinal replay pending
stabilization_window: immediate Codex positive, partial and error replay followed by owner-Claude longitudinal replay
stabilization_exit_refs: protected production run, pre/post backup and fresh-restore evidence, migration 0020, exact Remote labels/routes, Codex replay and owner-Claude acceptance
rollback_plan: restore stable and wi046-v2 traffic to the captured prior revisions on Remote smoke failure; use a successor migration for a read-model rollback while retaining migration history and all original V1/V2 rows
---

# WI-066 — Quarantine incomplete legacy total-asset history and restore truthful longitudinal analysis

## Problem and evidence

An owner real-use question about recovery from a purported July drawdown exposed a discontinuity that cannot be
explained as portfolio performance. Read-only production inspection found 36 retained V1 daily total-asset snapshots
from 2026-04-19 through 2026-09-09. The V1-to-V2 portfolio backfill copied 27 distinct dates from 2026-04-19 through
2026-08-27 into 889 `v1-latest` rows in `gold.portfolio_daily_state`.

The retained V1 aggregate changed from KRW 927,743,316 on 2026-06-20, including KRW 291,472,652 of overseas stock
and cash, to KRW 480,793,599 on 2026-07-24 with both overseas components recorded as zero. Overseas components remain
zero in the retained V1 daily aggregate through 2026-09-04 and reappear as KRW 234,552,810 on 2026-09-07. Therefore
the apparent July drawdown and September recovery mix portfolio movement with a missing overseas feeder and cannot be
used as investment performance.

The physical migration reconciled migrated holding sums to the already incomplete V1 overview total, so zero-KRW
reconciliation did not establish economic completeness. `scripts/migrate_v1_v2_portfolio.py` assigns migrated row
quality from grouped holding `value_krw IS NULL` only; it does not carry or reconstruct overview feeder coverage.
Legacy overview quality columns are null, and non-null domestic rows can consequently make a total with absent
overseas assets appear `pass`. The Remote performance read then exposes a numeric group whenever all migrated row
labels are `pass` or `passed`.

## Classification and contract

- Initial classification: high-severity data defect in legacy migration quality and longitudinal consumption.
- Compared contract: `dataset.portfolio-daily-state` requires input watermarks, component reconciliation and explicit
  degraded status for partial inputs. `docs/data-catalog.md` requires legacy rows to project as
  `legacy_unassessed`/incomplete rather than inferred `pass`.
- Contract result: physical preservation succeeded, but quality migration and downstream usability are below the
  approved contract. This is not evidence that the historical portfolio actually lost the omitted overseas amount.
- Approval boundary: the owner approved isolated implementation on 2026-10-07 and explicitly approved the complete
  protected backup, restore, migration, PR, deployment and immediate MCP validation process on 2026-10-08. This does
  not authorize source replay, historical row rewriting, destructive cleanup or a new provider.

## Scope

- Include a deterministic fixture reproducing a legacy overview whose holding sum reconciles while an expected
  overseas component is absent.
- Include date/component coverage profiling for every retained V1 daily overview and migrated `v1-latest` state.
- Include a fail-closed quality projection so unknown or incomplete legacy coverage cannot be labelled `pass` or
  used as a continuous portfolio-return series.
- Include bounded usability: preserve independently verified components and dates with explicit coverage instead of
  rejecting every historical value.
- Include a source-grounded recovery feasibility assessment using retained snapshots, trade/cash evidence, prices and
  FX. Reconstruct only when the inputs and reconciliation prove the result; otherwise retain an explicit gap.
- Include append-only correction, backup/restore, idempotency and actual MCP positive/partial/error acceptance if a
  production correction is later approved.
- Exclude destructive rewriting or deletion of V1 evidence, fabricated overseas values, inferred returns across the
  gap, new providers, public tool additions, order functionality and any unapproved production effect.

## Acceptance criteria

- [x] A regression proves that aggregate equality alone cannot pass a legacy day whose expected overseas feeder is
      absent or unassessed.
- [x] Every migrated `v1-latest` date receives the explicit `legacy_unassessed` disposition at the canonical view and
      Remote read boundary; unknown evidence never
      becomes `pass` by default.
- [x] `get-performance-history` preserves usable verified V2-native history while suppressing incomplete legacy
      totals so an LLM cannot describe the July gap as an observed portfolio crash.
- [x] Current V2-native states and current overview totals remain unchanged and continue to pass their existing
      quality gates.
- [x] Any recoverable historical correction is append-only, source-grounded, idempotent, reconciled, privately backed
      up and restorable; irrecoverable dates remain explicit gaps.
- [x] Focused, quick and full gates pass before release consideration.
- [ ] Actual Codex and owner-Claude OAuth calls immediately reproduce positive, partial and error behavior without
      waiting for a future scheduler slot.

## Change impact

- Architecture: no intended boundary change; V1 evidence remains retained and V2 Gold remains the governed consumer.
- Data/schema/backup: likely quality projection or additive correction evidence; exact migration and backup contract
  must be designed before implementation. No destructive rewrite is permitted.
- Security/privacy: confidential values remain owner-only; Work Item and test evidence use aggregate values and no
  account numbers, credentials or raw provider payloads.
- MCP/API compatibility: response envelope stays compatible, but previously false `pass` history may become explicit
  partial/unavailable with a specific missing-coverage reason.
- Deployment/rollback: authorized through the protected `wi066` target. It captures both current routes before change,
  migrates and restores before serving, and restores the prior stable and `wi046-v2` routes on Remote smoke failure.
- Cost/SLO: each release attempt is bounded to one build, one no-retry single-task Job, one Remote revision, one hour and two
  private backups of at most 10 GiB each. Source replay or production backfill remains separately gated.

## Implemented isolated correction

- Migration `0020_legacy_history_quality_quarantine.sql` rebuilds only the derived
  `gold.portfolio_daily_summary` view. It returns `NULL`/`legacy_unassessed` for every `v1-latest` group, accepts both
  retained `passed` and current `pass` only for non-legacy groups, and fails closed for every other quality value.
- `get-performance-history` applies the same rule directly to its account-filterable state query and returns the
  specific missing-coverage reason `legacy_history_unassessed`; it does not expose an internal reason field.
- A future replay of `scripts/migrate_v1_v2_portfolio.py` labels migrated position, cash and daily-state rows
  `legacy_unassessed` instead of inferring success from non-null values. Existing production rows remain untouched.
- Remote startup now requires migration `0020`, preventing code that promises the quarantine from serving against
  the current `0019` view.

## Plan

1. [done] Record the owner's 2026-10-08 authorization for the complete protected production migration/release process.
2. [done] Capture a private pre-migration backup and verify fresh restore at migration `0019`.
3. [done] Apply view-only migration `0020`, verify the view fixture against production counts, then capture and fresh-restore
   the post-migration backup. Do not update or delete retained rows.
4. [done] Deploy the same immutable digest only after the migration succeeds; verify health/auth plus immediate Codex MCP
   positive/current, partial/legacy and error/unsupported-grain calls.
5. Ask the owner to repeat the longitudinal question in Claude. Keep the item `stabilizing` until Claude no longer
   interprets the legacy gap as an observed drawdown.

## Sub-items

- `none` at intake. Separate a destructive migration, new source activation or materially independent reconstruction
  outcome rather than silently expanding this Work Item.

## Stabilization plan

- Observation period/sample: immediate Codex positive/current, partial/legacy and error/unsupported-grain calls, then
  the owner's original longitudinal question through Claude.
- Signals: component coverage, legacy disposition, reconciled totals, suppressed false totals, unaffected current
  overview and actual-client interpretation.
- Rollback trigger and safe state: any current-state regression, fabricated completeness, loss of retained evidence or
  restore mismatch; restore the captured read model while retaining append-only evidence.
- Exit evidence and owner acceptance: deterministic and live MCP acceptance plus owner confirmation that the system
  distinguishes an incomplete feeder interval from an actual portfolio drawdown.

## Real-use acceptance

- User-visible basis: yes; portfolio history directly informs the owner's loss, recovery and high-water-mark analysis.
- Actual approved clients/transports: authenticated Codex Remote MCP and owner Claude custom connector.
- Positive: a current V2-native date returns a usable total with lineage. No retained legacy date is currently proven
  complete enough to qualify as a positive total.
- Partial: a date in the overseas-zero interval preserves supported components but does not expose a complete total or
  return claim.
- Error: unsupported reconstruction or invalid range/selector returns a bounded, diagnosable owner-debug error without
  altering data.
- Findings must be assigned to this Work Item or a separately registered correction; transport success alone is not
  completion.

## Evidence

- Direct MCP `get-performance-history`, 2026-06-01 through 2026-10-05: 80 rows, overall partial, six explicitly
  degraded groups, and a discontinuity between retained V1 and native V2 levels.
- Read-only MotherDuck inventory: 57 retained `asset_overview_snapshots`, 36 daily representatives and 889 migrated
  `v1-latest` rows across 27 dates.
- Read-only component query: overseas assets KRW 291,472,652 on 2026-06-20; zero from 2026-07-24 through 2026-09-04;
  KRW 234,552,810 on 2026-09-07.
- Contract/code comparison: `docs/data-catalog.md`, `governance/catalog/datasets.toml`,
  `scripts/migrate_v1_v2_portfolio.py` and `remote_v2_warehouse.py`.
- Red regression before implementation: the legacy quarantine and migration tests both failed because `v1-latest`
  still returned/stored `pass` or `passed`.
- Focused implementation evidence: six core quarantine/migration/recovery tests passed; the broader warehouse,
  migration and recovery selection passed 53 tests.
- Immediate MCP tool-boundary fixture: `get-performance-history` returned a numeric `pass` current V2 total, a
  `NULL`/`legacy_unassessed` partial legacy row with `legacy_history_unassessed`, and an owner-debug
  `unsupported_performance_grain` error without a scheduler wait.
- Actual Codex production baseline on 2026-10-07: 2026-06-20 `v1-latest` still returned KRW 927,743,316 as `pass`,
  while 2026-07-24 returned `NULL`/`degraded`. This confirms production remains on the pre-fix behavior and is not
  post-release acceptance.
- Production preflight on 2026-10-08: protected `master` was the merged WI-066 implementation SHA, MotherDuck was
  exactly at migration `0019`, the four observed inventory differences matched registered preservation drift with no
  blocker, and stable plus `wi046-v2` both resolved to the captured pre-release Remote revision.
- Release-path red regression initially failed because the WI-066 release service did not exist. The implemented
  tests now require private backup/download/fresh restore on both sides of `0020`, no state-row mutation, idempotency,
  migration-before-route ordering, one immutable image and no Scheduler or IAM change.
- Protected run `37643171197` on 2026-10-08 passed repository gates and built the immutable image. It created and
  restored the pre-backup and applied view-only `0020`, then exhausted the Cloud Run default `512Mi` during later
  recovery work before Remote update. Original rows and both Remote routes remained unchanged. The corrective release
  set an explicit bounded `2Gi` limit and added a regression against silent platform-default fallback.
- Protected run `37693993263`, master `f472a24`, immutable digest `e481c195...14edd` and Remote revision
  `00058-5qk` succeeded. The resumable Job observed `0020` already applied, proved a no-op replay, restored both the
  pre and post snapshots with 79 governed objects each, preserved all 3,273 source rows exactly, quarantined all 27
  legacy groups, validated all 75 native groups, and recorded zero source calls, row mutations or deletions.
- Direct Codex production MCP acceptance on the released revision passed immediately: 2026-06-20 returned one
  `NULL`/`legacy_unassessed` partial row with `legacy_history_unassessed`; 2026-10-01 through 2026-10-07 returned 12
  numeric `pass` rows with no missing coverage; weekly grain returned owner-debug
  `unsupported_performance_grain`; unaffected overview returned pass/32 and no-selector pipeline returned pass/3 with
  all runs `succeeded`.
- `bash scripts/check.sh quick`: passed. `bash scripts/check.sh full`: 809 passed, one pre-existing Authlib
  deprecation warning.
- No source call, stored-row mutation, deletion, external notification or destructive operation occurred during the
  release. Only migration history/read view, private recovery objects and the approved Remote revision/routes changed.

## Closeout

- Result: implementation, protected production release and immediate Codex MCP acceptance are complete. WI-066 is
  `stabilizing` until the owner repeats the original longitudinal question through Claude.
- Remaining risk: the owner-Claude connector has not yet proved that its natural-language synthesis respects the new
  explicit legacy gap, although the shared released MCP contract now returns the correct partial evidence.
- Follow-up Work Item: none yet; allocate one only if recovery requires an independent source/backfill outcome.
