---
id: WI-053
title: Publish the human-readable Work Item dependency map
status: closed
type: governance
owner: maintainer
decision_refs: ADR-022
requirement_refs: GOV-003, GOV-004, GOV-006, GOV-008
milestone_ref: MS-GOV
delivery_refs: none
parent_work_item: none
depends_on: WI-052
architecture_impact: none; human-readable projection of the canonical milestone registry
data_impact: no schema, contract or row mutation
security_impact: no credentials, account data or external messages
cost_impact: repository-local documentation only
---

# WI-053 — Publish the human-readable Work Item dependency map

## Problem and evidence

The immutable milestone registry contains the Work Item order, but a maintainer reading individual files under
`docs/work-items/` cannot easily see the whole delivery path, the current position or the formal milestone start gates.
The existing upper-level design and delivery plan also did not link to one human-readable dependency view.

## Classification and contract

- Classification: `governance` documentation maintenance.
- `governance/project/milestones.toml` remains the machine-readable SSOT; the graph is a review projection only.
- Work Item identities, dependencies, milestone states and product contracts must not change as a side effect of drawing
  the graph.

## Scope

- Add an upper-design document map and Mermaid views for milestones, completed foundations and remaining Work Items.
- Explain the current `MS-002 → MS-003` formal start gate and distinguish read-only preparation from implementation.
- Link the V2 delivery plan back to the human-readable dependency view.
- Exclude runtime implementation, source calls, data writes, infrastructure changes and early MS-003 authorization.

## Acceptance criteria

- [x] The human view links the upper system design, delivery plan, milestone documents, registry and traceability.
- [x] Every displayed Work Item relationship agrees with the milestone registry.
- [x] The current `WI-029-S05` path and the remaining MS-002, MS-003 and MS-004 path are visible in Markdown.
- [x] The document states what may proceed while shadow evidence accumulates without weakening the formal gate.
- [x] Project OS quick/full shared gates pass.

## Change impact

- Architecture: none; approved architecture is navigated, not revised.
- Data/schema/backup: none.
- Security/privacy: none.
- MCP/API compatibility: none.
- Deployment/rollback: repository-only documentation change.
- Cost/SLO: none.

## Plan

1. Compare the current milestone registry, milestone documents, delivery plan and Work Item states.
2. Publish a compact human-readable map with explicit arrow semantics and SSOT precedence.
3. Add traceability and run repository gates.

## Sub-items

- `none`.

## Evidence

- Registry relationships were manually compared with all rendered graph edges; no existing product dependency changed.
- `bash scripts/check.sh quick`: passed; 54 tracked Work Items and one active implementation Work Item.
- `bash scripts/check.sh full`: 418 passed with one third-party Authlib deprecation warning.
- Operating evidence: documentation/governance only; zero runtime, data, infrastructure or external-message mutation.

## Closeout

- Result: closed; maintainers now have one Markdown entry point for the upper design, current position and remaining path.
- Remaining risk: the graph is a human projection and can drift; the registry wins on conflict, and milestone changes must
  update both artifacts in one change set.
- Follow-up Work Item: none. Any request to implement MS-003 before MS-002 closes requires a separate governance change.
