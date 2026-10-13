---
id: WI-069
title: Align Project OS recovery lanes with stabilization and steady-state operations
status: closed
type: governance
owner: owner
decision_refs: owner-approved five-step Project OS and signal-recovery plan 2026-10-13
requirement_refs: GOV-004, GOV-005, GOV-006, GOV-008..013
milestone_ref: MS-GOV
delivery_refs: none
parent_work_item: none
depends_on: WI-056
discovered_from: WI-056
supersedes: none
rollback_of: none
work_lane: operations
execution_scope: repository governance only
production_effects: none
architecture_impact: Project OS lifecycle and checker only; product architecture is unchanged
data_impact: no data contract, schema, migration or production row mutation
security_impact: no credential, permission or trust-boundary change
cost_impact: repository-local policy and tests only
user_visible_impact: no
real_use_acceptance: not_applicable
real_use_evidence_refs: not_applicable
stabilization_window: none
stabilization_exit_refs: none
rollback_plan: revert this repository-only governance change
---

# WI-069 — Align Project OS recovery lanes with stabilization and steady-state operations

## Problem and evidence

Project OS policy already requires a corrective Work Item to move through `in_progress` while its parent milestone
remains `stabilizing`, but the checker only permits active work under `ready` or `in_progress` milestones. That
contradiction pushed routine stabilization defects toward unnecessary new milestones. The lifecycle also did not
state clearly how a closed delivery milestone hands off later defects to steady-state operations.

## Classification and contract

- Classification: governance defect discovered from WI-056.
- Contract: preserve immutable milestone history, append-only feedback and the single implementation-WIP limit.
- Owner approval: the owner approved the five-step Project OS correction followed by the MS-006 signal restoration.

## Scope

- Include: stabilization recovery and post-closure operations lanes, milestone exit/handoff criteria and checker tests.
- Include: prohibit product-scope expansion through corrective lanes.
- Exclude: product runtime, database, infrastructure, deployment and Telegram mutation.

## Acceptance criteria

- [x] A linked corrective defect can be `in_progress` while its milestone remains `stabilizing`.
- [x] A linked operational defect can be `in_progress` without reopening a `closed` milestone.
- [x] Unlinked, non-corrective or incorrectly labelled work remains rejected.
- [x] Single-WIP, dependency, production and real-use gates remain intact.
- [x] Focused, quick and full checks pass.

## Change impact

- Architecture: Project OS control architecture only.
- Data/schema/backup: none.
- Security/privacy: none.
- MCP/API compatibility: none.
- Deployment/rollback: no deployment; revert the governance commit if needed.
- Cost/SLO: no runtime cost.

## Plan

1. Define finite milestone exit and steady-state operations handoff.
2. Add corrective work-lane metadata and checker rules.
3. Add positive and negative contract tests.
4. Run shared gates and close this repository-only correction.

## Sub-items

- `none`.

## Stabilization plan

- Not applicable. This is repository-only governance with no production effect.

## Real-use acceptance

- Not applicable because there is no user-visible runtime behavior.

## Evidence

- `uv run pytest -q tests/test_project_os_contract.py`: 26 passed.
- `bash scripts/check.sh quick`: passed with 69 tracked Work Items and one active implementation WIP.
- `bash scripts/check.sh full`: 818 passed with one pre-existing Authlib deprecation warning.
- Positive fixtures cover active corrections under both a stabilizing and a closed milestone; negative fixtures reject
  missing lane labels and product-scope `change` work disguised as an operational correction.

## Closeout

- Result: closed. Policy, template, Skill, checker and fixtures now share the same recovery/operations lifecycle.
- Remaining risk: the contract cannot replace human review of falsely classified scope, so owner approval remains
  required for a genuinely new milestone or product boundary.
- Follow-up Work Item: WI-070 permanent held-position Telegram signal restoration under MS-006.
