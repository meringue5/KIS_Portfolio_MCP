---
id: WI-062
title: Remediate capability gaps found by direct Remote MCP use
status: stabilizing
type: defect
owner: owner
decision_refs: DEC-057, DEC-058, DEC-059, ADR-029, ADR-030, ADR-031
requirement_refs: DEC-057, DEC-058, DEC-059
milestone_ref: MS-008
delivery_refs: none
parent_work_item: none
depends_on: WI-061
discovered_from: WI-060, WI-061
supersedes: none
rollback_of: none
execution_scope: production-correction
production_effects: guarded Remote MCP deployment after verified implementation
architecture_impact: bounded additive response metadata and corrected payload projection; core remains MCP-independent
data_impact: read-only production investigation only; no schema, producer, source activation or backfill change
security_impact: preserve owner-only scope, redaction and account masking
cost_impact: no provider or standing-resource change
stabilization_window: protected Remote deployment plus immediate direct Codex OAuth positive partial and error replay
stabilization_exit_refs: immutable release workflow serving revision direct MCP outputs and owner acceptance
rollback_plan: restore the prior serving Remote revision if positive reads regress sensitive fields expand or response contracts fail
user_visible_impact: yes
real_use_acceptance: required
real_use_evidence_refs: PR #135, deploy run 35868121973, Remote revision kis-portfolio-remote-00054-fh9, Codex OAuth thread 01a0ce7e-82d1-7c82-8b53-964060843fd3
---

# WI-062 — Remediate capability gaps found by direct Remote MCP use

## Problem and evidence

The 2026-09-23 direct Codex OAuth MCP suite called ten tools exactly once. Six were usable, performance and exposure
were explicitly degraded, and trade ledger plus fundamental outlook had no governed rows. The overview returned all
position rows despite `include_holdings=false`, and pipeline alias resolution was not explained in the response.

## Classification and contract

- Defect: `include_holdings=false` filters only aggregate level `instrument`, while production holdings are `position`.
- Clarification/compatible response change: `portfolio-refresh` resolves correctly but the response omits requested
  and resolved identity.
- Data/operations defect: the current trade ledger stops on 2026-08-25, its one-time backfill watermark stops on
  2026-08-28, and the recurring core implementation does not collect trade events despite the catalog output claim.
  WI-063 owns the incremental producer correction.
- Approved-inactive scope: fundamental, macro and ETF look-through contracts must not be fabricated or activated as
  an incidental bug fix.
- Accurate behavior: degraded performance rows remain partial and must not be coerced to pass.

## Scope

- Include: immediate deterministic reproduction, overview option correction, alias transparency and live replay.
- Include: trace trade-event producer/run/watermark evidence and either repair the approved pipeline or publish an
  exact owned unavailable reason and follow-up.
- Include: make inactive/missing capability boundaries honest and useful without false success.
- Exclude: unapproved provider activation, arbitrary backfill, fabricated fundamentals or ETF constituents.

## Acceptance criteria

- [x] `include_holdings=false` returns summary without position rows and reduces response size.
- [x] Pipeline alias responses explain requested and canonical identity without weakening exact filtering.
- [x] Trade ledger absence has a verified producer/run/root-cause disposition, an immediate regression case and an
  owned incremental correction in WI-063.
- [x] Fundamental, macro and ETF gaps are either separately approved for activation or explicitly represented as
  unsupported/inactive rather than appearing as mysteriously broken features.
- [x] Actual Codex OAuth MCP positive, partial and error scenarios pass after deployment.

## Change impact

- Architecture: DEC-059/ADR-031 approve bounded additive query metadata and payload/quality separation; core remains
  MCP-independent.
- Data/schema/backup: production inspection proved 282 governed trade rows but no September coverage; WI-062 only
  corrects the response and performs no schema, write, backfill or backup change. WI-063 owns collection restoration.
- Security/privacy: fewer holdings returned when excluded; no secret or account expansion.
- MCP/API compatibility: additive alias metadata and correction of an ignored boolean option.
- Deployment/rollback: production Remote change requires protected workflow and prior serving revision.
- Cost/SLO: no new provider or standing resource without a separate approved contract.

## Plan

1. Freeze direct-call fixtures for every finding.
2. Correct immediate read-model defects.
3. Inspect trade-event run, watermark and producer evidence before changing data. Completed read-only; no data
   mutation was necessary.
4. Separate inactive feature activation from defects and obtain approval where required.
5. Run full gate, protected deployment and direct Codex replay.

## Sub-items

- To be appended after WI-061 closes and the investigation separates independent outcomes.

## Stabilization plan

- Observation: immediate direct Codex replay plus at least one current governed portfolio state; no future slot is the
  sole test.
- Signals: transport result, envelope quality, missing coverage, response bounds and client-visible usefulness.
- Rollback: restore the prior serving Remote revision if positive reads regress or sensitive fields expand.
- Exit: owner accepts the direct-call result; source activation work, if any, remains separately gated.

## Real-use acceptance

- User-visible: yes; this Work Item changes public Remote MCP response behavior and usefulness.
- Client/transport: owner-authenticated Codex over the canonical OAuth Streamable HTTP `/mcp` endpoint.
- Immediate scenarios: portfolio summary without holdings, pipeline alias projection, trade-ledger unavailable/usable
  boundary, accurate partial performance/exposure and diagnostic error response.
- Initial evidence: 2026-09-23 ten-tool direct suite. Post-change evidence: PR #135, deploy run `35868121973`, Remote
  revision `kis-portfolio-remote-00054-fh9` and Codex OAuth thread `01a0ce7e-82d1-7c82-8b53-964060843fd3`.

## Evidence

- Initial direct MCP results are summarized in the problem statement; exact request IDs remain in operational logs.
- Production MotherDuck read-only aggregate on 2026-09-23: 282 `trade_events_current` rows from 2025-09-24 through
  2026-08-25; eleven backfill watermarks end no later than 2026-08-28; 54 succeeded and 3 historical failed core runs;
  latest core run succeeded at the 16:00 slot but its implementation has no trade collection stage.
- Deterministic regression set: holdings suppression, pipeline alias disclosure, covered empty trade window, uncovered
  trade window,
  fundamental approved-inactive and macro approved-inactive; five focused tests pass.
- Shared quick gate passes: Project OS, data governance, architecture, warehouse, MCP surface and V2 documentation.
- Final repository gate before release: 786 passed with one pre-existing Authlib deprecation warning.
- PR #135 merged as `2305c32`; production workflow `35868121973` deployed only Remote revision
  `kis-portfolio-remote-00054-fh9`, serving 100%. Labels match Git SHA, run ID, target `remote` and source
  `github-actions`; health returned 200 and unauthenticated `/mcp` returned 401.
- Direct Codex OAuth replay called six tools once each without retry: overview `pass/32` with zero positions and a
  present summary; pipeline alias `pass/3` with requested/resolved metadata; trade ledger `partial/0` with
  `collection_watermark_before_query_end`; exposure `partial/26` with approved-inactive macro and unsupported ETF;
  fundamental `partial/0` with both inputs approved-inactive; deliberate market snapshot failure exposed
  `unknown_instrument_reference`, `RemoteReadError`, owner-debug visibility and a request ID in the raw MCP result.
- The Codex summarizer emitted null diagnostic fields for the deliberate error even though its immediately preceding
  raw MCP result contained all four fields. Acceptance uses the raw transport result, not the lossy summary.

## Closeout

- Result: stabilizing after protected deployment and direct Codex replay; owner acceptance remains before closeout.
- Remaining risk: public tools can remain technically callable but not useful.
- Follow-up Work Item: WI-063.
