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

- `WI-042-S01` — audit the existing 35-tool surface, OAuth scope enforcement, approved V2 18-tool mapping and
  WI-040 thin read-adapter boundary without implementation (`closed`).

## Evidence

- `docs/operations/wi-042-s01-remote-read-surface-audit-2026-09.md`: exact 35-to-18 migration grouping, current
  endpoint-wide read scope gap, parallel V2 builder, request actor, official stateless transport and implementation
  gate inputs.
- Current surface audit passed with 35 tools and disabled order stubs; focused OAuth/MCP/package baseline passed
  44 tests and full gate passed 443 tests with one existing Authlib deprecation warning.
- S01 changed no DTO/handler, public catalog, OAuth grant, transport, deployment, live client or production state.

## Closeout

- Result: parent proposed; S01 research closed. This is the last planned MS-003 pre-research checkpoint before MS-002
  close; subsequent implementation remains dependency-gated.
- Remaining risk: real client behavior belongs to WI-044.
- Follow-up Work Item: WI-043.
