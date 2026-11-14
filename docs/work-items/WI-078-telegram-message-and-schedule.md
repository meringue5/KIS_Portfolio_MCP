---
id: WI-078
title: Clarify Telegram signals and align morning and afternoon reports
status: stabilizing
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
execution_scope: owner-approved protected production release
production_effects: explicit 0024 migration; four core Jobs and Remote image; 08:00/14:00 Scheduler activation
architecture_impact: none; reuse existing Jobs and adapters
data_impact: additive evaluation slot constraint and versioned schedule contracts
security_impact: unchanged owner-only destination
cost_impact: one additional bounded daily portfolio run; no new service or provider
user_visible_impact: yes
real_use_acceptance: required
real_use_evidence_refs: governance/project/evidence/wi078/protected-release.json; governance/project/evidence/wi078/corrective-release-2026-11-06.json
stabilization_window: immediate actual Telegram scenarios plus next 08:00 and 14:00 KST scheduled receipts
stabilization_exit_refs: provider-confirmed once-per-slot results and owner receipt; governance/project/evidence/wi078/protected-release.json
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
Initial isolated implementation had no live effects. Owner approved protected production release on 2026-11-05; release succeeded.

## Plan

1. Register approved requirements and contracts.
2. Update renderer, slot routing, collection and Scheduler definitions.
3. Verify gates; prepare reviewable release and actual-client acceptance.

## Sub-items

- WI-078-S01 — KST morning observation selection recovery.
- WI-078-S02 — overseas exchange row deduplication and scheduled Telegram recovery.

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
- Protected release run 42018708208 succeeded from merged master 733116843a8971c9ddf5ef7fef09aa87207b4c42.
  Runtime image sha256:542df53dfdc765cd11c4c9401940d54f7ec011f733d9c65f859fbe698bf36f7a matches all four Jobs.
  08:00/10:00/14:00/16:00 Scheduler definitions are ENABLED, Asia/Seoul; old afternoon resource name retained.
  Actual Cloud Run Telegram fixtures sent three provider-confirmed marked synthetic messages; unsafe payload rejected before I/O.
  Scheduled 08:00 exposed WI-078-S01; 10:00 domestic details and status succeeded. Owner-value acceptance remains open.


## Closeout

Protected production release verified; stabilizing for actual scenarios, next scheduled receipts and owner acceptance.


## Release review notes

Protected target wi078 performs private pre/post backup and fresh restore, all-table fingerprints, row-preserving
0024, transport smoke, four Jobs, Remote logical-handle compatibility, then Scheduler update. Existing afternoon
Job/Scheduler resource names remain 1430; logical args and cron become 1400. Prior definitions must be captured
before production approval; partial rollout failures require restoring Jobs and schedules together.
Existing KRX-open-date/weekday calendar policy is retained; weekends/US-only holidays are not newly activated.
The new 08:00 run may legitimately expose unavailable FX or prior same-slot comparison; it must not invent totals.
MCP input schema/scopes stay unchanged; old kr-1430 input is a compatibility alias of the current afternoon Job.


## Production authorization — 2026-11-05

Owner explicitly instructed “배포해주세요” after reviewing PR #181 and the 985-test/CI result.
Proceed through the protected master workflow with private backup/restore and runtime identity checks.
Prior Job/Scheduler definitions captured privately under /private/tmp/wi078-production-rollback; never commit raw configs.


## WI-078-S01 — KST morning observation selection recovery

- Classification: defect; work_lane stabilization_recovery; discovered_from WI-078 actual scheduled use.
- 2026-11-06 08:00 run e5c8bcc8-7fa6-4945-8daf-905b604c4be4 succeeded in collection but produced zero evaluated
  overseas candidates and sent an unavailable owner report. 10:00 evaluated 17 domestic candidates and sent five details.
- Root cause: materialize_daily_state filters TIMESTAMPTZ observations by UTC CAST(as_of AS DATE), excluding the
  prior-UTC-date observations made at 08:00 KST. Approved logical date is Korean calendar date.
- Fix: explicitly select Asia/Seoul date for positions and cash, bounded by the publication as_of cutoff. No new
  dataset, schema, threshold, financial fact, source or history rewrite. Preserve original failed 08:00 evidence.
- Verification: cross-UTC/KST-day regression for positions and cash, future observation exclusion, quick/full,
  protected same-runtime release and actual source/transport verification. Quick/full/CI passed with 986 tests; corrective release 42144894046 succeeded.


### WI-078-S01 protected corrective release — 2026-11-06

- PR #182 merged as 83cc004e2e108313afda1a2528046a8565aa0cf9. Protected run 42144894046 succeeded.
  Image sha256:f6b6102edbd73fdfac525f30ea676d3fd4864a0dc52706f24cb0677b93ae8c59 is verified on all four Jobs
  and Remote revision kis-portfolio-remote-00068-r7k (100% stable traffic and compatibility tag).
- Migration replay applied nothing; private pre/post backup/fresh restore preserved all 80 non-migration tables.
- Actual deployed image executed the in-memory KST boundary regression successfully. Read-only source query found
  22 KRX account-position rows and four NAS rows in the original pre-09:00 KST collection window, confirming data
  existed while the original UTC-day materialization selected none.
- After separate explicit owner approval, one supplement using the actual 10:00 slot/source timestamp
  2026-11-06T01:16:15.826903+00:00 was sent to the existing private Telegram destination: quality pass, no blockers,
  provider outcome sent. The caption explicitly identifies the 10:00 basis. No old 08:00 rows were rewritten;
  zero KIS calls and zero production financial writes in acceptance.
- Original marked synthetic active/recovered/quality-deferred messages were provider-confirmed, and unsafe input
  was rejected before I/O. These are distinct from the actual-data supplement and future scheduled receipts.
- Remain stabilizing: next 14:00 and 08:00 scheduled source/report receipts plus owner information-value acceptance.
  Do not close from deployment, controlled validation or provider-confirmed delivery alone.

Evidence: governance/project/evidence/wi078/corrective-release-2026-11-06.json.

## WI-078-S02 — Overseas exchange row recovery

- Classification: incident; work_lane: stabilization_recovery; discovered_from: WI-078 scheduled use.
- 2026-11-09 and 2026-11-10 all four owner-report Jobs failed at price coverage 44/46 before Telegram delivery. Scheduler remained enabled. A KIS NASD balance response included a holding with `ovrs_excg_cd=AMEX`; the AMEX balance response included the same holding. The collector treated the queried exchange as the instrument exchange, requested NAS prices and received successful but empty responses. AMS prices were present. The duplicate row also produced an extra position identity.
- Preserve the failed run and raw-source evidence. Use the row's exchange code, deduplicate the same account/instrument across exchange queries, and keep a strict failure when a genuinely held instrument lacks price coverage. Avoid fabricating price or delivery success.
- Affected contracts: `collection.owned-portfolio-core-v1`, `pipeline.owned-portfolio-core-v2`, `dataset.portfolio-position-observation`, and `dataset.price-bar-daily`. The approved held-instrument grain and strict quality gate are unchanged.
- Isolated verification: quick/full gates passed, 987 tests. Read-only replay of the 2026-11-10 10:00 landed bundle reduced 46 price requests to 44 canonical requests, all 44 covered; the two removed requests were wrong-exchange reads. No production data or delivery was changed by this replay.
- Release and exit: quick/full gates, protected deployment, actual positive/partial/error transport scenarios, next scheduled source/provider results, and owner receipt. Until these pass, WI-078 remains stabilizing.
- 2026-11-14 protected release: PR #184 merged as `09ff119e`; workflow `43537052840` succeeded. The WI-078 migration execution completed, provider-confirmed transport smoke returned `sent`, and all four core Jobs plus the 100%-serving Remote use one image digest. The four Asia/Seoul weekday Schedulers remain enabled at 08:00, 10:00, 14:00 and 16:00. Prior Job/Scheduler definitions were privately saved for rollback. The release outcome proves deployment and provider transport; it does not prove a scheduled financial report.
- Owner confirmed receipt of the marked validation Telegram message on 2026-11-14. This accepts the transport smoke only; scheduled report content and delivery remain unverified.
- Next verification: observe the next KRX-open scheduled 08:00/10:00/14:00/16:00 runs, confirm price coverage and per-slot delivery outcomes, and obtain owner receipt before closing. Do not replay failed historical dates as current reports.

Evidence: governance/project/evidence/wi078/exchange-row-recovery-release-2026-11-14.json.
