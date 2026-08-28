---
id: WI-047
title: Retire local setup and the V1 public MCP surface
status: proposed
type: maintenance
owner: owner
decision_refs: ADR-020, ADR-021
requirement_refs: DEC-034, DEC-047
milestone_ref: MS-004
delivery_refs: V2-W0801, V2-W0802
parent_work_item: none
depends_on: WI-046
architecture_impact: removes superseded public adapters after cutover
data_impact: none
security_impact: removes obsolete public capability including order stubs
cost_impact: may reduce deployment and support surface
---

# WI-047 — Retire local setup and the V1 public MCP surface

## Problem and evidence

After V2 cutover, local product setup and the V1 tool catalog would remain a conflicting public surface.

## Classification and contract

- `maintenance` retirement under the approved Remote-only decision.

## Scope

- Include setup/connector removal, V1 catalog and disabled order stub retirement, compatibility diagnostics.
- Exclude V1 data or runtime resource deletion.

## Acceptance criteria

- [ ] fresh setup registers Remote V2 only and V1 calls receive explicit migration guidance.
- [ ] public tool/security/full gates pass.

## Change impact

- Public compatibility change after completed cutover; rollback retains prior image/config.

## Plan

1. Verify zero supported use. 2. Remove public registration. 3. Test migration failures and rollback.

## Sub-items

- `none`.

## Evidence

- Pending.

## Closeout

- Result: proposed.
- Remaining risk: hidden local users must be checked.
- Follow-up Work Item: WI-049.
