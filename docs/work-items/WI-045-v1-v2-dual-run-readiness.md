---
id: WI-045
title: Complete V1 V2 dual-run recovery and cost readiness
status: proposed
type: architecture
owner: owner
decision_refs: ADR-020, ADR-021, ADR-023
requirement_refs: DEC-033..041, DEC-045
milestone_ref: MS-003
delivery_refs: V2-W0701, V2-W0702, V2-W0703, V2-W0706
parent_work_item: none
depends_on: WI-035, WI-044
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

- Pending.

## Closeout

- Result: proposed.
- Remaining risk: cutover requires explicit approval.
- Follow-up Work Item: WI-046.
