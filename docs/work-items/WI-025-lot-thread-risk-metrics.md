---
id: WI-025
title: Implement lot and thread path and risk metrics
status: closed
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

- [x] lot, thread and symbol totals reconcile against canonical quantities.
- [x] additions/partial exits and zero-quantity episode resets are deterministic.
- [x] freshness and incomplete risk plans fail closed.

## Change impact

- Gold metric additions only; no trading authority.

## Plan

1. Freeze path/risk formulas and fixtures.
2. Implement point-in-time evaluation.
3. Verify reconstruction, quality and recovery.

## Sub-items

- `none`.

## Evidence

- Project OS, Data Governance Harness, Warehouse Contract and portfolio operations procedures reviewed. WI-015,
  WI-019, WI-022 and WI-024 are closed. Adjusted point-in-time price revisions and typed owner stop plans exist in the
  repository contract, while production remains intentionally missing plan/allocation coverage.
- Eight approved metric contracts and Decimal formulas cover lot MFE/MAE, episode high/drawdown and owner-stop
  thread/instrument planned loss and risk ratios. Six focused tests prove independent DuckDB goldens, replay no-op,
  future/missing owner-plan null outcomes, partial-exit quantity changes, episode reset, quantity mismatch and complete
  backup/restore; the full gate passed 374 tests.
- Aggregate-only production inspection returned `publish_ready=false`: 0 reconstructed episode/lot rows, 0 adjusted
  operational-strict price rows, 57 open reconstruction exceptions and one missing required object. It performed no
  write, source call, migration or activation. See `docs/operations/wi-025-lot-thread-risk-readiness.md`.

## Closeout

- Result: closed; repository contract, evaluator, fail-closed quality, recovery and aggregate production-readiness
  evidence are complete.
- Remaining risk: production values remain intentionally unavailable until reconstruction, adjusted-price and
  owner-authored plan coverage pass together; activation is not part of this Work Item.
- Follow-up Work Item: WI-028.
