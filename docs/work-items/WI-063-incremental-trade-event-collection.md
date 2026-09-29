---
id: WI-063
title: Restore governed incremental trade-event collection and coverage evidence
status: stabilizing
type: defect
owner: owner
decision_refs: DEC-009, DEC-010, DEC-015, DEC-030, DEC-044, DEC-059, DEC-060, ADR-032
requirement_refs: DEC-009, DEC-010, DEC-059, DEC-060
milestone_ref: MS-008
delivery_refs: none
parent_work_item: none
depends_on: WI-062
discovered_from: WI-062
supersedes: none
rollback_of: none
execution_scope: repository implementation and production release
production_effects: guarded independent scale-to-zero Job activation after verified implementation
architecture_impact: ADR-032 restores a bounded independent logical producer while reusing the managed runtime image repositories and warehouse
data_impact: future append-only trade observations revisions quality evidence and per-partition coverage watermarks
security_impact: preserve account aliases only in public responses and existing confidential ledger controls
cost_impact: bounded KIS order-history calls must be measured before activation
user_visible_impact: yes
real_use_acceptance: required
real_use_evidence_refs: PR #137 and #138, protected deploy runs 35900350370 and 36595665194, immediate executions and direct Codex OAuth MCP replay recorded below
stabilization_window: immediate post-cutover scheduler execution plus bounded recurring-run and owner acceptance review
stabilization_exit_refs: immutable release evidence, four scheduler states, successful overseas execution, direct MCP positive/partial/error outputs and owner acceptance
rollback_plan: pause both new schedulers and resume only the preserved legacy schedulers through the protected release rollback path; never delete ledger observations
---

# WI-063 — Restore governed incremental trade-event collection and coverage evidence

## Problem and evidence

The 2026-09-23 real-use investigation found 282 governed current trade events through 2026-08-25 and eleven
`pipeline.trade-cash-backfill-v2` watermarks whose latest value is 2026-08-28. The recurring
`pipeline.owned-portfolio-core-v2` has current successful runs, but its implementation collects balances, prices and
FX rather than order history and does not advance a trade source coverage watermark. Its catalog nevertheless names
`dataset.trade-event` as an output. A September empty result therefore cannot prove that no trades occurred.

## Classification and contract

- Classification: defect and architecture correction discovered from actual MCP use.
- Contract: approved trade-event facts remain append-only and source-derived; no trade may be inferred from holdings.
- Immediate containment: WI-062 exposes `collection_watermark_before_query_end` instead of false empty-window pass.
- Approved correction: DEC-060/ADR-032 select an independent scale-to-zero incremental producer. It reuses the
  existing source adapter, normalization repository, image and warehouse while isolating its run, watermark and
  failure state from the owned-portfolio core pipeline.

## Scope

- Include: choose and implement one bounded incremental producer, per-source/account coverage watermark, quality rule,
  immediate fixture/replay and direct MCP verification.
- Include: reconcile the core pipeline catalog output with the chosen producer boundary without silently weakening it.
- Exclude: fabricating trades from position deltas, arbitrary unbounded backfill, live ordering or coupling unrelated
  portfolio reads to trade collection health.

## Acceptance criteria

- [x] The reviewed producer collects every approved current account/market partition within a bounded call budget.
- [x] A successful partition advances an explicit contiguous source coverage watermark only after quality/publish.
- [x] Empty-window trade-ledger pass is possible only when every requested partition covers the query end date.
- [x] Source failure degrades trade features without blocking portfolio overview, market data or verified partials.
- [x] Immediate replay and actual Codex OAuth MCP positive/partial/error scenarios pass after guarded deployment.

## Change impact

- Architecture: independent incremental producer preferred; no request-scoped long collection.
- Data/schema/backup: append-only existing ledger is preserved; any new control evidence needs catalog/migration/backup review.
- Security/privacy: no raw account number or provider payload in MCP or test evidence.
- MCP/API compatibility: retain WI-062 query status and coverage metadata.
- Deployment/rollback: protected pipeline/Remote release with prior revisions retained.
- Cost/SLO: measure exact KIS calls and latency before approval; no standing worker.

## Plan

1. Compare the existing daily domestic/overseas jobs and backfill runtime against an independent incremental design.
2. Approve the producer, watermark grain, quality rule, call budget and failure isolation contract.
3. Implement fixture/replay first, then guarded production release.
4. Verify direct MCP current-window behavior without waiting for a future trade or scheduler slot.

## Sub-items

- `WI-063-S01` (`stabilizing`) — correct the production cutover after stabilization showed that the legacy overseas
  transaction scheduler and the new incremental overseas scheduler both ran at 07:35 KST. The legacy Job refreshed
  a separate token cache while the incremental Job was using its prior token, producing four consecutive
  `http_status=403` failures. Preserve both legacy Jobs for rollback, pause both legacy trade schedulers, keep only the
  new domestic/overseas schedules active, and verify an immediate overseas execution plus recurring evidence.

## Stabilization plan

- Observation: immediate controlled replay plus one guarded current-date production run.
- Signals: per-partition watermark, source calls, rows published, quality evidence and unaffected portfolio reads.
- Rollback: restore prior producer/Remote revisions; never delete ledger events.
- Exit: owner accepts direct current-window MCP evidence and independent feature behavior.

## Real-use acceptance

- Required through the owner-authenticated Codex OAuth MCP connection.
- Must demonstrate a covered empty window, a populated window and an explicit source/coverage failure.

## Evidence

- Initial evidence is the read-only MotherDuck aggregate recorded by WI-062.
- PR #137 merged commit `684e081`; protected deploy run `35900350370` passed and deployed immutable digest
  `sha256:fd9d87b4...` to both incremental Jobs and Remote.
- Immediate controlled replay succeeded: domestic execution `...-m8qcg` produced 13 successful partition runs and
  overseas execution `...-fq9bz` produced four; all 34 quality checks passed. Direct Codex OAuth MCP calls proved a
  covered empty ISA window, a populated RIA window, explicit IRP/global partial coverage, owner-debug invalid-date
  error handling, an unaffected portfolio overview, and 17/17 successful pipeline-run rows.
- Stabilization on 2026-09-30 found domestic recurring executions successful but all four recurring overseas
  executions failed. Cloud Logging correlated the 07:35 legacy `kis-portfolio-overseas-transaction-history` token
  refresh with the new Job's cache miss and KIS token issuance 403. Both legacy trade schedulers were paused as
  recoverable containment; WI-063-S01 owns the durable cutover correction and replay.
- After containment, immediate overseas execution `kis-portfolio-trade-incremental-overseas-bj9sn` succeeded. Its
  four source requests reused the same cached token and returned HTTP 200 without a refresh or 403. The scheduler
  cutover regression tests and the full repository gate passed (`793 passed`, one pre-existing Authlib warning).
- PR #138 merged as `3903f16275892a6e2eed50998aaa247abac7c34a`; protected release run `36595665194`
  deployed both incremental Jobs from digest
  `sha256:d200e39a5cea2d192c551a19ff77d0bcba579efde00bc05125ec9a303b3757dd`. Post-release state has
  only `kis-portfolio-trade-incremental-domestic-1610` and `kis-portfolio-trade-incremental-overseas-0735`
  enabled; both legacy trade schedulers are paused. Scheduler-triggered overseas execution
  `kis-portfolio-trade-incremental-overseas-vnmvk` succeeded in 22.3 seconds from the released image.
- Direct Codex OAuth MCP replay after release proved: a covered brokerage empty window returns pass with coverage
  through 2026-09-29; a global 2026-09-30 query returns an explicit `collection_coverage_gap`; an inverted date range
  returns diagnosable `invalid_request`; and the unaffected portfolio overview remains available/pass with 32 rows.
  `get-pipeline-run` resolved the exact producer and returned 18 runs. The latest overseas run is successful, while
  aggregate quality remains `failed` because the one-day evidence window correctly retains the pre-cutover failed
  run; this historical failure is not suppressed or rewritten.

## Closeout

- Result: implementation, guarded production cutover and immediate real-use acceptance scenarios are complete;
  WI-063 is stabilizing pending bounded recurring evidence and owner acceptance.
- Remaining risk: the one-day pipeline evidence window retains the pre-cutover overseas failure until it ages out;
  future source failures must remain isolated and visible. Historical duplicate current rows are a separate issue.
- Follow-up Work Item: proposed WI-064 owns source-grounded current-ledger business-key deduplication without
  changing WI-063 acceptance or erasing append-only observations.
