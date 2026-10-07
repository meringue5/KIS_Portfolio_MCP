---
id: WI-066
title: Quarantine incomplete legacy total-asset history and restore truthful longitudinal analysis
status: in_progress
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
execution_scope: isolated implementation and read-only production profiling complete; production migration and release pending approval
production_effects: none
architecture_impact: none; enforce the approved legacy quality contract without changing SSOT, grain, public tools or trust boundaries
data_impact: repository migration 0020 and read projection quarantine retained v1-latest totals without rewriting source rows; no production write has occurred
security_impact: none; retain confidential portfolio-data handling and aggregate-only evidence
cost_impact: read-only warehouse inspection and deterministic fixtures only until a separately approved production correction
user_visible_impact: yes
real_use_acceptance: required
real_use_evidence_refs: pending Codex and owner-Claude longitudinal-history replay after an approved correction
stabilization_window: none
stabilization_exit_refs: none
rollback_plan: before production no-op; after an approved release use a successor migration to restore the prior view while retaining migration history and all original V1/V2 rows
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
- Approval boundary: the owner approved WI-066 implementation on 2026-10-07. The current phase remains isolated and
  read-only against production; production migration, backfill, rewrite, deployment or source calls require a reviewed
  plan and explicit authorization.

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
- [ ] Any recoverable historical correction is append-only, source-grounded, idempotent, reconciled, privately backed
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
- Deployment/rollback: not yet authorized. A future release must capture the current read model and preserve original
  rows so rollback does not erase evidence.
- Cost/SLO: initial investigation is DB-only. Any source replay or production backfill requires a separate bounded
  call/cost plan.

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

1. Obtain explicit owner approval for a protected production migration/release; code implementation approval alone
   did not authorize this effect.
2. Capture a private pre-migration backup and verify fresh restore at migration `0019`.
3. Apply view-only migration `0020`, verify the view fixture against production counts, then capture and fresh-restore
   the post-migration backup. Do not update or delete retained rows.
4. Deploy the same immutable digest only after the migration succeeds; verify health/auth plus immediate Codex MCP
   positive/current, partial/legacy and error/unsupported-grain calls.
5. Ask the owner to repeat the longitudinal question in Claude. Keep the item `in_progress` until both clients no
   longer interpret the legacy gap as an observed drawdown.

## Sub-items

- `none` at intake. Separate a destructive migration, new source activation or materially independent reconstruction
  outcome rather than silently expanding this Work Item.

## Stabilization plan

- Observation period/sample: to be defined before `stabilizing`; must include representative verified legacy,
  incomplete legacy and current V2-native dates.
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
- `bash scripts/check.sh quick`: passed. `bash scripts/check.sh full`: 803 passed, one pre-existing Authlib
  deprecation warning.
- No production write, source call, deployment, external notification or destructive operation occurred during intake.

## Closeout

- Result: isolated implementation and immediate MCP boundary verification are complete; the item remains the sole
  `in_progress` Work Item because production migration/release and owner-Claude acceptance are not authorized or done.
- Remaining risk: production clients can still misinterpret some migrated legacy totals as actual loss/recovery until
  migration `0020` and the matching Remote revision are released.
- Follow-up Work Item: none yet; allocate one only if recovery requires an independent source/backfill outcome.
