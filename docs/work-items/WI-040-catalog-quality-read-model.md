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

- `WI-040-S01` — research catalog, quality, lineage and pipeline read-model contracts (`closed`).

## Pre-research checkpoint

`WI-040-S01` is research-only. Parent `WI-040` remains `proposed`; MS-003's formal implementation gate remains
closed.

| Checkpoint | State | Evidence |
| --- | --- | --- |
| research boundary and current implementation audit | complete | existing manifest/file reader and Control SQL projection inspected |
| sensitivity and false-green threat review | complete | restricted metadata, arbitrary quality details, missing metric catalog and non-pass aggregation gaps identified |
| physical/logical contract gap review | complete | five Control objects lack governed dataset contracts; live inventory unavailable rather than assumed green |
| implementation inputs and unknowns | complete | `docs/operations/wi-040-pre-research-2026-09.md` |

Allowed scope was repository and live read-only inspection, DTO/query boundary analysis and implementation-gap
identification. It excluded contract lifecycle changes, DDL, DB writes, public MCP registration, deployment and source
calls.

## Evidence

- `WI-040-S01` closed on 2026-09-01 with no production mutation.
- `docs/operations/wi-040-pre-research-2026-09.md`: read-model contract and fail-closed implementation inputs.

## Closeout

- Result: parent proposed; `WI-040-S01` research closed without opening the MS-003 formal gate.
- Remaining risk: public scope compatibility belongs to WI-042.
- Follow-up Work Item: WI-042.
