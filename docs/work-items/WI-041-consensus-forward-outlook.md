---
id: WI-041
title: Implement point-in-time consensus and forward outlook analysis
status: proposed
type: change
owner: owner
decision_refs: ADR-021, ADR-023
requirement_refs: DEC-021, DEC-022, DEC-032, DEC-041, DEC-043
milestone_ref: MS-003
delivery_refs: V2-W0506
parent_work_item: none
depends_on: WI-037
architecture_impact: possible provider activation gate; no provider chosen by this baseline
data_impact: point-in-time consensus snapshots and outlook metrics
security_impact: licensed content rights and redistribution controls
cost_impact: provider cost must be separately approved
---

# WI-041 — Implement point-in-time consensus and forward outlook analysis

## Problem and evidence

Actual facts are approved, but consensus miss, guidance cut and NTM revision require a rights-cleared provider with
historical point-in-time coverage.

## Classification and contract

- `change` with a mandatory legal, coverage and cost activation gate.

## Scope

- Include pre-release consensus, analyst count/dispersion, surprise, guidance and post-release revision.
- Exclude paid subscription or collection before explicit approval.

## Acceptance criteria

- [ ] provider rights, point-in-time history, coverage and monthly cost are approved.
- [ ] future leakage and scenario/consensus confusion tests pass.
- [ ] missing coverage is explicit and full gates pass.

## Change impact

- New provider activation may require ADR/cost approval; implementation remains scale-to-zero.

## Plan

1. Sample candidate providers. 2. Approve contract/cost. 3. Implement and replay event windows.

## Sub-items

- `none`; provider-specific sampling may be appended when selected.

## Evidence

- Pending.

## Closeout

- Result: proposed.
- Remaining risk: U.S. licensed history may exceed budget.
- Follow-up Work Item: WI-042.
