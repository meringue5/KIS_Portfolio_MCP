---
id: WI-031
title: Baseline Milestones 3 and 4 and register newly approved work
status: closed
type: governance
owner: owner
decision_refs: pending DEC-047 and DEC-048
requirement_refs: GOV-003, GOV-004, GOV-006, GOV-008
milestone_ref: MS-GOV
delivery_refs: none
parent_work_item: none
depends_on: WI-018
architecture_impact: planning baseline only; product architecture is not implemented by this Work Item
data_impact: registers a metric contract but creates no production schema or data
security_impact: none; no credential or account data is handled
cost_impact: repository-local deterministic checks only
---

# WI-031 — Baseline Milestones 3 and 4 and register newly approved work

## Problem and evidence

The immutable registry currently stops at MS-002 even though the approved V2 delivery plan continues through Remote
MCP cutover and V1 retirement. The owner has now requested an explicit final Milestone 4 for consolidating V1
documentation into a V2 canonical set, and asked whether the previously deferred instrument-level total-asset daily
valuation-change contribution is fully represented in V2.

Live contract review shows that V2 contains a generic portfolio contribution direction and WI-023 covers
cash-flow-adjusted return attribution, but it does not define the requested KRW valuation-change decomposition,
snapshot completeness safeguards, cash/residual reconciliation or compatibility response contract.

## Classification and contract

- Classification: `governance` intake and baseline change.
- Compared contracts: approved V2 requirements, delivery plan, system design, milestone registry, metric catalog and
  current `get-total-asset-daily-change` implementation/tests.
- Contract result: both requests are approved additions. They require independent Work Items because each has its own
  acceptance and rollback boundary; neither redefines an existing WI.
- Approval: the owner's current request approves registration and requirements/design clarification, not product
  implementation or production change.

## Scope

- Include: define MS-003 and final MS-004, allocate WI-032 and WI-033, add exact requirement/design/data contracts,
  update MS-002 dependencies, traceability and deterministic milestone validation.
- Exclude: implement contribution calculations, alter the MCP runtime, migrate data, modify live MotherDuck, deploy,
  archive/delete V1 documents or change production traffic.

## Acceptance criteria

- [x] MS-003 and final MS-004 have stable identities, outcomes, readiness gates and dependency order.
- [x] V1 document consolidation has a dedicated M4 Work Item and V2 delivery item.
- [x] KRW valuation-change contribution has a separate Work Item from cash-flow-adjusted return contribution.
- [x] Requirements, metric contract, MCP/read-model design, milestone and Work Item all state completeness,
  reconciliation and overseas FX semantics consistently.
- [x] No existing Work Item ID or outcome is changed; any sequence change is recorded.
- [x] Project OS quick and full gates pass.

## Change impact

- Architecture: baseline and response-contract clarification only.
- Data/schema/backup: approved metric contract using governed V2 daily state; no physical change in this WI.
- Security/privacy: future V2 canonicalization must retain the existing secrets policy; no secret material here.
- MCP/API compatibility: plans a backward-compatible enrichment of the V1 daily-change response during transition and
  a V2 public read-model projection; no runtime change here.
- Deployment/rollback: repository-only; revert this baseline change before implementation if required.
- Cost/SLO: no runtime cost.

## Plan

1. Freeze MS-003/MS-004 identities and milestone dependency rules.
2. Allocate WI-032 for V2 documentation canonicalization and WI-033 for valuation-change contribution.
3. Add DEC, V2 delivery, metric and response-contract links without widening existing WI-023.
4. Extend deterministic checks and run Project OS gates.

## Sub-items

- `none`. The two owner requests have independent outcomes and therefore receive new Work Items.

## Evidence

- `governance/project/milestones.toml` defines MS-003 → MS-004 and preserves all existing WI identities while
  allocating WI-032/033 from the previous maximum WI-030.
- DEC-047/048, V2-W0510/W0807, the approved metric contract, V2 MCP read model and MS-002/004 documents form an
  inspectable requirement → design → milestone → Work Item chain.
- `uv run pytest -q tests/test_project_os_contract.py tests/test_data_governance_contract.py`: 10 passed.
- `bash scripts/check.sh quick`: passed; 72 governed contracts.
- `bash scripts/check.sh full`: 252 passed with one existing Authlib deprecation warning; all contract gates passed.
- Operating evidence: no production DB, cloud resource, deployment, MCP runtime or external message changed.

## Closeout

- Result: closed. Milestones 3/4 and both approved additions are in the immutable planning baseline.
- Remaining risk: WI-033 still requires implementation and live-quality verification; WI-032 cannot start before the
  MS-003 cutover evidence exists.
- Follow-up Work Items: WI-019 and WI-020 remain dependency-ready; WI-033 is also ready. Only one may become active.
