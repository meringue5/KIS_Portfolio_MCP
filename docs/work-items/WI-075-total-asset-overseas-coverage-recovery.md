---
id: WI-075
title: Prevent incomplete overseas coverage from being reported as total assets
status: stabilizing
type: incident
owner: owner
decision_refs: DEC-055, DEC-057, ADR-029
requirement_refs: DGOV-007, DGOV-008
milestone_ref: MS-002
delivery_refs: none
parent_work_item: none
depends_on: WI-055
discovered_from: WI-055, WI-059
supersedes: none
rollback_of: none
work_lane: operations
execution_scope: protected production correction approved by owner on 2026-10-16
production_effects: update the three existing owned-core Jobs from one immutable image after finance-free transport smoke
architecture_impact: none; preserve the existing KIS source, managed pipeline, Gold state and Telegram boundaries
data_impact: strengthen existing collection and publish quality; no DDL, migration, backfill, rewrite or deletion
security_impact: none; existing Secret Manager references and owner-only destination remain unchanged
cost_impact: exceptional later-slot overseas recovery only when the same-day anchor is missing; existing call cap remains 65
user_visible_impact: yes
real_use_acceptance: required
real_use_evidence_refs: deterministic recovery and fail-closed fixtures; PR 162; GitHub run 38759300465; finance-free smoke execution kis-portfolio-wi030-s03-wnqxq passed; next complete owner report pending
stabilization_window: protected release plus the next 10:00 and 16:00 owner-report slots including one controlled missing-anchor scenario
stabilization_exit_refs: exact image and Job labels, overseas-anchor quality evidence, complete component count and owner receipt
rollback_plan: restore the prior three-Job image or disable only the owner report; retain run, Gold and delivery evidence without replay
---

# WI-075 — Prevent incomplete overseas coverage from being reported as total assets

## Problem and evidence

The 2026-10-15 10:00 owned-core run failed on KIS `EGW00215`. The later domestic-only runs succeeded and published
27 passing Gold components even though the prior 16:00 state had 32. All five configured accounts were present, but
five overseas positions worth roughly KRW 249.6 million were absent. The 16:00 owner report therefore sent KRW
389.2 million as total assets instead of the owner's roughly KRW 600 million complete portfolio.

## Classification and contract

- Classification: production incident and defect in the closed MS-002 outcome; use the `operations` lane without a
  new milestone or reopening history.
- Existing contract: incomplete or stale inputs must block official Gold publish or remain explicitly degraded, and
  the owner report may call a value total assets only when all required account, price, FX and component coverage passes.
- Contract delta: compatible pipeline minor version clarifies the already-approved completeness and recovery rule.
- Approval: owner approved implementation, PR, merge and deployment on 2026-10-16.

## Scope

- Include: same-day overseas collection anchor, bounded 14:30/16:00 recovery, fail-closed quality, three bounded
  balance rate-limit retries, regression tests and protected three-Job release.
- Exclude: historical row rewrite, missed-message replay, new schedules/providers/schema, watchlist work and threshold changes.

## Acceptance criteria

- [x] A failed 10:00 anchor causes the first later slot to collect overseas scope once within the existing call cap.
- [x] A valid same-day anchor prevents duplicate later-slot overseas calls.
- [x] Missing or failed overseas recovery prevents Gold publish and exact total-asset delivery.
- [x] Account balance `EGW00215` receives three bounded idempotent retries without changing order behavior.
- [x] The three Jobs use one immutable image and preserve permanent held-position signals plus owner report flags.
- [ ] Actual transport smoke and the next complete owner report provide user-visible acceptance evidence.

## Change impact

- Architecture: none.
- Data/schema/backup: no physical change; existing observations and failed runs remain immutable.
- Security/privacy: no new secret or payload field.
- MCP/API compatibility: no public schema change.
- Deployment/rollback: protected build-once target; prior image remains the rollback artifact.
- Cost/SLO: normal slots unchanged; one bounded recovery collection only after a missing daily anchor.

## Plan

1. Freeze the missing-anchor and false-pass regressions.
2. Add explicit collection-scope evidence and later-slot recovery.
3. Strengthen the quality gate and balance retry boundary.
4. Run focused, quick and full checks.
5. Merge and deploy through GitHub Actions; reconcile exact labels and finance-free smoke.

## Sub-items

- `WI-075-S01` (`stabilizing`): when the current total is complete but the prior same-slot comparison is unavailable,
  preserve the full owner photo layout and current total/account/asset allocations. Replace only D/D and Top 5 with
  an explicit comparison-unavailable state. PR #164 and protected run `39044692160` deployed it to all three Jobs on
  the same immutable image as WI-076 after a successful photo-capable Rich transport smoke. This corrects the
  owner-visible presentation without weakening the current-state completeness gate or inventing a comparison; the
  next applicable 10:00 owner receipt remains the stabilization exit.

## Stabilization plan

- Observation: the first post-release 10:00 and 16:00 states plus any missing-anchor recovery.
- Signals: pipeline version, overseas anchor source slot, Gold component/account counts, total quality and report outcome.
- Rollback: any duplicate collection, unsafe send or unexplained total restores the prior image or disables the report.
- Exit: complete total, provider-confirmed delivery and owner receipt.

## Real-use acceptance

- Actual client/transport: production Cloud Run Jobs and the approved private Telegram destination.
- Immediate positive: deterministic missing-anchor recovery plus finance-free photo transport smoke.
- Immediate partial/error: deterministic missing/failed recovery prevents publish and numeric total output.
- Remaining acceptance: next scheduled complete total and owner receipt; no historical replay.

## Evidence

- Intake: 2026-10-15 `kr-1600` had 27 rows and KRW 389,191,496 versus 2026-10-14's 32 rows and KRW
  638,786,242. Five overseas position rows were absent while all five account aliases and every persisted row passed.
- Focused recovery, owner-report, KIS client and release tests: 144 passed. The missing-anchor fixture recovers at
  `kr-1430`, reuses that anchor at `kr-1600`, and records two passing `same-day-overseas-scope` quality results. The
  recovery-failure fixture leaves `gold.portfolio_daily_state` at zero rows for the logical date.
- `bash scripts/check.sh quick`: passed with 74 tracked Work Items and WI-075 as the sole active implementation.
- `bash scripts/check.sh full`: 850 passed with one existing Authlib deprecation warning; all Project OS, data,
  architecture, warehouse, MCP and documentation gates passed.
- PR #162 merged as `021ea3c9c1e5265e2bcfe1598473328f0af186f8`; protected GitHub run `38759300465`
  passed from that exact `master` SHA.
- The release built once and pinned all three owned-core Jobs to
  `sha256:4a3e9b4e9bf964937858e7a61d10856b1ee1118bf63e04772d15b0f97b4ea8d9` with
  `deploy-target=wi075-total-asset-completeness`, the merge SHA and the GitHub run ID.
- Live Job reconciliation confirmed delivery enabled, canary disabled, real-use signals enabled, V2 owner report
  enabled, legacy digest disabled, and approved destination `dest.owner.primary` on the 10:00, 14:30 and 16:00 Jobs.
- Finance-free photo transport execution `kis-portfolio-wi030-s03-wnqxq` completed successfully with one succeeded
  task and labels `deploy-target=wi075-photo-transport-smoke`, the merge SHA and the GitHub run ID.

## Closeout

- Result: stabilizing after protected production release and finance-free transport smoke.
- Remaining risk: the next scheduled 10:00 and 16:00 runs must prove complete same-day overseas coverage, correct
  total-asset value, provider-confirmed delivery and owner receipt; no historical report was replayed.
- Follow-up Work Item: none.
