---
id: WI-043
title: Add governed collection and journal commands to Remote MCP V2
status: proposed
type: change
owner: owner
decision_refs: ADR-020, ADR-021, ADR-023
requirement_refs: DEC-029..031, DEC-038
milestone_ref: MS-003
delivery_refs: V2-W0604, V2-W0605
parent_work_item: none
depends_on: WI-024, WI-042
architecture_impact: implements approved collect and journal scopes without adding order authority
data_impact: managed run requests and append-only journal/thread revisions
security_impact: mcp:collect and mcp:journal.write least-privilege scopes
cost_impact: allowlisted fixed jobs only
---

# WI-043 — Add governed collection and journal commands to Remote MCP V2

## Problem and evidence

Remote V2 needs safe long-running collection triggers and owner-authorized journal writes without arbitrary Job
arguments, SQL or order capability.

## Classification and contract

- `change` implementing already approved command scopes.

## Scope

- Include run request/status polling, expected revision, actor, idempotency and authorization.
- Exclude order submission and unrestricted pipeline arguments.

## Acceptance criteria

- [ ] read tokens cannot collect/write; invalid jobs and stale revisions fail closed.
- [ ] long jobs return run IDs and journal changes append revisions.
- [ ] audit, concurrency and full gates pass.

## Change impact

- Existing Firestore/application ports and fixed Jobs only.

## Plan

1. Freeze command DTOs. 2. Implement application commands. 3. Verify scopes and idempotency.

## Sub-items

- `none`.

## Evidence

- Pending.

## Closeout

- Result: proposed.
- Remaining risk: actual client flows belong to WI-044.
- Follow-up Work Item: WI-044.
