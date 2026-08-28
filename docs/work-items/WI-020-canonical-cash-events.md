---
id: WI-020
title: Establish canonical cash events and classification revisions
status: ready
type: change
owner: owner
decision_refs: ADR-021, ADR-023, V2-ADR-006, V2-ADR-010, V2-ADR-012
requirement_refs: DEC-009..014, DEC-026, DEC-038, DEC-041, DEC-044
milestone_ref: MS-002
delivery_refs: V2-W0304
parent_work_item: none
depends_on: WI-013, WI-016
architecture_impact: completes the approved immutable transaction and cash-event boundary
data_impact: canonical cash events plus append-only classification revisions and point-in-time provenance
security_impact: confidential cash facts remain in governed Bronze and Silver
cost_impact: existing KIS and MotherDuck scale-to-zero paths only
---

# WI-020 — Establish canonical cash events and classification revisions

## Problem and evidence

Cash balances exist, but replay-safe external cash-flow events and versioned classification do not. A balance delta
must not be promoted to a deposit, withdrawal, fee, dividend or internal transfer without source evidence.

## Classification and contract

- `change` implementing the approved cash-event boundary required by V2-W0502.
- Event identity is immutable; classification corrections append revisions.

## Scope

- Include effective/settled/knowledge/fetched/recorded time, provenance, link quality and classification revisions.
- Exclude three-year collection, performance calculation and inferred balance-difference events.

## Acceptance criteria

- [ ] owner flows, internal transfers, trade settlement, fees/taxes and dividends remain distinct.
- [ ] unmatched/partial events remain reversible and point-in-time.
- [ ] migration, catalog, repository, backup/restore and full gates pass.

## Change impact

- Additive governed data contracts only; no destructive correction or external surface.

## Plan

1. Freeze event and classification grains.
2. Add additive migration/repository and deterministic fixtures.
3. Reconcile bounded samples and recovery coverage.

## Sub-items

- `none`.

## Evidence

- Pending.

## Closeout

- Result: ready.
- Remaining risk: long-range source coverage belongs to WI-021.
- Follow-up Work Item: WI-021.
