---
id: WI-078
title: Clarify Telegram signals and align morning and afternoon reports
status: verified
type: change
owner: owner
decision_refs: DEC-064
requirement_refs: owner request 2026-11-05 and explicit 14:00 alignment
milestone_ref: MS-009
delivery_refs: none
parent_work_item: none
depends_on: WI-076
discovered_from: WI-070, WI-076
supersedes: none
rollback_of: none
work_lane: delivery
execution_scope: isolated
production_effects: none
architecture_impact: none; reuse existing Jobs and adapters
data_impact: additive evaluation slot constraint and versioned schedule contracts
security_impact: unchanged owner-only destination
cost_impact: one additional bounded daily portfolio run; no new service or provider
user_visible_impact: yes
real_use_acceptance: required
real_use_evidence_refs: pending
stabilization_window: none
stabilization_exit_refs: none
rollback_plan: restore prior immutable Jobs and Scheduler definitions; preserve all alert history
---

# WI-078 — Telegram wording and schedule

## Problem and evidence

Owner cannot interpret recovered/정상화 or unexplained yellow icons. Owner requests overseas holdings at 08:00,
total assets at 08:00/14:00, and explicitly approves moving afternoon stocks from 14:30 to 14:00.
Latest master is the implementation base; unrelated dirty checkout is preserved.

## Classification and contract

Change approved by direct owner request; DEC-064 owns behavior. No threshold, rule identity, provider,
public MCP contract, account scope or order capability changes.

## Scope

Internal 08:00 collection and U.S.-close evaluation; domestic 10:00/16:00 retained; replace 14:30 with 14:00.
Owner total reports at 08:00/14:00, exact-slot comparison and explicit quality limitations.
Condition release must not claim rebound or trend reversal. Show severity in words.

## Acceptance criteria

- [x] Clear condition/release wording and explicit severity with neutral release icon.
- [x] 08:00 overseas only; U.S. session identity prevents repeated later details.
- [x] 14:00 replaces 14:30; totals at 08:00/14:00 only.
- [x] Positive, partial, error, replay and migration tests; quick/full gates.
- [ ] Protected release, immediate actual Telegram scenarios and owner receipt before closure.

## Change impact

No new financial metric. Add kr-1400 while retaining historical kr-1430 records.
No live migration or deployment during isolated implementation.

## Plan

1. Register approved requirements and contracts.
2. Update renderer, slot routing, collection and Scheduler definitions.
3. Verify gates; prepare reviewable release and actual-client acceptance.

## Sub-items

none

## Stabilization plan

After release: immediate positive/partial/error scenarios and next 08:00/14:00 slots.
Rollback on duplicates, misleading wording, missing quality limits or reports.

## Real-use acceptance

Private Telegram through protected Cloud Run Jobs. Pending release; tests do not prove receipt.

## Evidence

- Latest-master isolated worktree; original checkout and its uncommitted changes untouched.
- Quick and final full gates passed: 985 tests, one existing Authlib warning. Missing-session/quality
  wording, backup/restore and compatibility regressions are included.
- Synthetic verification covers explicit severity/release meaning, unavailable metrics, foreign-only morning,
  U.S.-session reuse, afternoon exact-slot totals, date-slot idempotency, provider ambiguity, migration history/PK
  preservation, failed private backup, fresh restore, single-image release order and legacy MCP handle compatibility.
- Production migration, deployment, external messages and actual Telegram receipt: not executed.


## Closeout

Repository implementation verified. Production approval, protected release and real-use acceptance remain open.


## Release review notes

Protected target wi078 performs private pre/post backup and fresh restore, all-table fingerprints, row-preserving
0024, transport smoke, four Jobs, Remote logical-handle compatibility, then Scheduler update. Existing afternoon
Job/Scheduler resource names remain 1430; logical args and cron become 1400. Prior definitions must be captured
before production approval; partial rollout failures require restoring Jobs and schedules together.
Existing KRX-open-date/weekday calendar policy is retained; weekends/US-only holidays are not newly activated.
The new 08:00 run may legitimately expose unavailable FX or prior same-slot comparison; it must not invent totals.
MCP input schema/scopes stay unchanged; old kr-1430 input is a compatibility alias of the current afternoon Job.
