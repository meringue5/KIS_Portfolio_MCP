---
id: WI-024
title: Add typed thread risk plans and review state
status: proposed
type: change
owner: owner
decision_refs: ADR-021, ADR-023, V2-ADR-006, V2-ADR-010, V2-ADR-012
requirement_refs: DEC-012..014, DEC-027, DEC-031, DEC-038, DEC-044
milestone_ref: MS-002
delivery_refs: V2-W0305, V2-W0306
parent_work_item: none
depends_on: WI-010, WI-022
architecture_impact: implements approved owner-authored risk-plan and review revisions
data_impact: typed stop/reference/risk-plan revisions and sell-allocation review state
security_impact: confidential investment intent remains internal and revision-audited
cost_impact: negligible database writes; no always-on service
---

# WI-024 — Add typed thread risk plans and review state

## Problem and evidence

Journal prose is not an authoritative stop price, and missing lot/thread or sell allocation intent needs an explicit
owner review workflow before risk metrics can claim completeness.

## Classification and contract

- `change` implementing approved DEC-027 and DEC-031.
- Owner revisions are authoritative; ATR-derived stops remain advice metadata.

## Scope

- Include typed risk-plan versions, optimistic revision, review queue and audit actor.
- Exclude public MCP write exposure and automatic order execution.

## Acceptance criteria

- [ ] stop/reference/risk budget revisions are point-in-time and immutable.
- [ ] unanswered review items remain explicit and do not invent intent.
- [ ] concurrency, authorization boundary and restore tests pass.

## Change impact

- Additive Control/Silver state only; Remote MCP write adapter remains later work.

## Plan

1. Freeze typed plan and review contracts.
2. Add repository and revision tests.
3. Reconcile reconstructed threads without synthesizing owner intent.

## Sub-items

- `none`.

## Evidence

- Pending.

## Closeout

- Result: proposed; depends on WI-022.
- Remaining risk: later MCP journal/write workflow.
- Follow-up Work Item: WI-025.
