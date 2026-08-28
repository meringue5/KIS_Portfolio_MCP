---
id: WI-034
title: Identify and baseline all remaining V2 delivery work
status: closed
type: governance
owner: owner
decision_refs: ADR-021, ADR-022
requirement_refs: GOV-003, GOV-004, GOV-006, GOV-008
milestone_ref: MS-GOV
delivery_refs: none
parent_work_item: none
depends_on: WI-031
architecture_impact: planning baseline only; does not implement or change product boundaries
data_impact: records ownership of approved delivery items; no schema or row mutation
security_impact: no credentials or account data
cost_impact: repository-local deterministic inventory only
---

# WI-034 — Identify and baseline all remaining V2 delivery work

## Problem and evidence

MS-003 and MS-004 have outcome boundaries, but most remaining V2 delivery IDs have no immutable Work Item owner.
Conversely, several early delivery IDs appear unallocated even though WI-005 through WI-012 already implemented them.
Allocating from a raw missing-reference list would duplicate completed work. MS-003 also names the completed V2-W0409
inside a coarse remaining range.

## Classification and contract

- Classification: `governance` planning correction.
- Compare delivery plan, completed Work Item evidence, current code/migrations/deployment and milestone registry.
- Preserve every existing WI identity; completed work receives historical disposition, actual residual scope receives
  the next unused WI IDs.
- User approved this re-identification before sequential WI-020 and WI-019 delivery.

## Scope

- Include all V2-W0001 through V2-W0807 delivery IDs, historical ownership, remaining WI allocation, dependencies,
  milestone sequence and deterministic completeness checks.
- Exclude product implementation, provider activation, production changes and external messages.

## Acceptance criteria

- [x] Every delivery-plan ID is historically completed or owned by a registered current/future Work Item.
- [x] Completed V2-W0409 is removed from MS-003 remaining scope.
- [x] MS-002 residual corporate-action gap and all MS-003/MS-004 work have stable owners and dependencies.
- [x] No existing WI ID or outcome is renumbered or silently widened.
- [x] Project OS quick/full gates pass.

## Change impact

- Architecture: none; maps already approved architecture to executable work.
- Data/schema/backup: none.
- Security/privacy: none.
- MCP/API compatibility: none.
- Deployment/rollback: repository-only revert.
- Cost/SLO: no runtime cost.

## Plan

1. Classify each delivery ID from repository evidence.
2. Register historical ownership for completed pre-registry work.
3. Allocate new Work Items for independent remaining outcomes.
4. Enforce complete delivery ownership in the Project OS checker.
5. Run gates and close before activating WI-020.

## Sub-items

- `none`.

## Evidence

- All 69 delivery-plan IDs are covered by a registered Work Item or an explicit closed `delivery_history` entry.
- `WI-035` through `WI-051` were appended without changing any existing identity; WI-036 owns the residual
  corporate-action gap, and WI-032 remains the final documentation gate.
- The Project OS checker now rejects unowned delivery IDs, unknown historical owners and duplicate history entries.
- `uv run pytest -q tests/test_project_os_contract.py`: 8 passed.
- `bash scripts/check.sh quick`: passed.
- `bash scripts/check.sh full`: 254 passed, one third-party Authlib deprecation warning.

## Closeout

- Result: closed; the remaining V2 delivery baseline is complete and machine enforced.
- Remaining risk: later discoveries still require append-only WI/sub-item intake under Project OS.
- Follow-up Work Item: WI-020.
