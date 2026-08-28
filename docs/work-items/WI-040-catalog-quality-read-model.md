---
id: WI-040
title: Publish the DB-only catalog and quality read model
status: proposed
type: change
owner: owner
decision_refs: ADR-021, ADR-023
requirement_refs: DEC-038, DGOV-005..008
milestone_ref: MS-003
delivery_refs: V2-W0410
parent_work_item: none
depends_on: WI-012, WI-019, WI-020
architecture_impact: none; read model inside approved data plane
data_impact: governed catalog quality and lineage projections
security_impact: no secret or raw confidential payload exposure
cost_impact: DB-only bounded queries
---

# WI-040 — Publish the DB-only catalog and quality read model

## Problem and evidence

Control tables exist, but a stable DB-only consumer model cannot yet explain dataset grain, freshness, quality,
lineage and pipeline status to Remote MCP.

## Classification and contract

- `change` implementing governed consumption without exposing arbitrary SQL.

## Scope

- Include catalog, quality, lineage and run status DTOs with sensitivity filtering.
- Exclude public MCP registration, which belongs to WI-042.

## Acceptance criteria

- [ ] model explains version/grain/freshness/gaps and rejects restricted leakage.
- [ ] partial and failed runs are not presented as green.
- [ ] deterministic query, authorization and full gates pass.

## Change impact

- Read-only application query and MotherDuck projection.

## Plan

1. Freeze DTOs. 2. Implement projections. 3. Verify sensitivity and degraded states.

## Sub-items

- `none`.

## Evidence

- Pending.

## Closeout

- Result: proposed.
- Remaining risk: public scope compatibility belongs to WI-042.
- Follow-up Work Item: WI-042.
