---
id: WI-045
title: Complete V1 V2 dual-run recovery and cost readiness
status: closed
type: architecture
owner: owner
decision_refs: ADR-020, ADR-021, ADR-023
requirement_refs: DEC-033..041, DEC-045
milestone_ref: MS-003
delivery_refs: V2-W0701, V2-W0702, V2-W0703, V2-W0706
parent_work_item: none
depends_on: WI-035, WI-044
execution_scope: production
production_effects: readiness_evidence_only
architecture_impact: cutover readiness evidence without switching SSOT
data_impact: comparison reports only; both writers preserved
security_impact: confidential reports remain private and redacted
cost_impact: verifies actual and forecast against approved limits
---

# WI-045 — Complete V1 V2 dual-run recovery and cost readiness

## Problem and evidence

V2 cannot become SSOT until monetary, quantity, freshness, signal, recovery and cost behavior is observed beside V1.

## Classification and contract

- `architecture` readiness gate; no traffic switch in this WI.
- Current phase is production readiness evidence after MS-002 closure. It may capture read-only inventory,
  reconciliation and cost evidence and perform bounded backup/restore rehearsal, but cannot switch traffic.

## Scope

- Include daily comparison, ten trading days, gap triage, restore rehearsal, RPO/RTO and cost review.
- Exclude V1 deletion and connector/Scheduler cutover.

## Acceptance criteria

- [x] unexplained differences are zero and partial gaps have quality reasons.
- [x] ten-day SLO, restore RPO/RTO and cost envelope pass.
- [x] isolated fixture proves zero unexplained differences, explained partial gaps and all fail-closed comparison paths.
- [x] isolated fixture proves the ten-session schedule/RPO/RTO/cost contract without claiming elapsed production SLO.
- [x] rollback manifest contract is tested against immutable target-specific digests and restore evidence.

## Change impact

- Observation-only dual-run; both data planes preserved.

## Plan

1. Freeze report. 2. Observe ten sessions and triage. 3. Restore and cost rehearsal.

## Sub-items

- `WI-045-S01` — make V2 backup/restore fail closed against the exact checksum-verified production migration prefix
  (`closed`).
  - [x] new exports record a version-aware manifest without weakening legacy full-manifest restore.
  - [x] missing or unexpected managed tables fail before a backup can claim completeness.
  - [x] production 0013 private upload, exact-hash download and fresh restore pass.

## Evidence

- 2026-09-11 production activation: MS-002 closed by explicit owner acceptance in PR #76/master `65bda84`, opening
  the MS-003 production gate. The owner instructed the project to begin transition without further MS-002
  observation. No other implementation Work Item is in progress.
- This phase still excludes connector refresh, Scheduler switch, public MCP traffic, V1 pause/retirement and cleanup;
  those remain WI-046 and must fail closed if current readiness evidence is incomplete.
- 2026-09-11 activation: WI-035 and WI-044 are verified, MS-003 permits WI-045 as the next reviewed continuous-overlap
  item and no other implementation Work Item is in progress. This phase is restricted to deterministic comparison,
  recovery, cost and rollback contracts with synthetic fixtures and local verification.
- Activation does not authorize production inventory capture, live database reads or writes, source activation,
  IAM/Secret changes, Cloud Run/Scheduler changes, public MCP activation, cleanup, traffic cutover or V1 retirement.
- `kis-portfolio.dual-run-evidence/v1` and the review-only CLI evaluate the exact total asset, holding quantity, order,
  price, signal and freshness set; partial rows require a quality reason and explicit missing coverage, while any
  out-of-tolerance value fails closed.
- The combined gate requires at least ten unique dated sessions, all required runs successful, zero duplicate
  deliveries, RPO at most 24 hours, RTO at most 4 hours, normal-month actual/forecast at most KRW 7,500 and a valid
  WI-035 immutable release/rollback manifest. Its output always says `production_cutover_allowed=false`.
- Synthetic evidence: ten sessions, zero unexplained differences, one explained partial gap, 20/20 schedule runs,
  zero duplicate deliveries, RPO 720 minutes, RTO 45 minutes and KRW 6,200 forecast. The fixture-only result is
  intentionally `blocked` solely because it cannot satisfy the production dual-run gate.
- Verification: focused/recovery-adjacent `29 passed`; quick passed; full `607 passed` with all Project OS, data
  governance, architecture, warehouse and MCP gates. See
  `docs/operations/wi-045-isolated-readiness-2026-09.md`.
- Production observation: ten exact 14:30 trading-day sessions from 2026-08-31 through 2026-09-11; 220/220
  holding-quantity rows and 170/170 adjusted KRX OHLCV rows matched exactly, orders were 0/0, freshness remained
  inside five minutes, all 30 required owned-core schedule slots succeeded and duplicate terminal sends were zero.
- The V1 global-total and legacy-signal mirror were not scheduled at matching slots. They remain 20 explicitly
  explained partial rows across ten sessions rather than false matches; owner acceptance of the observed V2
  total-asset/Telegram behavior carries those gaps into MS-003 stabilization.
- Recovery: manifest v3 exported all 58 tables belonging to checksum-verified migration prefix 0013, uploaded 59
  content-addressed objects to the private recovery bucket, downloaded by exact index hash and restored every table
  plus version-appropriate views to a fresh memory DB. Conservative RPO/RTO evidence is 30/1 minutes.
- Cost: current-month all-project Billing evidence was KRW 434 actual and KRW 119 forecast after savings; the
  fail-closed evaluator used the larger value and returned `normal` below the KRW 7,500 target.
- Production readiness evaluator: `pass`, ten trading days, zero unexplained differences, 20 explained partials and
  no blockers. The output still says `production_cutover_allowed=false`; only WI-046 owns the protected cutover.
- Full operational evidence: `docs/operations/wi-045-production-readiness-2026-09.md` and the three versioned JSON
  artifacts under `governance/project/evidence/wi045/`.

## Closeout

- Result: closed after isolated verification and production readiness evidence; WI-046 may start.
- Remaining risk: the matching-slot V1 global-total and legacy-signal mirrors were absent, migration 0014–0017 remains
  unapplied, and actual connector/public-client smoke has not run. These stay explicit in WI-046 and MS-003
  stabilization; no V1 cleanup or retirement is authorized here.
- Follow-up Work Item: WI-046 production cutover through the protected release path.
