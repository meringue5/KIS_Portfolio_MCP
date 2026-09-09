---
id: WI-040
title: Publish the DB-only catalog and quality read model
status: verified
type: change
owner: owner
decision_refs: ADR-021, ADR-023
requirement_refs: DEC-038, DGOV-005..008
milestone_ref: MS-003
delivery_refs: V2-W0410
parent_work_item: none
depends_on: WI-012, WI-019, WI-020
execution_scope: isolated
production_effects: none
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

- [x] model explains version/grain/freshness/gaps and rejects restricted leakage.
- [x] partial and failed runs are not presented as green.
- [x] deterministic query, authorization and full gates pass.

## Change impact

- Read-only application query and MotherDuck projection.

## Plan

1. Freeze DTOs. 2. Implement projections. 3. Verify sensitivity and degraded states.

## Isolated implementation checkpoint — 2026-09-09

`WI-040` entered `in_progress` under the MS-003 isolated-overlap gate after the owner approved implementation.
This stage is limited to typed application DTOs, fixed packaged-registry readers, bounded read-only Control queries,
synthetic fixtures and local verification. It must retain `execution_scope: isolated` and
`production_effects: none`.

No DDL or migration, live DB write, source call or activation, IAM/Secret change, Cloud Run/Scheduler change, public
MCP registration, cleanup or cutover is authorized. If the existing Control schema cannot support the approved DTOs
without semantic overloading, implementation stops and records an additive migration proposal instead of changing
the schema.

The isolated implementation reached `verified` on 2026-09-09. Existing Control columns were sufficient, so no DDL or
migration proposal was needed. Verification is limited to packaged manifests, synthetic DuckDB Control evidence and
local repository gates; it does not activate the inactive read-model contracts or authorize production/public use.

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
- `src/kis_portfolio/services/governance_read_models.py`: immutable envelope and policy DTOs, fixed packaged catalog
  projection, bounded parameterized Control queries, strict cursor validation, sensitivity filtering, opaque refs and
  fail-closed status composition.
- `tests/test_governance_read_models.py`: 12 synthetic tests covering six catalog kinds, proposed/restricted/raw-field
  suppression, pass/failed/partial/stale/not-assessed/unavailable, unknown evidence, authorization, bounds and stable
  cursor pagination.
- `tests/test_project_os_contract.py`: overlap fixture no longer inherits whichever Work Item is active in the source
  checkout, keeping the full gate reproducible during an authorized implementation.
- `bash scripts/check.sh quick`: passed throughout implementation.
- `bash scripts/check.sh full`: 518 passed on 2026-09-09 with one existing Authlib deprecation warning.

## Closeout

- Result: parent `verified`; internal application DTO/query implementation and synthetic local verification complete
  with no production effects. `WI-040-S01..S03` remain closed design/adoption history.
- Remaining risk: no default executable per-pipeline coverage/freshness policy is inferred from prose, so pipelines
  without a separately registered exact policy remain `not_assessed`. No live Control query was performed in this
  isolated phase.
- Follow-up Work Item: WI-042 owns public MCP names, OAuth actor/scope wiring, serialization and client compatibility;
  activation remains blocked by the MS-003 production gate.

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
