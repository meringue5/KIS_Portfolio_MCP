---
id: WI-042
title: Implement the stateless Remote MCP V2 read surface
status: proposed
type: architecture
owner: owner
decision_refs: ADR-020, ADR-021
requirement_refs: DEC-029, DEC-033, DEC-034, DEC-038
milestone_ref: MS-003
delivery_refs: V2-W0601, V2-W0602, V2-W0603
parent_work_item: none
depends_on: WI-030, WI-040, WI-041
architecture_impact: implements approved stateless transport and 18-tool public boundary
data_impact: governed query DTOs only
security_impact: mcp:read scope and bearer validation
cost_impact: scale-to-zero service with bounded requests
---

# WI-042 — Implement the stateless Remote MCP V2 read surface

## Problem and evidence

The V1 35-tool adapter remains public; the approved outcome-oriented V2 catalog and stateless transport are not active.

## Classification and contract

- `architecture` implementation of the approved Remote MCP V2 read boundary.

## Scope

- Include DTO/schema envelope, thin handlers, stateless HTTP, limits, host/origin and `mcp:read` authorization.
- Exclude collect/journal commands and production cutover.

## Acceptance criteria

- [ ] approved tool budget, scopes, replicas and compatibility tests pass.
- [ ] handlers delegate to application queries and preserve quality/lineage.
- [ ] remote, security, cost and full gates pass.

## Change impact

- Parallel V2 endpoint/revision with V1 rollback retained.

## Plan

1. Freeze DTOs/scope matrix. 2. Implement transport/handlers. 3. Run replica and negative authorization tests.

## Sub-items

- `none`.

## Evidence

- Pending.

## Closeout

- Result: proposed.
- Remaining risk: real client behavior belongs to WI-044.
- Follow-up Work Item: WI-043.
