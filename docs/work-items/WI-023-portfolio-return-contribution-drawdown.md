---
id: WI-023
title: Implement portfolio return contribution and drawdown
status: closed
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
- Formula contract: `R = (EMV - BMV - sum(CF)) / (BMV + sum(weight * CF))`, where
  `weight = (period_end - effective_at) / (period_end - period_start)`.
- Component contribution uses the same denominator; external owner flows are assigned only to the matching cash
  currency component. Contribution sum plus explicit residual must equal return within `0.0000000001`.
- Drawdown is `wealth / running_high_water - 1`; absolute total assets are never used as the high-water series.

## Scope

- Include return, contribution, residual, reconciliation and quality states.
- Exclude alert thresholds and Telegram.
- Reuse `gold.metric_values`; no migration, source call, public MCP surface or production schedule is added.
- Require exact cash-flow coverage evidence, equal account coverage, pass state rows and KRX calendar continuity.
- Until point-in-time FX cash-event revisions exist, non-KRW external owner flows remain unavailable.

## Acceptance criteria

- [x] independent fixtures match metric output and residual is explicit.
- [x] future knowledge and unclassified cash flows fail closed or remain partial.
- [x] direct SQL and metric repository agree by version.

## Change impact

- Gold metrics only; no new provider or external interface.

## Plan

1. Freeze formulas and reconciliation tolerances.
2. Implement point-in-time evaluator and fixtures.
3. Verify replay, quality and restore.

## Sub-items

- `none`.

## Evidence

- Project OS, Data Governance Harness, Warehouse Contract and portfolio operations contracts reviewed before
  implementation. WI-009, WI-015 and WI-020~022 are closed; unresolved reconstruction scopes remain explicit quality
  blockers rather than inferred performance inputs.
- Five approved metric contracts, deterministic Decimal formulas, a point-in-time evaluator and explicit-version
  repository read model are implemented. Independent DuckDB SQL, future-knowledge, replay, account/calendar/cash
  coverage, chain-gap and complete backup/restore tests pass (`9` WI-023 tests; adjacent metric suite `22` tests).
- The production read-only readiness inspection observed 920 portfolio-state rows across 28 dates: 31 pass and 889
  non-pass. It also observed 49 canonical cash events but zero passing exact external-cash-flow coverage results.
  Therefore `publish_ready=false`; the inspection made zero source calls and zero warehouse writes. Aggregate evidence
  is recorded in `docs/operations/wi023-performance-readiness-2026-08.md`.
- Full repository gate: `363` tests passed.

## Closeout

- Result: closed; W0502 formula, evaluator, persistence, replay and recovery contracts are implemented.
- Remaining risk: production numeric publication remains fail-closed until canonical portfolio-state quality and exact
  cash-flow coverage pass. The 57 open reconstruction exceptions remain contextual upstream evidence and are not
  silently converted into performance inputs.
- Follow-up Work Item: WI-028 may consume only passing versioned values; upstream state/cash coverage remediation is
  tracked as data-quality work rather than weakening this contract.
