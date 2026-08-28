---
id: WI-027
title: Implement nested ETF look-through and impact
status: rejected
type: change
owner: owner
decision_refs: ADR-021, ADR-023, ADR-024, V2-ADR-006, V2-ADR-010, V2-ADR-012
requirement_refs: DEC-018, DEC-019, DEC-026, DEC-038, DEC-041, DEC-044, DEC-049
milestone_ref: MS-002
delivery_refs: V2-W0505
parent_work_item: none
depends_on: WI-009, WI-017, WI-026
architecture_impact: implements approved exposure analysis over governed ETF snapshots
data_impact: direct and nested constituent exposure residual confidence and impact metrics
security_impact: combines confidential position value with public constituents inside MotherDuck only
cost_impact: scale-to-zero materialization over currently held ETFs
---

# WI-027 — Implement nested ETF look-through and impact

## Problem and evidence

ETF market value is visible, but its company, country, sector and currency exposure cannot be attributed until official
constituent snapshots are joined point-in-time to current positions.

## Classification and contract

- `change` implementing V2-W0505.
- Nested ETF expansion is capped at three levels with cycle guard and explicit residual/confidence.

## Scope

- Include direct/indirect exposure, nested expansion, residual, confidence and impact estimates.
- Exclude double-counting ETF market value in canonical total assets.

## Acceptance criteria

- [ ] source-date alignment and cycle/depth guards are deterministic.
- [ ] weights, residual and confidence reconcile without silent normalization.
- [ ] stale/partial source quality propagates to consumers.

## Change impact

- Gold exposure products only; no public MCP or Telegram activation.

## Plan

1. Freeze exposure grain and recursive rules.
2. Implement independent fixtures and point-in-time joins.
3. Verify quality, reconciliation and restore.

## Sub-items

- `none`.

## Evidence

- WI-026 official-source rights review found no production-approved complete constituent source; KIS remains a partial
  cross-check only.
- 2026-08-28 owner chose option 3, excluding ETF impact analysis from initial V2 while preserving later research.

## Closeout

- Result: rejected from initial V2 scope without implementation; acceptance criteria remain intentionally unmet.
- Remaining risk: provider coverage and source-date gaps.
- Follow-up Work Item: WI-028 proceeds without constituent exposure; future reintroduction requires a new Work Item.
