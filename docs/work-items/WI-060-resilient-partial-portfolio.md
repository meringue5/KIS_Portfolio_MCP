---
id: WI-060
title: Isolate portfolio capability failures and provide accurate partial results
status: in_progress
type: architecture
owner: owner
decision_refs: DEC-055, DEC-057, ADR-021, ADR-023, ADR-024, ADR-028, ADR-029
requirement_refs: DEC-029, DEC-031, DEC-032, DEC-038, DEC-055, DEC-057
milestone_ref: MS-007
delivery_refs: none
parent_work_item: none
depends_on: none
discovered_from: WI-059, WI-055, WI-058
supersedes: none
rollback_of: none
execution_scope: isolated
production_effects: none
architecture_impact: yes; separate capability quality, read-model and report boundaries without changing the V2 trust boundary
data_impact: proposed versioned FX-source and partial-result contracts; no live source or physical DB mutation in this phase
security_impact: retain owner-only destination, masked accounts, no payload or secret logging
cost_impact: assess bounded second FX source within the existing monthly ceiling before activation
stabilization_window: none
stabilization_exit_refs: none
rollback_plan: none
---

# WI-060 — Resilient partial portfolio usability

## Problem and evidence

The owner rejected a system where a missing prior same-slot state or delayed USD/KRW rate makes all useful
current holdings disappear from the Telegram report, and where Claude's MCP reads repeatedly show unusable or
misleading quality. On 2026-09-17 the 10:00 owner report was unavailable because the 9/16 10:00 state was absent.
Separately, the 9/17 10:16 stored KRX/KRW position subset contained 17 pass-quality instruments and remained
queryable without FX. This subset is not a complete total asset value and includes KRX-listed overseas-themed ETFs.

Code audit found that `get-portfolio-overview` includes non-pass Gold rows in its numeric sum, while its outer
envelope reports `pass` whenever any rows exist. `get-performance-history` tests for the literal `passed`, though
Gold writes `pass`; its fixture repeats the wrong literal. These are independently reproducible read-model defects.

## Classification and contract

- Architecture/change: current DEC-055 explicitly suppresses all amounts and chart if either state is incomplete.
  The owner's feedback requests a different product behavior, not a silent exception to that decision.
- Defect: remote read-model quality aggregation and performance-history status literal disagree with persisted Gold.
- Data-source change: `dataset.fx-rate-daily` currently names only `source.kis-open-api`. A second FX provider needs
  source rights, rate-basis/time equivalence, new contract versions and architecture review before activation.
- Detailed proposal and failure matrix: `docs/design/resilient-capability-degradation-review.md`.

## Scope and release unit

- Isolated phase: map producer-to-consumer dependencies, specify independently useful capability cells, freeze
  deterministic failure fixtures and correct clear false-green/false-degraded read-model defects under review.
- Approved isolated implementation: expose verified current KRW holdings and labeled partial reports independently
  of prior comparison and USD conversion; evaluate a secondary FX source without mixing unlike rate definitions.
- Exclude: fabricated total assets, stale FX silently treated as current, manual replay of old Telegram sends,
  provider signup/credential provisioning, production collection, public MCP change or deploy in this phase.
- Ship the WI-060 user-visible correction as **one protected release candidate** after its contracts, fixtures,
  no-send production preflight and CI pass. Small reviewed commits and PR updates are allowed; do not activate a
  half-fixed MCP or Telegram surface in separate production deployments. This is a WI-060 boundary, not a promise
  to finish every unrelated historical TODO before release.
- A secondary FX provider is part of the same candidate only if source rights, rate semantics, credentials,
  cost and activation contracts are approved. If those prerequisites are unavailable, do not silently claim that
  the single-source dependency was fixed; report the remaining gap and seek a release-scope decision before merge.

## Acceptance criteria

- [x] A missing prior slot disables only comparison and contribution, not a verified current-only capability.
- [x] Stale FX disables USD-to-KRW conversion and complete KRW total, not native values or verified KRX/KRW rows.
- [x] Missing one source or optional macro/ETF look-through never yields a false `pass` and never erases unrelated
  verified components; every numeric subtotal is labeled by coverage, source time and valuation basis.
- [x] MCP and Telegram fixtures reproduce user-visible complete, partial and unavailable cases without a clock wait.
- [ ] Real Claude/MCP and owner-visible Telegram review accepts the presentation before production closeout.
- [ ] Any secondary FX source has approved rights, cost, source-date/rate-type mapping and deterministic conflict
  handling; no production calls or credentials are added merely to pass tests.

## Change impact

- Architecture: capability-oriented quality composition instead of one all-or-nothing report gate.
- Data/schema/backup: no mutation in isolated phase; later source/dataset revisions may require additive lineage.
- Security/privacy: no change to OAuth or Telegram owner-only destination; partial output remains confidential.
- MCP/API compatibility: prefer additive fields and explicit quality status; major version if existing field meaning
  must change. Preserve the 18-tool catalog unless separately approved.
- Deployment/rollback: the independent MS-007 gate depends on already-closed MS-005, not WI-059/MS-006
  stabilization. Any later release still needs approved product/data contracts and protected immutable V2 delivery.
- Cost/SLO: second source must fit the current bounded-call and monthly-cost contract.

## Plan

1. Record the usability feedback, trace the dependency graph and identify false-green/false-negative behavior.
2. Define field-level quality/coverage and a presentation matrix in a proposed DEC/ADR for owner review.
3. Freeze executable fixtures for missing prior, stale FX, missing account, degraded row, optional context gaps
   and complete states. Implement isolated read-model and report slices; preserve exact totals as fail-closed.
4. Review source rights, rate basis and operations for secondary FX; activate only after contract approval.
5. Run quick/full gates, synthetic fault injection, no-send report previews and read-only production preflight.
   Review the exact single-release diff and rollback image. The current workflow has no narrow target combining
   Remote MCP and the owner-report Job; add and test such a target instead of deploying unrelated services with
   `all` or treating two independent target runs as an atomic release.
6. Merge once and deploy one immutable image through the protected production workflow. Verify Git SHA and image
   labels across both Remote MCP and the scheduled report job before enabling the changed consumer behavior.
7. Verify real Claude/MCP output and an owner-visible Telegram report with source/coverage labels and receipt;
   retain stabilization evidence before closeout. A future scheduler slot is not the sole acceptance test.

## Sub-items

- `none`. Independent future provider activation or physical schema work should receive a separate Work Item.

## Stabilization plan

- Isolated phase only. Before production, define bounded live and owner-visible review, rollback and exit evidence.
  Do not create a new dependency on the unavailable old report's owner-acceptance outcome.

## Evidence

- Architecture contract and MCP surface checks pass, yet neither checks degraded-result usability.
- Read-only MotherDuck inspection: 9/17 10:16 KRX/KRW 17 pass positions; 9/16 16:01 and 9/17 10:16 quantities
  are unchanged for those lines. These are different slots, not a canonical same-time daily return.
- WI-059-S01 readiness: `missing_prior_state` for 9/17 10:00 and `fx_input_stale` for 9/16 16:00.
- First isolated read-model slice: red tests reproduced a false `pass` overview with a degraded row and a
  false-degraded performance history using the actual Gold literal `pass`. The overview now suppresses a complete
  total when row/FX/account coverage is deficient, retains an explicitly named verified KRX/KRW position subtotal,
  and removes invalid converted amounts. The history literal is corrected and degraded sums are null.
  Focused warehouse tests: 34 passed; digest/read-surface adjacency: 33 passed. A read-only production DB
  preflight at 2026-09-17 14:32 showed `partial`, complete total suppressed, 22 verified KRX/KRW position lines,
  and `fx_input_stale` as the missing reason. Full shared gate: 741 passed, one pre-existing Authlib
  deprecation warning. No public service or Telegram deployment occurred.
- DEC-057/ADR-029 approve capability isolation. Shared quality composition, Telegram presentation `2.3.0`,
  data-quality/pipeline-run false-green correction and the one-image `wi060` protected target have focused
  deterministic coverage. `scripts/check_resilient_portfolio_cases.py` passes five immediate no-network/no-send
  scenarios. Korea Eximbank source, collection, dataset and pipeline contracts remain proposed only; no credential,
  provider call or production valuation fallback exists yet.
- Read-only MotherDuck previews with branch code require no Scheduler wait: 2026-09-18 `kr-1000` and `kr-1600`
  are both `ready_partial` with only `prior_fx_input_stale`; 2026-09-21 both slots are `ready`/`pass`. No run row,
  source call or Telegram claim was created. The standalone fault matrix passed, the protected release command
  dry-run reused one immutable image for Remote MCP and all three fixed-slot Jobs, and the full repository gate
  passed with 749 collected tests and one pre-existing Authlib deprecation warning.

## Closeout

- Result: open.
- Remaining risk: design and implementation not yet accepted or production-active.
- Follow-up Work Item: none yet.
