---
id: WI-049
title: Approve and execute bounded V1 runtime resource cleanup
status: proposed
type: maintenance
owner: owner
decision_refs: ADR-020, ADR-021
requirement_refs: DEC-034, DEC-041, DEC-047
milestone_ref: MS-004
delivery_refs: V2-W0804
parent_work_item: none
depends_on: WI-047
architecture_impact: removes superseded deployment resources
data_impact: no data deletion
security_impact: obsolete identities/secrets require scoped review
cost_impact: removes residual image Job and Scheduler cost
---

# WI-049 — Approve and execute bounded V1 runtime resource cleanup

## Problem and evidence

Past images, Jobs and Schedulers should not remain indefinitely after rollback confidence, but cleanup is destructive.

## Classification and contract

- `maintenance` with target-by-target destructive approval and recovery evidence.

## Scope

- Include exact resource manifest, dependency checks, retained rollback artifacts and bounded removal.
- Exclude databases, backups and active V2 resources.

## Acceptance criteria

- [ ] owner approves exact targets and recovery artifacts.
- [ ] active/rollback/V2 resources cannot match cleanup.
- [ ] post-cleanup smoke and cost evidence pass.

## Change impact

- Destructive but recoverable deployment cleanup.

## Plan

1. Generate targets. 2. Approve and preserve rollback. 3. Remove and smoke.

## Sub-items

- `none`; each resource family may become a stable sub-item.

## Evidence

- Pending.

## Closeout

- Result: proposed.
- Remaining risk: deletion authorization is intentionally deferred.
- Follow-up Work Item: WI-051.
