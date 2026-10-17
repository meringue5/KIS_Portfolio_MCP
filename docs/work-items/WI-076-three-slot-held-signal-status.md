---
id: WI-076
title: Deliver held-position signal status at all three governed slots
status: stabilizing
type: defect
owner: owner
decision_refs: DEC-006, DEC-053, DEC-061, DEC-063
requirement_refs: owner clarification 2026-10-17; 10:00, 14:30 and 16:00 minimum receipt
milestone_ref: MS-006
delivery_refs: none
parent_work_item: none
depends_on: WI-070
discovered_from: WI-070, WI-030
supersedes: none
rollback_of: none
work_lane: stabilization_recovery
execution_scope: approved implementation and protected production release
production_effects: add one consolidated held-signal status Telegram operation to each existing owned-core slot
architecture_impact: none; reuse the modular-monolith Job, existing alert candidates, Telegram adapter and pipeline evidence ledger
data_impact: extend the approved Telegram delivery pipeline contract; no DDL, row rewrite or new financial dataset
security_impact: owner-only destination; report contains redacted instrument labels and relative signal values only
cost_impact: at most one additional Telegram operation per governed slot and three per applicable day; no new KIS calls
user_visible_impact: yes
real_use_acceptance: required
real_use_evidence_refs: deterministic positive/no-change/partial/error scenarios; finance-free transport smoke kis-portfolio-wi030-s03-snbfr; next applicable 10:00, 14:30 and 16:00 owner receipts pending
stabilization_window: protected release plus immediate actual positive/no-change/error scenarios and the next three governed slots
stabilization_exit_refs: one terminal report per date-slot, current active-signal count, no duplicate detail alerts, provider outcome and owner receipt
rollback_plan: disable only KIS_TELEGRAM_SIGNAL_SLOT_REPORT_ENABLED or restore the prior three-Job image; preserve candidates, detail delivery and report evidence
---

# WI-076 — Deliver held-position signal status at all three governed slots

## Problem and evidence

Production evaluates held positions at 10:00, 14:30 and 16:00, but Telegram sends only delivery-required state
transitions. On 2026-10-16 the morning run sent transitions while the later two runs evaluated candidates with zero
transitions and therefore sent nothing. The owner intended the three times as a minimum receipt cadence when true
event-time monitoring is unavailable, not merely an internal evaluation cadence.

## Classification and contract

- Classification: clarification-backed stabilization defect. The scheduler is healthy and transition-only detail
  delivery behaves as implemented, but it does not satisfy the owner's original minimum three-receipt intent.
- DEC-063 owns the clarified result: one consolidated report at every governed slot while detailed transition alerts
  retain their existing de-duplication.
- No architecture change: compose the report after evaluation and detail delivery in the existing Job.

## Scope

- Include: one date-slot report, active watch-or-higher signals, new/escalated/recovered count, explicit zero-change
  result, bounded rendering, provider-outcome evidence and independent feature flag.
- Include: 10:00 U.S.-close scope only; 14:30/16:00 must not repeat the same U.S. session.
- Exclude: unheld watchlists, threshold changes, real-time polling/streaming, new provider, detailed-alert replay and
  historical missed-slot sends.

## Acceptance criteria

- [x] Each 10:00, 14:30 and 16:00 run attempts exactly one consolidated report when enabled.
- [x] A zero-transition slot still says `신규 변화 0건` and lists current active pass-quality signals.
- [x] Existing detailed transition delivery remains once-only and is not repeated by the consolidated report.
- [x] Same date-slot replay does not send again; interrupted/ambiguous send becomes terminal unknown.
- [x] Disabled, unsafe or missing evaluation evidence fails before a provider request.
- [x] Protected one-image release preserves total-asset reporting and all three Jobs.
- [ ] Actual private Telegram positive/no-change/error scenarios and owner receipt pass before closure.

## Change impact

- Architecture: none.
- Data/schema/backup: no DDL; existing pipeline run/stage evidence stores only counts, hashes and outcomes.
- Security/privacy: no account identifiers, totals, credentials, raw rows or destination identifiers in payload/evidence.
- MCP/API compatibility: none.
- Deployment/rollback: independent feature flag and prior immutable image.
- Cost/SLO: maximum three extra Telegram operations per applicable day; zero additional market-data calls.

## Plan

1. Freeze no-transition, transition, replay and ambiguous-send scenarios.
2. Add bounded report composition/rendering and date-slot idempotent evidence.
3. Compose after the permanent held-position evaluation and detail delivery.
4. Run focused, quick and full gates, merge and protected release.
5. Execute immediate actual transport scenarios and reconcile the next three scheduled receipts.

## Sub-items

- `none`.

## Stabilization plan

- Observation: immediate controlled report plus the next 10:00, 14:30 and 16:00 slots.
- Signals: evaluated/active/changed/quality-suppressed counts, report hash, provider outcome and reused flag.
- Rollback: duplicates, unsafe content, unexplained counts or owner rejection disable only the slot-report flag.
- Exit: provider-confirmed one-per-slot delivery, preserved detail de-duplication and owner acceptance.

## Real-use acceptance

- Actual client/transport: existing Cloud Run Jobs and approved private Telegram destination.
- Positive: a slot containing active and newly changed signals produces one consolidated report.
- Partial/no-change: zero transitions still produces an explicit useful report; quality-suppressed counts remain named.
- Error: unsafe payload fails before I/O and ambiguous provider result is sealed without automatic resend.

## Evidence

- Intake evidence: 2026-10-16 10:00 evaluated 21 candidates and sent 19 eligible transitions; 14:30 and 16:00 each
  evaluated 17 candidates with zero transitions and zero sends. This proves evaluation occurred but minimum receipt did not.
- Focused Telegram, signal evaluation, owner report and release suite: 153 passed. It covers all three labels,
  active baseline with explicit zero change, date-slot replay, provider-crash ambiguity, evaluation/storage mismatch,
  current-only photo layout and the protected `wi076` release target.
- `bash scripts/check.sh quick`: passed with WI-076 as the only active implementation.
- `bash scripts/check.sh full`: 856 passed with the existing Authlib deprecation warning and a sandbox-only pytest
  cache warning; Project OS, data, architecture, warehouse, MCP and documentation gates all passed.
- PR #164 merged as `f5b9dc44d94bb6faf5e66467640f554b844b3bbb`; protected GitHub run `39044692160`
  passed from that exact `master` SHA, including the full test step and the dedicated `wi076` release step.
- The release built once and pinned the 10:00, 14:30 and 16:00 owned-core Jobs to
  `sha256:fc187a3bd5770a8d808cd53e431855a8fffd3a7112e42904abeab2c185e2b195`. Live reconciliation confirmed
  `deploy-target=wi076-three-slot-signal-status`, the merge SHA/run ID, exact slot arguments, approved owner
  destination, real-use delivery, V2 owner report and `KIS_TELEGRAM_SIGNAL_SLOT_REPORT_ENABLED=true` on all three.
- Finance-free Rich transport execution `kis-portfolio-wi030-s03-snbfr` completed successfully on the same image
  with `deploy-target=wi076-rich-transport-smoke`. No historical financial slot was replayed.

## Closeout

- Result: stabilizing after protected production release, live Job reconciliation and successful finance-free transport smoke.
- Remaining risk: because release completed on Saturday, the next applicable 10:00, 14:30 and 16:00 runs must prove
  one-per-slot provider delivery, preserved detail de-duplication and owner usefulness; no historical report is replayed.
- Follow-up Work Item: true event-time monitoring only after a separately approved source/cost design.
