---
id: WI-035
title: Complete production inventory cost and release cleanup guardrails
status: proposed
type: maintenance
owner: owner
decision_refs: ADR-020, ADR-021
requirement_refs: DEC-033..041
milestone_ref: MS-003
delivery_refs: V2-W0002, V2-W0003, V2-W0106
parent_work_item: none
depends_on: WI-012
architecture_impact: none; completes approved operational controls
data_impact: inventory metadata only
security_impact: resource names and IAM metadata only; no secret payload
cost_impact: enforces approved cost envelope and safe registry cleanup
---

# WI-035 — Complete production inventory cost and release cleanup guardrails

## Problem and evidence

Build-once deployment exists, but the complete resource snapshot, hard-envelope enforcement and rollback-safe Artifact
Registry cleanup remain separate delivery gaps.

## Classification and contract

- `maintenance` implementing approved cost and release controls without changing topology.
- Active and rollback digests must be protected before any cleanup applies.

## Scope

- Include machine-readable resource inventory, 7,500/35,000/42,500/50,000 won controls and cleanup dry-run/apply gate.
- Exclude service deletion, paid provider activation and architecture changes.

## Acceptance criteria

- [ ] inventory is reproducible without secrets; cost states and stop actions are deterministic.
- [ ] cleanup cannot select active or rollback digests and has restore evidence.
- [ ] release and full gates pass.

## Change impact

- Existing scale-to-zero release plane only; apply requires normal production approval.

## Plan

1. Inventory resources and costs. 2. Implement guardrails and cleanup simulation. 3. Verify rollback and apply gate.

## Sub-items

- `none`.

## Evidence

- Pending.

## Closeout

- Result: proposed.
- Remaining risk: current billing export granularity may remain limited.
- Follow-up Work Item: WI-045.
