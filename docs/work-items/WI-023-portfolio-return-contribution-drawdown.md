---
id: WI-023
title: Implement portfolio return contribution and drawdown
status: proposed
type: change
owner: owner
decision_refs: ADR-021, ADR-023, V2-ADR-006, V2-ADR-010, V2-ADR-012
requirement_refs: DEC-004, DEC-009..017, DEC-026, DEC-038, DEC-041, DEC-044
milestone_ref: MS-002
delivery_refs: V2-W0502
parent_work_item: none
depends_on: WI-009, WI-015, WI-020, WI-021, WI-022
architecture_impact: implements approved Gold performance metrics on canonical ledgers
data_impact: cash-flow-adjusted return, contribution/residual and drawdown metric values
security_impact: derived portfolio values remain confidential and internal
cost_impact: scale-to-zero daily and replay computation
---

# WI-023 — Implement portfolio return contribution and drawdown

## Problem and evidence

Canonical asset values alone cannot distinguish investment performance from owner deposits and withdrawals.

## Classification and contract

- `change` implementing V2-W0502.
- Modified Dietz and chain-linked wealth/drawdown use only point-in-time canonical inputs.

## Scope

- Include return, contribution, residual, reconciliation and quality states.
- Exclude alert thresholds and Telegram.

## Acceptance criteria

- [ ] independent fixtures match metric output and residual is explicit.
- [ ] future knowledge and unclassified cash flows fail closed or remain partial.
- [ ] direct SQL and metric repository agree by version.

## Change impact

- Gold metrics only; no new provider or external interface.

## Plan

1. Freeze formulas and reconciliation tolerances.
2. Implement point-in-time evaluator and fixtures.
3. Verify replay, quality and restore.

## Sub-items

- `none`.

## Evidence

- Pending.

## Closeout

- Result: proposed; dependencies incomplete.
- Remaining risk: continuous history and cash classification.
- Follow-up Work Item: WI-028.
