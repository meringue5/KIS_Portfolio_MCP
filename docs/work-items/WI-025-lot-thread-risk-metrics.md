---
id: WI-025
title: Implement lot and thread path and risk metrics
status: proposed
type: change
owner: owner
decision_refs: ADR-021, ADR-023, V2-ADR-006, V2-ADR-010, V2-ADR-012
requirement_refs: DEC-012..017, DEC-027, DEC-038, DEC-041, DEC-044
milestone_ref: MS-002
delivery_refs: V2-W0504
parent_work_item: none
depends_on: WI-015, WI-019, WI-022, WI-024
architecture_impact: implements approved lot/thread analytical metrics
data_impact: MFE MAE episode high planned loss and 2 percent risk metrics
security_impact: derived confidential position values remain internal
cost_impact: scale-to-zero daily and replay computation
---

# WI-025 — Implement lot and thread path and risk metrics

## Problem and evidence

Average-cost portfolio views do not expose each purchase lot/thread path, drawdown sensitivity or owner stop risk.

## Classification and contract

- `change` implementing V2-W0504.
- Owner stop dominates; 2N ATR is suggestion-only and missing inputs yield unknown/partial.

## Scope

- Include MFE, MAE, episode high, planned loss, 2% cap and position/thread aggregation.
- Exclude order execution and Telegram delivery.

## Acceptance criteria

- [ ] lot, thread and symbol totals reconcile against canonical quantities.
- [ ] additions/partial exits and zero-quantity episode resets are deterministic.
- [ ] freshness and incomplete risk plans fail closed.

## Change impact

- Gold metric additions only; no trading authority.

## Plan

1. Freeze path/risk formulas and fixtures.
2. Implement point-in-time evaluation.
3. Verify reconstruction, quality and recovery.

## Sub-items

- `none`.

## Evidence

- Pending.

## Closeout

- Result: proposed; dependencies incomplete.
- Remaining risk: owner-authored plan coverage.
- Follow-up Work Item: WI-028.
