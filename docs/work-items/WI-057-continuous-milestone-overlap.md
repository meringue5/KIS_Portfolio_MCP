---
id: WI-057
title: Make milestone overlap continuous and phase-aware
status: closed
type: governance
owner: maintainer
decision_refs: ADR-022
requirement_refs: GOV-004..012
milestone_ref: MS-GOV
delivery_refs: none
parent_work_item: none
depends_on: WI-056
discovered_from: WI-056
supersedes: none
rollback_of: none
execution_scope: isolated
production_effects: none
architecture_impact: Project OS milestone execution and production gate semantics only
data_impact: no data contract, schema, migration or production row mutation
security_impact: no credential, permission or trust-boundary change
cost_impact: repository-local governance and tests only
---

# WI-057 — Make milestone overlap continuous and phase-aware

## Problem and evidence

WI-056 introduced stabilization and separate implementation/production gates, but the MS-003 baseline reduced
continuous successor progress to a fixed two-item exception for WI-035 and WI-040. After both were verified, the
registry and a negative fixture incorrectly required MS-002 closure before WI-037 implementation even though the
owner intended MS-002 stabilization and MS-003 implementation verification to proceed together.

## Classification and contract

- Classification: `governance` correction discovered from WI-056.
- Preserve the approved WIP limit, dependency DAG, append-only recovery loop and production-effect gate.
- Correct implementation progression so predecessor closure is not a condition for successor repository work.

## Scope

- Include continuous phase-aware overlap policy, MS-003 rebaseline, future MS-004 implementation gate, checker,
  tests, Skill, AGENTS summary, milestone graph and traceability.
- Exclude MS-003 product implementation, migration, source calls or activation, infrastructure, public MCP and
  cutover.

## Acceptance criteria

- [ ] a successor milestone may be `in_progress` while its predecessor is `stabilizing`.
- [ ] eligible successor Work Items progress one at a time through isolated implementation and `verified`.
- [ ] active Work Item dependencies are at least `verified`, while production effects still require the production
  gate.
- [ ] the same continuous overlap model applies to future milestone boundaries.
- [ ] quick/full gates and positive/negative fixtures pass.

## Change impact

- Product architecture/data/security/deployment: none.
- Governance: corrects current-phase metadata and executable milestone gates without rewriting WI-056 history.

## Plan

1. Clarify continuous and phase-aware overlap semantics. 2. Rebaseline registries and graphs. 3. Harden checker and
fixtures. 4. Verify and close. 5. Activate WI-037 under the corrected gate.

## Sub-items

- `none`.

## Evidence

- `uv run pytest tests/test_project_os_contract.py -q`: 21 passed, including positive WI-037 overlap and negative
  dependency, cutover and pre-gate production-effect fixtures.
- `bash scripts/check.sh quick`: passed with 58 tracked Work Items, one active Work Item and 162 Data Governance
  contracts before closeout.
- `bash scripts/check.sh full`: 521 passed with all Project OS, Data Governance, Architecture, Warehouse and MCP
  surface contracts passing.
- Commit `ae2fca5` contains the policy, registry, checker, Skill, agent context, milestone and traceability correction.

## Closeout

- Result: closed. MS-003 is now `in_progress` under continuous dependency-ordered isolated overlap; the checker
  permits WI-037 and preserves the MS-002 `closed` production gate and WI-046 cutover exclusion.
- Remaining risk: actual production migration, live source activation, infrastructure/public surface changes and
  cutover remain unavailable until the predecessor production gate opens.
- Follow-up Work Item: WI-037.
