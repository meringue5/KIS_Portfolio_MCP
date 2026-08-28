---
id: WI-036
title: Establish corporate-action identity and adjustment lineage
status: closed
type: change
owner: owner
decision_refs: ADR-021, ADR-023
requirement_refs: DEC-015..017
milestone_ref: MS-002
delivery_refs: V2-W0307
parent_work_item: none
depends_on: WI-015
architecture_impact: none; completes the approved price and ledger model
data_impact: versioned corporate-action identity and price/lot adjustment lineage
security_impact: internal market facts only
cost_impact: bounded held-instrument collection and replay
---

# WI-036 — Establish corporate-action identity and adjustment lineage

## Problem and evidence

Dual-basis price and FX ledgers are present, but split, reverse split, symbol change, merger and spin-off identity is not
yet a governed ledger that downstream lot and performance logic can cite.

## Classification and contract

- `change` completing V2-W0307; it does not reinterpret existing raw/adjusted prices.
- Contract-first source, dataset and pipeline changes are required before collection.

## Scope

- Include immutable action identity, effective/knowledge time, source provenance and price/lot adjustment links.
- Exclude tax advice and unsupported historical inference.

## Acceptance criteria

- [x] actions and revisions are point-in-time and idempotent.
- [x] price/quantity adjustment lineage is explicit; unknown action blocks false return claims.
- [x] migration, repository, backup/restore and full gates pass.

## Change impact

- Additive Silver/Control contracts; no public MCP or external send.

## Plan

1. Approve source/dataset contract. 2. Add migration/repository. 3. Reconcile split fixtures and recovery.

## Sub-items

- `none`.

## Evidence

- Source preflight found no new provider requirement: the approved `source.kis-open-api` exposes domestic KSD
  merger/split and face-value replacement schedules plus overseas period-rights revisions for the held-instrument scope.
- `dataset.corporate-action-event` and `pipeline.corporate-actions-v2` define immutable source identity, content
  revisions, point-in-time terms, held-instrument coverage evidence and fail-closed publish rules; DGH passes with
  86 registered contracts.
- Migration `0009_corporate_action_ledger.sql` adds three backed-up Silver tables and one rebuild view. The V2 registry
  and catalog agree on 48 objects: 40 tables and eight views; 39 tables are in the complete backup allowlist.
- `CorporateActionWarehouseRepository` preserves identical content as a no-op, appends changed knowledge revisions,
  selects revisions by cutoff and emits reciprocal quantity/price effects only for confirmed complete splits.
- Every generated effect cites its action revision through `control.lineage_edges`. Return readiness also requires a
  passing `held_instrument_date_range_coverage` result; no row is never silently interpreted as no action.
- Conservative KIS normalizers preserve domestic free-form merger ratios and overseas allocation ratios as unresolved
  rather than guessing their unit semantics.
- Focused migration, revision, coverage, unknown-term and restore fixtures: 8 passed. `bash scripts/check.sh quick`
  passed; `bash scripts/check.sh full` passed with 317 tests and the existing Authlib deprecation warning.
- No production source call, Scheduler, live MotherDuck migration or external send was performed.

## Closeout

- Result: closed; the governed repository-local corporate-action ledger, adjustment effect and recovery contract are
  complete.
- Remaining risk: production endpoint sampling, page limits, source coverage evidence, migration `0009` application
  and scheduling require their normal external/production approval gate. Until then readiness remains `not_assessed`.
- Follow-up Work Item: WI-022 may preserve missing coverage as an explicit reconstruction exception; production
  corporate-action activation must be tracked before any KIS source call.
