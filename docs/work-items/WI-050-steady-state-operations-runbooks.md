---
id: WI-050
title: Finalize steady-state recovery cost and source review runbooks
status: closed
type: maintenance
owner: owner
decision_refs: ADR-020, ADR-021, ADR-023
requirement_refs: DEC-038..041, DEC-047
milestone_ref: MS-004
delivery_refs: V2-W0805
parent_work_item: none
depends_on: WI-047, WI-048
execution_scope: isolated
production_effects: none
architecture_impact: none
data_impact: documents restore capacity and source-contract review cadence
security_impact: includes quarterly IAM and secret review without values
cost_impact: monthly capacity and cost review
---

# WI-050 — Finalize steady-state recovery cost and source review runbooks

## Problem and evidence

The final platform needs repeatable quarterly restore and monthly capacity/cost/source review after project cutover.

## Classification and contract

- `maintenance` operationalization of approved SLO, cost and governance cadence.

## Scope

- Include restore rehearsal, capacity, cost, source rights, IAM and exception review procedures.
- Exclude creating recurring automation unless separately requested.

## Acceptance criteria

- [x] a maintainer can execute each runbook from clean prerequisites.
- [x] RPO/RTO, cost thresholds and escalation actions are measurable.
- [x] release/full gates pass.

## Change impact

- Documentation and reproducible scripts only.

## Plan

1. Consolidate evidence. 2. Rehearse procedures. 3. Record cadence and escalation.

## Sub-items

- `none`.

## Evidence

- Activated 2026-09-14 after WI-047 and WI-048 closed and WI-049 cleanup completed. The active phase is limited to
  documentation, fixtures, read-only inspection and local restore verification. It does not create recurring
  automation, mutate production data, deploy resources, change IAM/Secrets or activate a source.
- `docs/operations/steady-state-operations-runbook.md` now owns the monthly, quarterly and release review procedure,
  including clean prerequisites, evidence boundaries, thresholds, escalation actions and explicit non-authorization
  of production changes. `scripts/steady_state_operations.py` evaluates the evidence deterministically and
  `scripts/verify_private_object_recovery.py` verifies restricted objects without emitting object names or content.
- The 2026-09-14 quarterly rehearsal restored the immutable WI-048 backup into a fresh local database: 79 backup
  objects / 14,409,499 bytes, 78 restored tables through migration `0019`, index SHA-256
  `bc91f37b77f5bc2ef98d218a416337de71e2112ccecba2bf879b8afd15968da0`, measured RPO 522 minutes and conservative
  download-plus-restore RTO 8 seconds. All 33 private objects / 3,954,341 bytes matched their recorded hashes.
- Read-only capacity and governance review found 129.7 MiB in MotherDuck, 49 artifact versions, exact runtime counts
  of 2 services / 6 jobs / 6 schedulers, zero minimum instances and explicit maximum caps. All 19 source contracts
  were reviewed: 13 approved, 6 proposed, with no approved unknown-rights or unknown-cost contracts and no prohibited
  collection attempt. IAM/Secret metadata review counted 4 service accounts and 26 Secret resources without payload
  reads or mutations; no overbroad finding was recorded. Current exception review found 57 reconstruction items,
  zero owner-review items and zero registered emergency exceptions.
- `governance/project/evidence/wi050/steady-state-review-2026-09-14.json` evaluates `pass`, with no blockers, cost state
  `normal` at KRW 434, action `continue_within_approved_limits`, and `production_change_authorized=false`.
- Verification: focused steady-state tests `37 passed`; `bash scripts/check.sh quick` passed; final
  `bash scripts/check.sh full` passed with `710 passed` and one existing Authlib deprecation warning.

## Closeout

- Result: closed. The initial monthly/quarterly/release operating baseline is executable and its first quarterly
  local/read-only rehearsal is within RPO, RTO, cost, capacity, source, access and exception guardrails.
- Remaining risk: future review snapshots require a maintainer to capture fresh evidence; recurring automation still
  requires a separate explicit user request. The cost input is the approved 2026-09-11 snapshot and must be refreshed
  at the next review. Local temporary restore files are not repository evidence.
- Follow-up Work Item: WI-051.
