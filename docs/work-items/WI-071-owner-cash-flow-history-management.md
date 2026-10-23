---
id: WI-071
title: Reconcile cash balances with trade settlement and surface unexplained movements
status: verified
type: change
owner: owner
decision_refs: DEC-013, DEC-023, DEC-063, ADR-026, ADR-032, ADR-034
requirement_refs: owner design 2026-10-14, isolated implementation and production transition authorization 2026-10-23
milestone_ref: MS-008
delivery_refs: none
parent_work_item: none
depends_on: WI-010, WI-042
discovered_from: WI-068
supersedes: none
rollback_of: none
work_lane: delivery
execution_scope: production transition
production_effects: additive Control evidence migration, stored-input batch evaluation and existing authenticated data-quality projection
architecture_impact: ADR-034 additive noncanonical Control evidence; no change to monetary SSOT or OAuth scopes
data_impact: append-only diagnostic revisions; production numeric support remains disabled
security_impact: aliases and opaque lineage only; no raw payload, credential or URI in output or logs
cost_impact: existing runtime/cadence and database; zero additional broker calls or Scheduler
user_visible_impact: yes
real_use_acceptance: required
real_use_evidence_refs: production OAuth positive/partial/error replay pending release
stabilization_window: immediate OAuth replay and next successful owned-portfolio batch slot
stabilization_exit_refs: six-scope deferred read, replay no-op, failed/absent source handling, unchanged money/report behavior and owner acceptance
rollback_plan: disable KIS_CASH_RECONCILIATION_ENABLED and restore exact prior Job/Remote definitions; retain additive schema and evidence
---

# WI-071 — cash reconciliation

## Problem and evidence

Domestic normalized cash is a valuation residual, and foreign cash mixes deposit/withdrawable fields. Existing
source-date trade coverage and date-only settlement do not prove actual cash posting. A reconciled residual can
never prove complete external flows or permit performance computation. Stored-source audit and isolated
implementation established these boundaries before this production transition.

## Classification and contract

Existing independent change discovered from WI-068; issued identity/dependencies preserved. Owner authorized
design on 2026-10-14, isolated implementation on 2026-10-23, then explicitly requested production transition.
DEC-063/ADR-034 own the bounded production decision: deferred-only stored-input diagnosis is useful now;
numeric enablement requires separately verified account/currency source evidence. No preceding closed outcome
is reopened. Original shared-checkout work and unrelated WI-072 artifacts remain preserved.

## Scope and acceptance

- Add immutable Control evidence with input/formula hash, interval revision and knowledge/recording clocks.
- Reuse successful owned-portfolio cadence, isolate evaluator failures, no provider calls or new Scheduler.
- Reuse authenticated get-data-quality with exact reconciliation dataset and a typed allowlist; no new tool/scope.
- Preserve existing cash/trade/valuation/performance/report behavior. Numeric production writes prohibited.
- Verify append/replay/concurrency, source/fee/cutoff boundaries, migration and fresh backup/restore.
- Verify actual OAuth positive/partial/error immediately after protected release, preserving source limitations.

## Stabilization plan

Observe immediate actual-client reads and the next successful scheduled producer. Missing/stale/basis/posting
inputs remain deferred. Producer failure cannot fail portfolio refresh/report delivery. On source mutation,
privacy leak or false monetary/coverage pass, disable the feature and restore exact prior runtime definitions;
retain immutable source and diagnostic evidence. Close only after the declared evidence and owner acceptance.

## Real-use acceptance

Positive is an authenticated useful diagnostic read with six currently deferred scopes; numeric positive remains
unsupported. Partial covers pre-activation/missing results or unavailable source. Error covers invalid limits,
cursors and unauthorized access using the same existing owner OAuth transport. Synthetic numeric fixtures must
not be inserted into the production evidence table to manufacture a positive acceptance.

## Evidence and closeout

Isolated phase: 43 new tests, 928 shared-checkout full tests, synthetic internal positive/partial/error and six
stored-source deferred results; these are historical isolated evidence, not production OAuth acceptance.
Current release/testing/provenance is recorded in docs/operations/wi-071-production-transition.md. No closeout
claim is made until the production gates and owner acceptance are satisfied.

## Acceptance criteria

- Durable replay no-op and append-only revisions; old-cutoff reads preserve knowledge/recording boundaries.
- Deferred-only storage constraints and actual-source gaps cannot produce money or performance pass.
- Existing cadence and OAuth route tested; authoritative data fingerprints and fresh restore verified.
- Protected release provenance, actual-client positive/partial/error and owner acceptance before closure.

## Change impact

ADR-034/DEC-063 add diagnostic Control storage and typed existing-tool read; no monetary SSOT/scope change.
Private backup includes the additive object; rollback preserves schema/evidence and restores runtime definitions.

## Plan

Complete repository contracts/code/tests; protected migration and bootstrap; update three existing Job images
and both Remote routes from one digest; immediate actual-client replay, then bounded scheduled stabilization.

## Sub-items

None; continue the existing WI-071 outcome and immutable identity.

## Closeout

In progress; implementation, release provenance and actual acceptance are tracked in the production runbook.
No completion is inferred from synthetic tests, deployment health or a deferred result alone.
