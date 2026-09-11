---
id: WI-043
title: Add governed collection and journal commands to Remote MCP V2
status: verified
type: change
owner: owner
decision_refs: ADR-020, ADR-021, ADR-023
requirement_refs: DEC-029..031, DEC-038
milestone_ref: MS-003
delivery_refs: V2-W0604, V2-W0605
parent_work_item: none
depends_on: WI-024, WI-042
execution_scope: isolated
production_effects: none
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

- [x] read tokens cannot collect/write; invalid jobs and stale revisions fail closed.
- [x] long jobs return run IDs and journal changes append revisions.
- [x] audit, concurrency and full gates pass.

## Change impact

- Existing Firestore/application ports and fixed Jobs only.

## Plan

1. Freeze command DTOs. 2. Implement application commands. 3. Verify scopes and idempotency.

## Sub-items

- `none`.

## Evidence

- 2026-09-11 isolated activation: WI-024 is closed, WI-042 is verified, MS-003 remains in continuous isolated
  overlap and no other implementation Work Item is in progress. This phase is limited to typed command/application
  ports, fixed-job and append-only revision fixtures, authorization/idempotency/concurrency tests and local gates.
- Activation does not authorize OAuth grant expansion, actual Job execution, live DB writes, IAM/Secret or Cloud Run
  changes, public V2 catalog activation, deployment, traffic cutover or external messages.
- Implemented an inactive application command boundary for the exact three approved commands. `portfolio-refresh`
  maps only to the fixed owned-core pipeline/version and three fixed Job slots; arbitrary command, SQL, args, env and
  timeout input do not exist. A deterministic run ID is returned immediately for existing `get-pipeline-run` polling.
- Added `mcp:collect` and `mcp:journal.write` per-tool plus application authorization, exact resource validation and
  owner-subject projection without bearer retention. Existing grants and production auth configuration are unchanged.
- Firestore-compatible state claims guard idempotency and concurrent replay. Local atomic revision fixtures append
  journal and typed thread/lot/sell-allocation changes, retain actor/client/request audit evidence and fail stale
  expected revisions closed.
- Verification: focused and adjacent V2 tests `34 passed`; quick passed; full `590 passed` with all Project OS, data
  governance, architecture, warehouse and MCP gates. See
  `docs/operations/wi-043-isolated-verification-2026-09.md`.

## Closeout

- Result: verified under the MS-003 isolated-overlap gate; production effects remain none.
- Remaining risk: actual client flows belong to WI-044; production adapter, consent/grant and infrastructure wiring
  remain gated to WI-046.
- Follow-up Work Item: WI-044.
