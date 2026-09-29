---
id: WI-065
title: Restore the Claude recent-asset-change MCP workflow on the current Remote revision
status: verified
type: incident
owner: owner
decision_refs: DEC-029, DEC-031, DEC-032, DEC-038, DEC-057, DEC-058, ADR-015, ADR-028, ADR-029, ADR-030
requirement_refs: DEC-029, DEC-031, DEC-032, DEC-038, DEC-057, DEC-058
milestone_ref: MS-008
delivery_refs: none
parent_work_item: none
depends_on: WI-063
discovered_from: WI-063
supersedes: none
rollback_of: none
execution_scope: repository implementation and production-equivalent Remote verification
production_effects: none
architecture_impact: none; repair the approved read contract and canonical Remote release path without changing tools scopes or trust boundaries
data_impact: read-only quality vocabulary normalization over existing append-only daily states; no schema write migration or source activation
security_impact: retain owner-debug redaction OAuth resource binding and exact Host validation
cost_impact: zero source calls and no standing resource change
user_visible_impact: yes
real_use_acceptance: required
real_use_evidence_refs: owner Claude asset-change session and redacted Cloud Run logs at 2026-09-29T23:19Z
---

# WI-065 — Restore the Claude recent-asset-change MCP workflow on the current Remote revision

## Problem and evidence

The owner asked Claude for recent asset changes. Claude successfully called portfolio overview, performance history
and data quality, but `get-pipeline-run` returned only `Error executing tool get-pipeline-run`. The same response
reported all 56 performance-history rows as `degraded` while the current overview rows were `pass`.

Redacted Cloud Run evidence proves that Claude called `get-pipeline-run` with neither `run_id` nor `pipeline_id`.
The request reached HTTP 200, then `PipelineRunRequest` raised a validation error before the shared owner-debug
boundary could return a useful result. The natural recent-status call therefore has no usable default.

The same requests reached the retained `wi046-v2` tagged URL on revision `00048` / SHA `13c0ce5`, while the stable
service serves revision `00056` at 100%. Revision `00048` treats only legacy `passed` daily-state rows as healthy;
current producers store canonical `pass`, so current history is falsely labelled degraded. Read-only MotherDuck
profiling found 58 pass and 29 degraded date-slot groups under the current master expression, with recent slots
mostly pass. Historical data also contains both `pass` and `passed`, so the read model must normalize both approved
success spellings rather than reverse which half is falsely degraded.

## Classification and contract

- Classification: production incident containing two public read defects and one release/configuration drift.
- Existing contract: a recent pipeline-status read returns bounded evidence; historical portfolio values expose their
  own quality honestly; Claude uses the canonical current Remote connection rather than an immutable candidate tag.
- Contract result: implementation and serving configuration are below the approved behavior. No new capability,
  provider, dataset, schema, scope or architecture decision is required.
- Authorization: the owner requested test-first remediation on 2026-09-30. Production traffic or connector mutation
  remains outside the current `production_effects: none` phase until the tested release is separately authorized.

## Scope

- Include an immediate Claude-profile transport regression for no-argument `get-pipeline-run`.
- Include a safe default to current `portfolio-refresh` evidence only when both selectors are omitted; explicit
  `run_id` and `pipeline_id` behavior remains unchanged.
- Include daily-state quality normalization for canonical `pass` and retained legacy `passed`, while any other status
  still suppresses an apparently complete total.
- Include a release regression that prevents the retained Claude compatibility tag from remaining on an older
  revision than the newly verified Remote release, or an explicit canonical-URL migration check with equivalent proof.
- Exclude data rewriting, history deletion, source calls, performance-return claims, cash-flow inference and WI-064
  trade-event deduplication.

## Acceptance criteria

- [x] The recorded Claude profile can call `get-pipeline-run` with `{}` and receive current portfolio-refresh evidence.
- [x] Explicit run and pipeline selectors retain their validation and alias behavior.
- [x] Mixed canonical `pass` and retained legacy `passed` rows remain usable; a genuinely degraded component still
      yields partial quality and suppresses the group total.
- [x] Release tests fail if the Claude compatibility route can remain pinned to an older Remote revision.
- [x] Focused, quick and full gates pass before any release request.
- [ ] Actual Claude positive, partial and error scenarios pass on the released current revision without waiting for a
      scheduled slot.

## Change impact

- Architecture: no boundary change; canonical Remote remains the product endpoint.
- Data/schema/backup: read-only normalization; no migration, write or backup change.
- Security/privacy: no new response fields or identifiers; existing redaction remains mandatory.
- MCP/API compatibility: additive no-argument default and correction of false quality labels.
- Deployment/rollback: current phase is repository-only. A later protected Remote release must record exact SHA,
  revision, image and stable/tag routing; rollback restores the prior stable revision without data changes.
- Cost/SLO: DB-only bounded reads; no source-call or instance-cost increase.

## Plan

1. Freeze the exact Claude no-argument tool call, mixed quality vocabulary and stale-tag release path as failing tests.
2. Implement the smallest adapter/read-model/release correction and rerun focused tests.
3. Run quick and full gates, then prepare a protected release handoff with immediate Claude/Codex replay.

## Sub-items

- `none`.

## Stabilization plan

- Observation: immediate Claude and Codex calls after an approved protected Remote release.
- Signals: serving revision/SHA, stable and compatibility route target, pipeline-run result, history quality distribution
  and unaffected overview/data-quality reads.
- Rollback: restore prior stable traffic revision; do not rewrite portfolio history.
- Exit: no generic tool error, quality labels reconcile to component status, and owner accepts the Claude result.

## Real-use acceptance

- Actual client/transport: owner-authenticated Claude custom connector and Codex OAuth Remote MCP.
- Positive: no-argument recent pipeline status and a current pass-quality history range.
- Partial: a fixture and governed date-slot containing a degraded component remains explicit and does not expose a
  complete total.
- Error: conflicting explicit `run_id` and `pipeline_id` returns a diagnosable owner-debug invalid request.

## Evidence

- Owner Claude report: three tools usable; `get-pipeline-run` generic error; 56 history rows shown as degraded.
- Cloud Run 2026-09-29T23:19Z: `Claude-User`, tagged `wi046-v2` request, HTTP 200 transport, Pydantic error because
  both selectors were absent, then MCP `UnexpectedToolError`.
- Cloud Run inventory: stable latest revision `00056` at 100%; `wi046-v2` remains on revision `00048`.
- MotherDuck read-only profile: 87 date-slot groups under the current expression, 58 pass and 29 degraded; recent
  current slots are predominantly pass, and retained historical rows contain both `pass` and `passed` vocabulary.
- Red/green regression: the exact no-selector unit/Claude profile, mixed success vocabulary and absent WI-065 release
  target produced five failures before implementation. The focused MCP/warehouse/deploy suite then passed 158 tests.
- Patched-code production read against MotherDuck, with no writes or source calls: no-selector pipeline status resolved
  `pipeline.owned-portfolio-core-v2`, returned nine rows and quality `pass`; 2026-07-24 through 2026-09-29 history
  returned 66 date-slot rows, of which 60 were pass and six genuinely degraded with six suppressed totals.
- Quick gate and full repository gate passed; the full suite now contains 799 tests. WI-065 deploy dry-run changes only
  the Remote image, stable latest traffic and `wi046-v2=LATEST` tag mapping.

## Closeout

- Result: repository implementation verified; protected production release and actual-client replay remain pending.
- Remaining risk: Claude continues to use an old tagged revision until an approved release/configuration correction.
- Follow-up Work Item: WI-064 remains independently proposed for trade-event business-key deduplication.
