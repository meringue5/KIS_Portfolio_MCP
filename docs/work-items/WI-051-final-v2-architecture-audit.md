---
id: WI-051
title: Remove obsolete shims and complete the final V2 architecture audit
status: proposed
type: architecture
owner: owner
decision_refs: ADR-021, ADR-022, ADR-023
requirement_refs: DEC-033..041, DEC-047
milestone_ref: MS-004
delivery_refs: V2-W0806
parent_work_item: none
depends_on: WI-047, WI-048, WI-049, WI-050
architecture_impact: establishes the implemented final V2 boundary
data_impact: verifies warehouse contract and drift; no silent deletion
security_impact: verifies trust boundaries and obsolete privileges
cost_impact: verifies final steady-state forecast
---

# WI-051 — Remove obsolete shims and complete the final V2 architecture audit

## Problem and evidence

After retirement work, obsolete code/shims and cross-document drift may still contradict the implemented V2 system.

## Classification and contract

- `architecture` final implementation audit before documentation canonicalization.

## Scope

- Include obsolete package/shim removal and architecture, MCP, warehouse, security, release and cost audit.
- Exclude rewriting historical evidence or deleting data without approval.

## Acceptance criteria

- [ ] no obsolete runtime path or unauthorized dependency remains.
- [ ] architecture, warehouse, MCP, security, release and full gates pass with live evidence.
- [ ] residual exceptions have owners and expiry.

## Change impact

- Final code boundary cleanup with prior release as rollback.

## Plan

1. Inventory residuals. 2. Remove bounded shims. 3. Run all audits and live smokes.

## Sub-items

- `none`.

## Evidence

- Pending.

## Closeout

- Result: proposed.
- Remaining risk: documentation truth cutover belongs to WI-032.
- Follow-up Work Item: WI-032.
