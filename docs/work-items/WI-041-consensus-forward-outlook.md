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

- `WI-041-S01` (closed): research provider fields, rights, cost, point-in-time semantics and contract gaps without
  subscription, API call, DB write or implementation.
- `WI-041-S02` (closed): bounded KIS sampling completed at 6 calls; Alpha Vantage public demo failed closed because
  the endpoint requires an owner-issued free key. No raw payload was persisted and no provider was activated.
- `WI-041-S03` (proposed): sample current U.S. direct issuers with an owner-controlled Alpha Vantage free key and
  obtain explicit private-retention, backup, derived-use and internal LLM/MCP rights evidence.

## Evidence

- `docs/operations/wi-041-pre-research-2026-09.md`
- `docs/operations/wi-041-s02-bounded-sampling-2026-09.md`
- The research found no currently approvable canonical provider. Alpha Vantage is the first U.S. no-cost schema
  sampling candidate; KIS remains the domestic bounded sampling candidate. Both require rights, semantic and PIT gates.
- KIS live sampling confirmed endpoint connectivity but failed metric identity, analyst count/distribution and PIT
  requirements. Alpha Vantage requires owner credential issuance before a live schema sample.

## Closeout

- Result: proposed.
- Remaining risk: U.S. licensed history may exceed budget or prohibit retained PIT snapshots; the current dataset
  backup exclusion also prevents replay.
- Follow-up Work Item: WI-042.
