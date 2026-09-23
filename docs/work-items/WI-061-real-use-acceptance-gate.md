---
id: WI-061
title: Require real-use acceptance for user-visible completion
status: closed
type: governance
owner: owner
decision_refs: GOV-013
requirement_refs: GOV-013
milestone_ref: MS-008
delivery_refs: none
parent_work_item: none
depends_on: none
discovered_from: WI-060
supersedes: none
rollback_of: none
execution_scope: repository
production_effects: none
architecture_impact: none; the change governs acceptance evidence without changing product boundaries
data_impact: none
security_impact: real-use evidence remains aggregate and redacted
cost_impact: bounded owner test calls only; no standing resource
user_visible_impact: no
real_use_acceptance: not_applicable
real_use_evidence_refs: not_applicable
---

# WI-061 — Require real-use acceptance for user-visible completion

## Problem and evidence

PR, CI and Cloud Run success previously allowed conversation to drift toward completion before the actual Codex MCP
client had exercised useful owner scenarios. On 2026-09-23 a direct ten-call suite found a ignored
`include_holdings=false` option, an unexplained pipeline alias resolution, two accurately degraded capabilities and
two public tools with no governed rows. None was visible from deployment success alone.

## Classification and contract

- Initial classification: governance.
- Compared contract: Project OS sections 2, 6, 8, 10 and 11.
- Contract gap: live evidence is required in principle, but no explicit machine-readable real-use acceptance field
  prevents a user-visible Work Item from closing on code/deploy evidence alone.
- Approval: the owner explicitly confirmed that redefining completion means revising Project OS and that findings
  must be acted on.

## Scope

- Include: policy, Work Item template, PR review prompt, checker and fixtures for real-use acceptance classification.
- Include: deterministic positive, partial and error scenarios through the actual client/transport when a Work Item
  changes user-visible behavior.
- Exclude: requiring a future clock slot when an immediate fixture or direct call can reproduce the outcome.
- Exclude: automatically activating providers, sending messages, exposing secrets or treating every data gap as a bug.

## Acceptance criteria

- [x] New Work Items declare whether they affect a user-visible surface and whether real-use acceptance is required.
- [x] A required real-use Work Item cannot close with pending or absent evidence references.
- [x] Project OS distinguishes automated tests, deployment smoke and user-value acceptance.
- [x] WI-062 dogfoods the new fields and owns every finding from the direct MCP suite.
- [x] Project OS quick and full gates pass.

## Change impact

- Architecture: none; governance-only acceptance contract.
- Data/schema/backup: none.
- Security/privacy: evidence must exclude credentials, raw tokens, full account identifiers and unnecessary holdings.
- MCP/API compatibility: none in WI-061.
- Deployment/rollback: no deployment; revert the policy/checker change if it blocks valid historical records.
- Cost/SLO: only bounded test calls authorized by the applicable Work Item.

## Plan

1. Add GOV-013 and the real-use evidence policy.
2. Extend new Work Item metadata and deterministic checks without rewriting historical closed records.
3. Update the template and PR review contract.
4. Apply the fields to WI-062 and run quick/full gates.

## Sub-items

- `none`.

## Stabilization plan

- Not applicable; repository-only governance work closes after deterministic checks and WI-062 dogfood.

## Real-use acceptance

- Not applicable to WI-061 itself because it changes repository governance rather than a user-facing product result.
- Dogfood target: WI-062 declares `user_visible_impact: yes`, requires actual Codex OAuth MCP evidence and cannot close
  while its evidence reference is pending.

## Evidence

- Direct Codex OAuth MCP suite on 2026-09-23: ten distinct tools called without retries or scheduler waiting.
- The suite found six usable, two degraded-but-usable and two unavailable capabilities plus one response-option defect.
- Project OS checker regression: 23 passed. Shared quick gate passed with 18 public tools unchanged. Full repository
  gate: 783 passed with one pre-existing Authlib deprecation warning.

## Closeout

- Result: closed; policy, template, PR prompt and deterministic checker now enforce the new completion contract for
  WI-061 and later Work Items while grandfathering immutable historical records.
- Remaining risk: real-use evidence is necessarily external to static CI; concrete refs and owner acceptance remain
  review evidence rather than something CI can manufacture.
- Follow-up Work Item: WI-062.
