---
id: WI-044
title: Verify Remote MCP V2 clients and publish the migration guide
status: proposed
type: maintenance
owner: owner
decision_refs: ADR-015, ADR-020, ADR-021
requirement_refs: DEC-029, DEC-034
milestone_ref: MS-003
delivery_refs: V2-W0606, V2-W0607
parent_work_item: none
depends_on: WI-042, WI-043
architecture_impact: none; verifies approved public boundary
data_impact: none beyond synthetic/read-only smoke
security_impact: real OAuth discovery and scope negative tests
cost_impact: bounded scale-to-zero smoke
---

# WI-044 — Verify Remote MCP V2 clients and publish the migration guide

## Problem and evidence

Transport tests do not prove Claude, ChatGPT and iPhone connector behavior or a safe V1 tool migration path.

## Classification and contract

- `maintenance` compatibility and documentation verification.

## Scope

- Include discovery/auth/tool calls for portfolio, market, catalog, pipeline and journal plus unsupported mapping.
- Exclude production connector cutover.

## Acceptance criteria

- [ ] actual supported clients pass new-conversation calls and scope tests.
- [ ] every V1 tool has a V2 mapping or explicit unsupported response.
- [ ] no local MCP product instruction remains in the migration guide.

## Change impact

- Parallel endpoint only; V1 remains rollback target.

## Plan

1. Build compatibility suite. 2. Run client smokes. 3. Publish migration and gap report.

## Sub-items

- `none`.

## Evidence

- Pending.

## Closeout

- Result: proposed.
- Remaining risk: client UI caching must be verified separately from logs.
- Follow-up Work Item: WI-045.
