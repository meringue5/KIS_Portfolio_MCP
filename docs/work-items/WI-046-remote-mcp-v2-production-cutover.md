---
id: WI-046
title: Cut production connectors and schedules over to Remote MCP V2
status: in_progress
type: architecture
owner: owner
decision_refs: ADR-020, ADR-021
requirement_refs: DEC-030, DEC-034, DEC-045
milestone_ref: MS-003
delivery_refs: V2-W0704, V2-W0705, V2-W0707
parent_work_item: none
depends_on: WI-045
execution_scope: production
production_effects: bounded_remote_connector_and_scheduler_cutover
architecture_impact: changes the production MCP and Scheduler SSOT
data_impact: V2 writers become primary while V1 remains paused for rollback
security_impact: OAuth scopes and production identities switch to V2
cost_impact: actual production configuration remains within approved envelope
---

# WI-046 — Cut production connectors and schedules over to Remote MCP V2

## Problem and evidence

Passing dual-run evidence must be converted into one bounded, reversible production cutover.

## Classification and contract

- `architecture` cutover requiring explicit owner approval at the execution gate.
- The owner approved starting the transition after accepting the 2026-09-11 14:30 observation and the immutable
  WI-045 manifest. Production mutations must run from tested `master` through the protected GitHub Actions path.
- Preserve the pre-cutover Remote MCP revision and V1 schedule definitions for at least a seven-day rollback window.
  Do not delete V1 services, jobs, schedules, data, secrets or revisions in this Work Item.

## Scope

- Include connector refresh, V2 Scheduler activation, V1 pause, approval record and rollback window.
- Exclude V1 deletion and final retirement.

## Acceptance criteria

- [ ] owner approves immutable manifest and rollback window.
- [ ] Remote MCP/iPhone and scheduled runs pass production smoke.
- [ ] rollback to V1 revision and schedules is rehearsed.

## Change impact

- Production SSOT switch; preservation-first and reversible.

## Plan

1. Approve manifest. 2. Switch connector and schedules. 3. Smoke, observe and close rollback window.

## Sub-items

- `none`.

## Evidence

- 2026-09-11 activation: WI-045 closed on PR #77/master `6245238` with a passing ten-date readiness assessment,
  private exact-hash restore, current cost pass and target-specific immutable rollback digests. The owner explicitly
  instructed the project to stop further MS-002 observation and begin transition.
- Execution order remains fail closed: merge the protected release implementation, apply additive migrations,
  deploy/smoke inactive V2 targets, refresh production connectors, switch schedules, then observe. Any failed gate
  restores the recorded V1 revision/schedules while preserving V2 data.

## Closeout

- Result: in progress.
- Remaining risk: V1 retirement remains MS-004.
- Follow-up Work Item: WI-047.
