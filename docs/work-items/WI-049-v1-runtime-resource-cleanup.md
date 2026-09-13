---
id: WI-049
title: Approve and execute bounded V1 runtime resource cleanup
status: in_progress
type: maintenance
owner: owner
decision_refs: ADR-020, ADR-021
requirement_refs: DEC-034, DEC-041, DEC-047
milestone_ref: MS-004
delivery_refs: V2-W0804
parent_work_item: none
depends_on: WI-047
execution_scope: isolated
production_effects: none
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
- Permanently protect canonical total-asset snapshots and holdings, domestic/overseas order and transaction history,
  trade/cash/lot/thread/journal history, V2 Bronze/Silver/Gold/Control objects, local and private-GCS recovery artifacts,
  and every object referenced by a current backup manifest. WI-049 cannot authorize their deletion.

## Acceptance criteria

- [ ] owner approves exact targets and recovery artifacts.
- [ ] active/rollback/V2 resources cannot match cleanup.
- [ ] post-cleanup smoke and cost evidence pass.

## Change impact

- Destructive but recoverable deployment cleanup.

## Plan

1. Freeze read-only inventory, protected history and recovery evidence. 2. Obtain exact-target approval and remove
   only retired one-time Job definitions. 3. Re-inventory and smoke the canonical runtime. 4. Review Artifact Registry
   versions as a separate destructive family; never infer image approval from Job approval.

## Sub-items

- `WI-049-S01` — verified: freeze runtime inventory, history protections and recovery evidence.
- `WI-049-S02` — proposed: execute owner-approved one-time Cloud Run Job cleanup.
- `WI-049-S03` — proposed: review and execute separately approved Artifact Registry image cleanup.

## Evidence

- Activated 2026-09-13 after WI-048 closed. The current isolated phase is read-only inventory, dependency analysis,
  recovery capture and exact cleanup-manifest generation; production deletion, IAM/Secret mutation and Scheduler or
  Cloud Run changes remain disabled until the owner reviews the exact targets and recovery artifacts.
- Owner reaffirmed that total-asset and trade-history preservation is critical. Repository evidence records only
  aggregate metadata and resource names; portfolio values, holdings, account identifiers and secret values are
  excluded.
- `WI-049-S01` froze 15 protected dataset row-count baselines, 19 protected runtime/storage resources, 11 unscheduled
  one-time Cloud Run Job candidates, their last successful executions, non-secret configuration hashes, deployment
  references and exact recovery references in
  `governance/project/evidence/wi049/runtime-cleanup-readiness-2026-09-13.json`. The review-only schema forces
  `apply_allowed=false`, `owner_approved=false` and denies data, backup, IAM, Secret and Scheduler changes.
- The latest private WI-048 post-backup index exists at its content-addressed URI with SHA-256
  `bc91f37b...68da0`; its production workflow already passed fresh restore. No new backup or database write was needed
  for this read-only phase.
- Artifact Registry inventory found 64 untagged versions older than 30 days in `cloud-run-source-deploy`, but none is
  authorized or nominated by S01. Image cleanup remains S03 because active, forward-recovery and Job-recreation
  digests must be protected independently from Job-definition cleanup.
- Focused guardrail verification passed 23 tests; related guardrail/readiness verification passed 33 tests; the full
  gate passed 682 tests with one existing Authlib deprecation warning. No Cloud Run, Scheduler, IAM, Secret, Firestore,
  MotherDuck, GCS or Artifact Registry mutation occurred.

## Closeout

- Result: in progress; destructive execution has not started.
- Remaining risk: S02 still needs owner approval of the exact 11 Job names. Deleting a Job definition also removes its
  Cloud Run execution view, so the frozen manifest and GitHub evidence are the durable replacement. S03 requires a
  later, independent exact-digest review and approval.
- Follow-up Work Item: WI-051.
