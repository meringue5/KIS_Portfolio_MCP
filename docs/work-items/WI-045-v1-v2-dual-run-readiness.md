---
id: WI-045
title: Complete V1 V2 dual-run recovery and cost readiness
status: in_progress
type: architecture
owner: owner
decision_refs: ADR-020, ADR-021, ADR-023
requirement_refs: DEC-033..041, DEC-045
milestone_ref: MS-003
delivery_refs: V2-W0701, V2-W0702, V2-W0703, V2-W0706
parent_work_item: none
depends_on: WI-035, WI-044
execution_scope: isolated
production_effects: none
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
- Current phase is isolated contract, fixture and local verification only. It does not claim elapsed production
  dual-run, live restore or current billing evidence.

## Scope

- Include daily comparison, ten trading days, gap triage, restore rehearsal, RPO/RTO and cost review.
- Exclude V1 deletion and connector/Scheduler cutover.

## Acceptance criteria

- [ ] unexplained differences are zero and partial gaps have quality reasons.
- [ ] ten-day SLO, restore RPO/RTO and cost envelope pass.
- [ ] rollback manifest is tested.

## Change impact

- Observation-only dual-run; both data planes preserved.

## Plan

1. Freeze report. 2. Observe ten sessions and triage. 3. Restore and cost rehearsal.

## Sub-items

- `none`.

## Evidence

- 2026-09-11 activation: WI-035 and WI-044 are verified, MS-003 permits WI-045 as the next reviewed continuous-overlap
  item and no other implementation Work Item is in progress. This phase is restricted to deterministic comparison,
  recovery, cost and rollback contracts with synthetic fixtures and local verification.
- Activation does not authorize production inventory capture, live database reads or writes, source activation,
  IAM/Secret changes, Cloud Run/Scheduler changes, public MCP activation, cleanup, traffic cutover or V1 retirement.

## Closeout

- Result: in progress under the isolated overlap gate.
- Remaining risk: cutover requires explicit approval.
- Follow-up Work Item: WI-046.
