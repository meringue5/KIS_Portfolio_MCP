---
id: WI-074
title: Recover omitted domestic SOR executions and preserve complete trade collection
status: stabilizing
type: defect
owner: owner
decision_refs: DEC-009, DEC-010, DEC-015, DEC-030, DEC-044, DEC-060, ADR-032
requirement_refs: DEC-009, DEC-010, DEC-060
milestone_ref: MS-008
delivery_refs: none
parent_work_item: none
depends_on: WI-063
discovered_from: WI-063
supersedes: none
rollback_of: none
work_lane: delivery
execution_scope: tested source correction and protected bounded production recovery
production_effects: domestic incremental Job image update and fixed October 7-14 recovery
architecture_impact: none; approved same-account domestic trade completeness, no new instrument market or provider
data_impact: no DDL; append existing trade observations and revisions with source venue retained in Bronze
security_impact: existing account secrets and confidential trade controls; no new scope or orders
cost_impact: bounded existing five-account domestic source budget; no new schedules
user_visible_impact: yes
real_use_acceptance: required
real_use_evidence_refs: protected run 38516713345; l6qml recovery and 8twgd scheduled success; Codex positive e779b12205bd4ee89a5e98c5923c3e14, partial ffc4376fc66b4195ab449c2e84fada85 and error 7367b01062b5481a8651493219e8f230; owner Claude trade link acceptance pending
stabilization_window: immediate controlled recovery and next domestic scheduled run
stabilization_exit_refs: exact Samsung October 12 and 13 execution evidence visible through Codex and Claude; recurring success and owner journal link acceptance
rollback_plan: restore prior domestic Job image if collection fails; preserve all prior and appended observations, never delete ledger history
---

# WI-074 — Recover omitted domestic SOR executions and preserve complete trade collection

## Problem and evidence

Owner reports brokerage Samsung purchases this week. Existing scheduled domestic source stages return zero raw rows, advancing coverage through October 13 while current ledger has no October trades. A bounded read-only October 12-14 comparison returned zero with omitted exchange selection and two Samsung buys with `EXCG_ID_DVSN_CD=ALL`: October 12 three shares and October 13 one share, both SOR. This establishes producer venue filtering rather than settlement delay or normalization loss.

Official KIS reference: https://github.com/koreainvestment/open-trading-api/blob/main/examples_llm/domestic_stock/inquire_daily_ccld/inquire_daily_ccld.py documents KRX/NXT/SOR/ALL.

## Classification and contract

Defect against approved same-account domestic trade completeness. Existing canonical KRX market identifies domestic instruments, not an execution-venue restriction; retain raw execution venue in Bronze. No additional source, accounts, canonical instrument market, schema, ordering or price collection is authorized. Pipeline patch version makes corrected runs distinct from prior successful zero-row executions.

## Scope

Send ALL for domestic history; preserve existing source and normalized trade identity. Deploy only existing domestic trade Job, leaving schedules and other services unchanged. Execute one fixed reviewed October 7-14 domestic recovery under existing call budgets. Preserve historical failed/successful runs and all existing observations.

## Acceptance criteria

- [ ] Source regression verifies ALL and real response becomes canonical trade events.
- [ ] Quick and full gates pass.
- [ ] Protected image provenance and bounded replay pass without ledger duplicates.
- [ ] Actual Codex ledger shows the October 12/13 Samsung buys; missing coverage stays explicit.
- [ ] Owner Claude can link the real events to journal after fresh consent.

## Change impact

No DDL, migration, secret, IAM or schedule changes. Approved trade pipeline patch version and source completeness documentation updated together. Existing account-market natural keys and idempotency retained.

## Plan

Fix source, add realistic source/pipeline regression, guarded Job-only release and fixed recovery, verify stored reconciliation and client ledger, retain stabilizing for next slot/owner acceptance.

## Sub-items

None.

## Stabilization plan

Immediate positive/partial/error ledger replay and next domestic scheduled sample. On failure restore prior image; append corrective evidence, preserve all history. Owner acceptance of actual trade-linked journal remains an exit.

## Real-use acceptance

Actual approved Codex OAuth and owner Claude. Positive Samsung buys, account-wide partial unsupported coverage and invalid-request error. No fabricated trades or journal bodies.

## Evidence

Direct KIS comparison: rt_cd=0 both; omitted exchange KIOK0560/0 rows; ALL KIOK0510/2 rows/SOR. October 12 and 13 source reconciliation in stored prior runs had raw_rows=0 and no deferred observations. No collection replay during diagnosis.

## Closeout

Pending protected release, immediate recovery and owner acceptance.

- Verification: 107 source/incremental/deploy tests passed; full production-scope gate 844 passed. Regression reprocesses a prior 1.0.0 empty success under 1.0.1, lands SOR venue and canonical quantity, and reuses repeat recovery without duplicate trade events.
- Pre-release domestic Job image: `sha256:d200e39a5cea2d192c551a19ff77d0bcba579efde00bc05125ec9a303b3757dd`; routine args remain `collect-trade-incremental-v2 --date today --scope domestic` and the pipeline execution identity is unchanged.

- First protected release 38515331206 updated only the domestic image but execution zrx26 failed before any source call or write: global minimum source watermark July 14 rejected the fixed October 7 recovery. Source route endpoints represent complementary historical/recent ranges, not scope completeness. Resolve from quality-published account-market query coverage only when every callable market in the requested scope has evidence; otherwise preserve conservative legacy fallback and no-gap/120-day guards. Retain failed execution and retry the same bounded October 7-14 scope after verification.

- Scoped coverage correction verified: five incremental tests and full production-scope gate 845 passed. Complete scoped query evidence permits October 7 reread; missing account/market evidence, true skipped dates and >120-day replay still fail closed. Immutable successor pipeline patch is 1.0.2.

- Production successor: protected run 38516713345/source be4e80a/image ae81fb7e797786cbb6eab9d806f6471dbcc5e5241eb4d7c2166530f5be89034e. Recovery l6qml succeeded 14:30-14:31 KST; normal 16:10 execution 8twgd succeeded 16:10-16:11. Routine args stayed current-date/domestic. Stored 1.0.2 evidence totals eight source calls across recovery and scheduled four-market runs; raw_rows=2, output_rows=2. No source/write occurred in the prior failed zrx26 execution.
- Actual Codex-authorized MCP ledger: October 12/13 positive returns two Samsung buys (3 and 1 shares), quality pass and no missing coverage; through October 14 returns the same verified events with explicit partial coverage (brokerage overseas date remains October 13); invalid reversed dates return invalid_request. Stored business facts each occur once, both revision 1. No journal content was fabricated.
- Remaining acceptance: owner Claude can now attach the actual Samsung trade-event IDs to a journal; journal authority itself has owner-confirmed acceptance under closed WI-073. Align Remote packaged pipeline catalog to successor 1.0.2 via guarded existing image/traffic release 38547709115; outcome pending at evidence preparation.
