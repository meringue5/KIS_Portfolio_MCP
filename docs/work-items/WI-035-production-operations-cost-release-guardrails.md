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

- `WI-035-S01` — research production inventory, cost and rollback cleanup evidence (`closed`).

## Pre-research checkpoint

`WI-035-S01` is a research-only sub-item. The parent `WI-035` remains `proposed`, and this checkpoint does not open
the MS-003 formal start gate.

| Checkpoint | State | Evidence |
| --- | --- | --- |
| research start and boundary | complete | 2026-08-30; this Work Item and registry entry |
| repository operations/cost/release audit | complete | no executable inventory, cost evaluator, release manifest or cleanup planner found |
| live read-only resource metadata audit | complete | 2 services, 12 jobs, 6 schedulers and two image repositories reconciled |
| implementation inputs and unknowns | complete | `docs/operations/wi-035-pre-research-2026-08.md` |

Allowed scope is read-only repository and live metadata inspection, current cost/budget observability assessment,
active/rollback digest preservation inputs, and implementation-gap identification. It excludes GCP resource mutation,
database mutation, deploy/cleanup apply, code implementation and approved contract changes.

## Evidence

- `WI-035-S01` start checkpoint: 2026-08-30.
- `docs/operations/wi-035-pre-research-2026-08.md`: closed read-only evidence and implementation inputs.

## Closeout

- Result: parent proposed; `WI-035-S01` research closed without opening the MS-003 formal gate.
- Remaining risk: current billing export granularity may remain limited.
- Follow-up Work Item: WI-045.
