---
id: WI-024
title: Add typed thread risk plans and review state
status: closed
type: change
owner: owner
decision_refs: ADR-021, ADR-023, V2-ADR-006, V2-ADR-010, V2-ADR-012
requirement_refs: DEC-012..014, DEC-027, DEC-031, DEC-038, DEC-044
milestone_ref: MS-002
delivery_refs: V2-W0305, V2-W0306
parent_work_item: none
depends_on: WI-010, WI-022
architecture_impact: implements approved owner-authored risk-plan and review revisions
data_impact: typed stop/reference/risk-plan revisions and sell-allocation review state
security_impact: confidential investment intent remains internal and revision-audited
cost_impact: negligible database writes; no always-on service
---

# WI-024 — Add typed thread risk plans and review state

## Problem and evidence

Journal prose is not an authoritative stop price, and missing lot/thread or sell allocation intent needs an explicit
owner review workflow before risk metrics can claim completeness.

## Classification and contract

- `change` implementing approved DEC-027 and DEC-031.
- Owner revisions are authoritative; ATR-derived stops remain advice metadata.

## Scope

- Include typed risk-plan versions, optimistic revision, review queue and audit actor.
- Exclude public MCP write exposure and automatic order execution.

## Acceptance criteria

- [x] stop/reference/risk budget revisions are point-in-time and immutable.
- [x] unanswered review items remain explicit and do not invent intent.
- [x] concurrency, authorization boundary and restore tests pass.

## Change impact

- Additive Control/Silver state only; Remote MCP write adapter remains later work.

## Plan

1. Freeze typed plan and review contracts.
2. Add repository and revision tests.
3. Reconcile reconstructed threads without synthesizing owner intent.

## Sub-items

- `none`.

## Evidence

- Project OS, Data Governance Harness, Warehouse Contract and portfolio operations procedures reviewed. WI-010 and
  WI-022 are closed. Existing `silver.trade_threads`, `silver.trade_journal_revisions` and
  `silver.sell_allocations_current` preserve identity and reconstruction evidence, but no typed owner-authoritative
  stop/reference plan or shared append-only review queue exists.
- Two approved dataset contracts, migration `0011`, three backed append-only tables, two rebuild views, pure typed
  validation and an owner-authority/optimistic-concurrency repository are implemented. Journal/model prose is never
  parsed into a stop; system discovery opens questions only and owner resolution cites a separate authoritative
  revision.
- `5` focused and `28` adjacent migration/reconstruction/recovery tests pass. Complete V2 Parquet export and fresh
  restore retain plan and review revisions and rebuild both current views.
- Production read-only evidence found 19 open threads, 0 owner journal revisions, 0 sell-allocation sets and 57 open
  reconstruction exceptions. Migration `0011` and all five WI-024 objects remain unapplied, with 0 new owner-intent
  rows and no source calls or writes. See `docs/operations/wi024-thread-review-readiness-2026-08.md`.
- Full repository gate: `368` tests passed.

## Closeout

- Result: closed; typed plan and review contracts, local migration, repository and recovery are complete.
- Remaining risk: production migration/population and later MCP journal/write workflow remain separately gated; 57
  reconstruction exceptions and 19 missing owner plans are not silently resolved.
- Follow-up Work Item: WI-025.
