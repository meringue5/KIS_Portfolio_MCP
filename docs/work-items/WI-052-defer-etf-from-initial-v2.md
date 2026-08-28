---
id: WI-052
title: Defer ETF constituent collection and look-through from initial V2 acceptance
status: closed
type: governance
owner: owner
decision_refs: ADR-024
requirement_refs: DEC-049, GOV-003, GOV-004, GOV-007, DGOV-003, DGOV-004
milestone_ref: MS-GOV
delivery_refs: none
parent_work_item: none
depends_on: WI-034
architecture_impact: revises initial V2 scope and the alert dependency graph without deleting future ETF contracts
data_impact: moves the ETF collection basket and pipeline to later; no schema or data mutation
security_impact: no credentials, account identifiers, provider calls or external messages
cost_impact: removes unapproved ETF provider cost from the initial V2 release
---

# WI-052 — Defer ETF constituent collection and look-through from initial V2 acceptance

## Problem and evidence

WI-026 established that no current source grants the required production rights for complete ETF composition. KIS is
an authorized cross-check but returns partial composition. The owner chose option 3: exclude ETF look-through from the
initial V2 release while continuing independent source research later.

## Classification and contract

- `governance` plus approved product-scope `change`.
- DEC-018/019 remain historical requirements for a future ETF capability; DEC-049 supersedes their inclusion in the
  initial V2 acceptance boundary.
- Existing WI IDs, source reviews, fixture parsers, routes and physical objects are preserved.

## Scope

- Include DEC/ADR, DGH collection/pipeline lifecycle, WI status, MS-002 outcome/acceptance and dependency revision.
- Exclude provider activation, source calls, data writes, schema changes and deletion of ETF fixtures or history.

## Acceptance criteria

- [x] WI-026/027 and provider sub-items retain identity and evidence but are rejected from the initial V2 path.
- [x] ETF collection is `later`, has no initial V2 schedule or production trigger, and remains fail-closed.
- [x] WI-028 no longer depends on WI-027 and still treats ETF holdings as opaque securities without fabricated
  constituent exposure.
- [x] milestone revision, requirements, ADR, delivery plan, traceability and machine registry agree.
- [x] quick/full Project OS and DGH gates pass.

## Change impact

- Architecture: initial V2 no longer promises ETF constituent collection or nested look-through.
- Data/schema/backup: existing dormant objects and fixture data remain; no migration, publish or deletion.
- Security/privacy: unchanged.
- MCP/API compatibility: exposure responses must report ETF look-through as unsupported/missing coverage in initial V2.
- Deployment/rollback: repository-only contract revision; future reintroduction uses a new approved Work Item.
- Cost/SLO: no ETF provider or collector cost/SLO in initial V2.

## Plan

1. Record DEC-049/ADR-024 and DGH version revisions.
2. Reject initial-scope WI-026/027 while preserving evidence and update MS-002 dependencies.
3. Run governance/full gates and close before activating WI-028.

## Sub-items

- `none`.

## Evidence

- User decision: option 3, ETF analysis excluded from initial V2 while further source research continues.
- Contract artifacts: DEC-049, ADR-024, collection/dataset/pipeline v1.1.0, MS-002 revision 2026-08-28.5,
  rejected WI-026/027 and revised WI-028 dependency.
- Commands/tests: 14 focused Project OS/DGH tests and quick/full shared gates pass.
- Operating evidence: repository-only change; zero provider calls, data writes, schedules, secrets, infrastructure or
  external messages.

## Closeout

- Result: closed; ETF no longer blocks the initial V2 delivery path and remains explicitly unsupported rather than
  approximated.
- Remaining risk: ETF holdings remain opaque for company/sector/country/currency look-through.
- Follow-up Work Item: WI-028; a future ETF reintroduction must receive a new Work Item and rights-approved source.
