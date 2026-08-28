---
id: WI-018
title: Establish immutable milestone and Work Item control
status: closed
type: governance
owner: owner
decision_refs: ADR-022
requirement_refs: GOV-003, GOV-004, GOV-006, GOV-008
milestone_ref: MS-GOV
delivery_refs: none
parent_work_item: none
depends_on: none
architecture_impact: none; strengthens the Project OS control plane without changing product architecture
data_impact: none; no product dataset, schema or production row changes
security_impact: none; governance metadata contains no credentials or account facts
cost_impact: repository-local deterministic checks only
---

# WI-018 — Establish immutable milestone and Work Item control

## Problem and evidence

Milestone 2 work was correctly re-sequenced by production data readiness, but the approved milestone assignment was
not preserved in a canonical registry. Sequentially issuing `WI-015`, `WI-016` and `WI-017` therefore made execution
order look like mutable identity. `WI-017` is now a completed ETF routing record and must remain unchanged; unfinished
milestone work must move to newly allocated IDs instead of shifting or reusing an existing index.

The current checker validates frontmatter, one active implementation and traceability presence, but it does not bind
requirements, design delivery IDs, milestones and Work Item identities or model discovered sub-items.

## Classification and contract

- Classification: `governance` defect in Project OS planning and traceability controls.
- Approved requirements, V2 design and completed `WI-013` through `WI-017` do not change.
- Existing Work Item IDs are permanent records. Planning order is represented separately from identity.
- User-approved rule: newly discovered scope never renumbers an existing Work Item; it becomes an appended sub-item
  when it stays within the parent's outcome, or a newly allocated Work Item when independently acceptable.

## Scope

- Include: canonical milestone registry, Milestone 2 baseline and remaining-work inventory, Work Item relationship
  fields, append-only identity rules, deterministic checks and regression tests.
- Include sub-item `WI-018-S01`: verify delivery-plan item uniqueness and enforce it in the checker.
- Exclude: product code, database, cloud resources, source calls, backfill, deployment and Telegram transmission.

## Acceptance criteria

- [x] completed `WI-013` through `WI-017`, especially ETF routing `WI-017`, retain their IDs and outcomes.
- [x] Milestone 2 has an explicit baseline containing completed and remaining Work Items with dependencies and design refs.
- [x] execution order can change without changing a Work Item ID.
- [x] an in-scope discovery can be appended as a stable sub-item; independent scope receives the next unused WI ID.
- [x] checker rejects duplicate registry IDs, dangling refs, mismatched Work Item identity and invalid sub-item ownership.
- [x] requirements → design → milestone → Work Item → evidence remains inspectable from canonical documents.
- [x] Project OS quick and full gates pass.

## Change impact

- Architecture: Project OS control metadata and checks only; no Product System boundary changes.
- Data/schema/backup: none.
- Security/privacy: no secret or confidential operational data.
- MCP/API compatibility: none.
- Deployment/rollback: repository-only; revert this change set if the registry proves unusable.
- Cost/SLO: no runtime cost.

## Plan

1. Freeze the identity and discovery rules in Project OS policy.
2. Add a machine-readable milestone registry and a human-readable Milestone 2 baseline.
3. Allocate new IDs to remaining work without modifying completed Work Item identities.
4. Extend the Work Item template and checker, then add negative regression tests.
5. Run quick/full gates and record remaining Milestone 2 boundaries.

## Sub-items

- `WI-018-S01`: verify delivery-plan item IDs are unique and add a deterministic uniqueness check.

## Evidence

- `governance/project/milestones.toml` binds MS-001, MS-002 and MS-GOV to stable Work Item identities, design refs,
  dependencies, sequence and sub-items.
- `docs/milestones/MS-002-portfolio-analytics-alerting.md` freezes completed WI-013~017 and allocates remaining work
  as WI-019~030 without changing an existing ID.
- `WI-018-S01` verified delivery-plan IDs are unique and added a deterministic duplicate-ID check.
- `uv run pytest -q tests/test_project_os_contract.py`: 5 passed, including identity drift, dangling sub-item and
  duplicate delivery-ID negative tests.
- `bash scripts/check.sh quick`: passed.
- `bash scripts/check.sh full`: 251 passed with one existing Authlib deprecation warning; all contract gates passed.

## Closeout

- Result: closed. Immutable Work Item allocation, milestone baseline and sub-item controls are active.
- Remaining risk: a coordinated edit can still change registry and Work Item together; policy, review history and
  milestone revision log remain the human approval layer over deterministic consistency checks.
- Follow-up Work Item: WI-019 and WI-020 are dependency-ready; only one may become `in_progress` at a time.
