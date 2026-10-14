---
id: WI-073
title: Restore production journal OAuth consent and scope challenges
status: verified
type: defect
owner: owner
decision_refs: ADR-015, ADR-020, ADR-028
requirement_refs: DEC-029, DEC-030, DEC-038
milestone_ref: MS-003
delivery_refs: none
parent_work_item: WI-046
depends_on: WI-046
discovered_from: WI-046
supersedes: none
rollback_of: none
work_lane: operations
execution_scope: production recovery through protected release
production_effects: auth and remote journal scope recovery
architecture_impact: none; restore approved scope separation and OAuth challenge contract
data_impact: none; no schema or journal content changes
security_impact: explicitly consented journal permission; existing grants stay unchanged
cost_impact: existing services only
user_visible_impact: yes
real_use_acceptance: required
real_use_evidence_refs: owner Claude insufficient_scope report; fresh consent replay pending
stabilization_window: none
stabilization_exit_refs: none
rollback_plan: none
---

# WI-073 — Restore production journal OAuth consent and scope challenges

## Problem and evidence

Owner Claude `upsert-trade-journal` fails with `insufficient_scope`. Live auth metadata advertises read/offline and resource metadata read only. Production environment has no allowed-scopes variable. Generic deployment read-only fallback can revert prior V2 activation.

## Classification and contract

Defect against DEC-029/030/038 and approved ADR-015/020/028. No new tool, order scope, source or trust boundary. Owner asks to proceed with recovery. Existing read grants remain unchanged; journal requires fresh explicit consent. Collection authority remains separately configured.

## Scope

Production journal scope configuration; resource discovery and command HTTP challenge. Preserve application authorization, idempotency and expected revisions. No real journal content invented or altered during verification. Trade producer diagnosis is read-only and belongs to WI-063 recovery if needed.

## Acceptance criteria

- [ ] Discovery advertises journal on auth and resource endpoints.
- [ ] Read-only command HTTP 403 challenges specify exact missing scope; authenticated reads remain available.
- [ ] Authorized command body reaches MCP unchanged and application authorization remains enforced.
- [ ] Full gate and protected auth/remote release pass.
- [ ] Owner Claude reconnect and actual journal revision acceptance.

## Change impact

No schema, secret rotation or new costs. Existing services and approved scopes only. Production default permits read/journal/offline; local defaults remain read/offline. Collect is an explicit configuration choice.

## Plan

Regression tests, shared metadata and transport correction, production configuration, protected release, live discovery and actual client checks, fresh owner consent.

## Sub-items

None.

## Stabilization plan

After protected release, inspect serving discovery and immediately replay read/partial/error. Owner reconnects Claude and writes the intended journal with idempotency and current expected revision. Restore prior serving revision/configuration if transport fails; preserve old grants and history. Close only on owner acceptance.

## Real-use acceptance

Owner Claude failure is the trigger. Actual Codex OAuth read/partial/error checks and fresh Claude write are required. Do not manufacture financial journal content to obtain a test result.

## Evidence

2026-10-14 live discovery confirmed read-only scope regression. Domestic trade Scheduler is enabled; Jobs succeeded October 8/9/12/13 and failed October 7. Ledger October 7-13 is empty, reports coverage_through October 13 but partial coverage. No producer stoppage inferred from event knowledge timestamp; no collection replay.

## Closeout

Pending full gate, production release and owner Claude consent/write.

- Remote release uses the guarded WI-065 image/traffic path through target `wi073`, adding only the explicit allowed-scope env update; stable and Claude compatibility routes move together. Existing runtime settings and fixed Jobs are preserved.

- Repository verification: 45 auth/command/compatibility tests, 117 auth/deployment tests and full 842 tests passed. Quick, governance, architecture, warehouse, MCP and documentation gates passed. Owner identifies Samsung purchase in brokerage this week with settlement D+2 today; preserve as concrete trade discrepancy pending source evidence.
