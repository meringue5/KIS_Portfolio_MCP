---
id: WI-067
title: Distinguish closed-market quiet windows from missing scheduled portfolio runs
status: verified
type: defect
owner: owner
decision_refs: DEC-031, DEC-032, DEC-038, DEC-057, ADR-029
requirement_refs: DGOV-007, DGOV-008
milestone_ref: MS-008
delivery_refs: none
parent_work_item: none
depends_on: WI-066
discovered_from: WI-066
supersedes: none
rollback_of: none
execution_scope: repository implementation and deterministic actual-tool-boundary fixtures verified; production release requires its normal gate
production_effects: none in the current phase
architecture_impact: none; reuse the governed KRX calendar inside the existing read adapter and preserve the service, warehouse and MCP boundaries
data_impact: no DDL or stored-row mutation; read_model.pipeline-run-v1 adds dataset.market-calendar as schedule evidence
security_impact: none; no new identifiers, credentials or raw provider payloads are exposed
cost_impact: one bounded calendar query per portfolio pipeline-status read
user_visible_impact: yes
real_use_acceptance: required
real_use_evidence_refs: deterministic MCP tool-boundary no-runs-expected positive, scheduled-run-missing partial and invalid-selector error passed; PR #149 initial CI run 38191885891 passed; post-release Codex and owner-Claude replay pending
stabilization_window: post-release immediate Codex and owner-Claude replay across a closed-only window and a window containing scheduled runs
stabilization_exit_refs: protected release evidence plus actual-client positive, partial and error behavior
rollback_plan: restore the prior Remote revision if current run visibility regresses; no data rollback is required because the change is read-only
---

# WI-067 — Distinguish closed-market quiet windows from missing scheduled portfolio runs

## Problem and evidence

On 2026-10-12, owner-Claude queried `get-pipeline-run` with a three-day lookback after the 2026-10-09 KRX holiday
and weekend. The read returned `runs: []`, freshness `unavailable`, quality `partial` and generic
`no_governed_rows`, even though no 10:00, 14:30 or 16:00 KST portfolio slot was scheduled in that window. A seven-day
query immediately returned nine successful runs from 2026-10-06 through 2026-10-08.

The active warehouse adapter currently classifies every empty wall-clock window as partial without consulting
`control.market_calendar` or the approved portfolio schedule. This makes expected market closure look like pipeline
or data failure and invites false incident diagnosis.

## Classification and contract

- Initial classification: user-visible read-model defect.
- Compared contract: `pipeline.owned-portfolio-core-v2` already requires the governed KR/US market calendar and fixes
  the Korean slots at 10:00, 14:30 and 16:00 KST. `read_model.pipeline-run-v1` currently forbids empty green results
  but does not distinguish calendar-proven no-run windows from missing scheduled evidence.
- Contract result: the implementation and read-model contract are incomplete. Empty results may be healthy only when
  governed calendar evidence proves that zero slots were due; missing expected slots must remain degraded.
- Approval: the owner explicitly approved separating and fixing this defect. Production release remains subject to
  the normal protected release gate.

## Scope

- Include: evaluate due Korean portfolio slots inside the requested wall-clock window using `control.market_calendar`
  and KST; exclude future same-day slots.
- Include: return explicit `no_runs_expected`, `scheduled_runs_missing` and `calendar_evidence_unavailable` states.
- Include: preserve observed run rows and existing quality-evidence checks.
- Exclude: calendar generation/synchronization changes, scheduler changes, historical row mutation, new sources,
  pipeline execution, Telegram behavior and reconstruction of past runs.

## Acceptance criteria

- [x] A closed-market-only empty window is freshness `available`, quality `pass`, has no missing coverage and reports
      zero expected runs with `window_status=no_runs_expected`.
- [x] An open-market window after one or more due slots with absent run evidence remains partial and names
      `scheduled_run_missing`.
- [x] Missing or incomplete calendar coverage remains partial/unavailable and names
      `calendar_evidence_unavailable`; it never becomes a false green.
- [x] Same-day slots later than the query cutoff are not counted as missing.
- [x] Existing successful/failed run and quality-evidence behavior remains compatible.
- [x] Focused, quick and full checks pass before release consideration.
- [ ] Actual Codex and owner-Claude calls reproduce the closed-window and scheduled-window behavior after release.

## Change impact

- Architecture: no boundary change; the existing outbound warehouse adapter reads an existing governed Control
  dataset.
- Data/schema/backup: no physical schema or backup change. The read-model manifest gains calendar input and explicit
  window fields.
- Security/privacy: owner-only aggregate operational evidence only; no account or secret fields.
- MCP/API compatibility: additive response fields under `data.window`; existing `data.runs` and query fields remain.
- Deployment/rollback: code-only Remote release after approval; revert traffic to the prior revision on regression.
- Cost/SLO: one small bounded calendar query covering at most 32 local dates.

## Plan

1. Add deterministic red fixtures for healthy closed windows, missing due slots, missing calendar evidence and future
   same-day slots.
2. Revise the governed read-model contract and implement calendar-aware status composition.
3. Run focused, governance, MCP surface, quick and full checks.
4. After protected release approval, execute immediate actual-client scenarios without waiting for a future slot.

## Sub-items

- `none`.

## Stabilization plan

- Observation period/sample: immediate closed-only and scheduled-window reads in Codex and owner-Claude after release.
- Signals: expected, observed and missing run counts; window status; freshness; quality; missing-coverage reason.
- Rollback trigger and safe state: any hidden real failure, false green, lost run row or MCP schema regression; restore
  the prior Remote revision.
- Exit evidence and owner acceptance: both actual clients distinguish expected quiet from missing scheduled work and
  the owner accepts the original three-day scenario.

## Real-use acceptance

- User-visible basis: yes; the result directly controls whether an LLM reports a pipeline incident.
- Actual approved clients/transports: authenticated Codex Remote MCP and owner-Claude custom connector.
- Immediate scenarios: closed-only empty window as positive; due slot without a run as partial; unavailable calendar
  as explicit diagnostic/error boundary; unaffected observed-run window.
- Findings: route implementation defects to WI-067 and independent transport/source defects to a new Work Item.

## Evidence

- Initial live evidence: three-day empty result was partial/unavailable, while seven days returned nine successful
  runs from 2026-10-06 through 2026-10-08.
- Code evidence: `_get_pipeline_run` used only `started_at` lookback and classified every empty result as partial.
- Red regression: four new warehouse tests failed on missing `data.window` before implementation.
- Focused tests: eight pipeline warehouse tests, then 73 combined warehouse and MCP surface tests passed.
- Governance and safety: data governance, architecture, warehouse, MCP surface, V2 documentation and 22
  orchestrator/order/account safety tests passed.
- `bash scripts/check.sh quick`: passed with the repository Python 3.13 and uv paths explicitly selected.
- `bash scripts/check.sh full`: 815 passed with one pre-existing Authlib deprecation warning.
- PR #149 initial CI run `38191885891`: passed on commit `860ee4d`.
- Production evidence: pending protected release and actual-client replay.

## Closeout

- Result: repository implementation and deterministic actual MCP tool-boundary verification complete; status
  `verified`, not deployed.
- Remaining risk: governed calendar completeness and production client interpretation must be verified.
- Follow-up Work Item: none at intake.
