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
- `WI-040-S02` — freeze DB-only authority, Control evidence datasets, DTOs, sensitivity, false-green status and bounded
  query contracts without implementation or public MCP registration (`closed after owner approval`).
- `WI-040-S03` — adopt the approved DGH schema, six Control evidence datasets, three inactive read models and canonical
  requirements/system-design clarification without implementation or public MCP registration (`closed`).

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

## Contract design checkpoint — 2026-09-02

- `DB-only` means packaged canonical manifest plus MotherDuck Control evidence with no provider call. A derived DB
  catalog snapshot is rejected because it would create a second authority and reconciliation burden.
- Six logical Control evidence datasets map the existing five evidence tables and compatibility summary view; no new
  DDL is expected. A source-less run ledger receives a tightly limited `control_origin` DGH rule.
- Three versioned inactive application contracts are `data-catalog-v1`, `data-quality-v1` and `pipeline-run-v1`.
  WI-042 alone owns their future public MCP registration.
- Catalog projection covers source, dataset, metric, pipeline, macro series and physical object. Proposed planning
  records and restricted details are excluded from the Remote MCP result.
- Typed DTOs suppress raw JSON, error text, partition keys, object locators, secret/auth and internal cost fields.
  Page/lookback and 256 KiB response ceilings are fixed.
- Overall status precedence is `unavailable > failed > partial > stale > not_assessed > pass`; a succeeded run or empty
  evidence cannot independently produce green.
- Evidence: `docs/operations/wi-040-s02-read-model-contract-design-2026-09.md`.
- Verification: Project OS/DGH/architecture/warehouse/MCP gates and full 440-test suite passed.
- Result: owner approved all eight recommendations and S03 adopted them without application/runtime activation.
  Parent WI-040 and MS-003 remain proposed.
- Remaining prework: WI-042-S01 is the next useful research checkpoint. WI-043~046
  should wait for their upstream contract/evidence gates rather than produce stale research.

## Canonical adoption checkpoint — 2026-09-02

- Six existing Control objects/views now have approved logical dataset contracts. No DDL, migration or physical object
  change occurred.
- DGH now owns three `approved + inactive` read-model contracts and rejects unsafe source-less origins, overlapping
  allowed/suppressed fields, unbounded sizes and premature production activation.
- Requirements, system design, DGH policy and physical catalog links now express one DB-only authority and false-green
  rule. Public MCP/OAuth behavior remains WI-042 scope.
- Evidence: `docs/operations/wi-040-s03-contract-adoption-2026-09.md`.
- Verification: DGH 161 contracts, focused 10 tests, quick passed, full 443 passed with one existing warning.
- Result: S03 closed; parent WI-040 and MS-003 remain proposed and implementation stays gated.
