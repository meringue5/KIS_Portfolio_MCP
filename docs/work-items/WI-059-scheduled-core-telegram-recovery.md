---
id: WI-059
title: Restore 10:00 quality and scheduled Telegram delivery after the V2 core deployment
status: stabilizing
type: incident
owner: owner
decision_refs: DEC-051, DEC-053, DEC-055, ADR-021, ADR-023
requirement_refs: DEC-030, DEC-038, DEC-051, DEC-053, DEC-055
milestone_ref: MS-006
delivery_refs: none
parent_work_item: none
depends_on: WI-058, WI-055
discovered_from: WI-058, WI-055
supersedes: none
rollback_of: none
execution_scope: production
production_effects: deploy
architecture_impact: none; restore existing fixed-slot Job, quality and outbound boundaries
data_impact: correct price request-coverage counting without changing stored rows, grain, source or retention
security_impact: restore approved owner-only Telegram flags and pinned secret references without exposing values
cost_impact: no new resources or source calls; existing photo smoke and scheduled messages resume
stabilization_window: first post-release 10:00 and 16:00 scheduled runs plus owner receipt
stabilization_exit_refs: post-release Job execution, per-run quality result, redacted delivery ledger and owner report
rollback_plan: use the last known safe image/configuration through a protected release; do not replay historical sends
---

# WI-059 — Restore scheduled core and Telegram

## Problem and evidence

On 2026-09-16 the first 10:00 execution using the new price-quality rule failed in the quality stage with
`price coverage failed: 834/42`. The rule compared distinct daily price rows to the number of held-instrument
price requests; an overseas response can contain many historical dates per request. The 14:30 and 16:00 Jobs
completed but their Telegram alert and owner-report components were disabled with zero send attempts.

Cloud Run execution metadata ties the deployment change to protected workflow `34916315077`: the 2026-09-15
10:00 execution used the prior image with outbound delivery and owner report enabled and pinned secret references;
the same day's 16:00 and the 2026-09-16 three slots used the generic `v2-core-batch` deployment image. The generic
deployment did not supply the established outbound configuration or secret references. The owner reports that the
2026-09-15 10:00 total-asset report was the last visible Telegram message.

## Classification and contract

- `incident` with two implementation defects under existing approved contracts.
- Contracts: `dataset.price-bar-daily`, `pipeline.owned-portfolio-core-v2`, DEC-051/053/055 and fixed-slot Job release.
- No new source, quality relaxation, recipient or message type is requested. The owner authorized recovery on
  2026-09-16.

## Scope

- Include: count price coverage per requested instrument/basis observation that yielded at least one admissible bar;
  preserve strict failure if any request has no bar; prevent generic Job deployment from silently replacing an active
  Telegram-enabled release; restore the owner-approved configuration via the protected photo-smoke release path.
- Exclude: re-running the failed 10:00 Job, backfilling missed messages, changing Scheduler, destinations, secrets or
  public MCP contracts.

## Acceptance criteria

- [x] Multi-row overseas history cannot inflate request coverage; one empty/future-only request still fails.
- [x] Generic V2 core deployment cannot silently disable owner-approved outbound settings.
- [x] Focused, quick, full and protected CI gates pass.
- [x] Three production Jobs share the tested image and restore alert, report, destination and secret-reference settings.
- [ ] First post-release 10:00 run succeeds with exact per-request quality evidence and bounded delivery outcomes.
- [ ] Owner confirms client-visible report or a legitimate no-send outcome; no historical send is replayed.

## Change impact

- Architecture: none.
- Data/schema/backup: no physical change; existing price bars and failed run stay immutable.
- Security/privacy: compare boolean flags and secret-reference presence only; never print values.
- MCP/API compatibility: none.
- Deployment/rollback: protected master `wi055-s04` target; old safe image/configuration remains rollback input.
- Cost/SLO: no additional source calls; one finance-free photo smoke follows the existing release contract.

## Plan

1. Record production evidence and freeze both regressions as tests.
2. Correct per-request price quality accounting and fail-close the unsafe generic release path.
3. Run gates, merge and protected deploy; verify exact Job labels/configuration without revealing secrets.
4. Observe the next scheduled 10:00/16:00 slots and owner receipt before closing.

## Sub-items

- none.

## Stabilization plan

- Observe first post-release 10:00 and 16:00 fixed-slot executions, quality rows and aggregate Telegram ledger.
- If quality fails, keep sends gated; if delivery is disabled or ambiguous, do not auto-retry or duplicate messages.
- Exit after live runtime evidence and owner-visible receipt or an explicitly justified no-send result.

## Evidence

- 2026-09-16 execution `kis-portfolio-owned-core-v2-1000-fp9s2` failed at quality on run
  `4a561c37-c755-42c7-b402-8359f4cd2fd4` with 834 normalized distinct price rows from 42 requests.
- 2026-09-16 14:30/16:00 executions completed; 16:00 summary reported owner report and Telegram delivery disabled
  with zero attempts. Job template has both report flags false and no Telegram bot/chat secret references.
- 2026-09-15 10:00 pre-deploy execution had delivery, real-use and owner report enabled and secret references present;
  16:00 post-deploy execution did not.
- Repository correction counts price coverage per request with at least one admissible row, not per daily row. A
  multi-row history response produces 1/1 evidence; a second future-only request produces a 1/2 quality failure.
  The generic `v2-core-batch` target now exits before image build and Job mutation, directing the operator to the
  existing protected owner-report target. Focused regression suite: 74 passed; quick gate passed.
- Full gate and PR #118 CI passed with 731 tests. PR #118 merged as master
  `9c7d51888db3b7fcb77053a43b4079fd7cd15d84`.
- Protected `wi055-s04` run `35070642487` completed successfully. Its finance-free photo smoke execution
  `kis-portfolio-wi030-s03-4gfv7` completed with logged `outcome=sent` and `error_code=null` before updating the
  three fixed-slot Jobs.
- All three Jobs now carry git SHA `9c7d518`, GitHub run `35070642487`, deploy target `wi055-s04-caption-layout` and
  identical immutable image digest `sha256:f434a46bf717dea0fcb437e94685f227781995db56dab9da486c5f10a2a0ac2c`.
  Redacted template inspection confirmed delivery, real-use, owner approval and V2 report enabled; canary and legacy
  digest disabled; destination and pinned bot/chat Secret references present. No Scheduler, DB or recipient changed.

## Closeout

- Result: code and configuration recovery deployed; live stabilization remains open. No missed-message replay.
- Remaining risk: the first post-release 10:00 run and owner receipt are not yet observed; photo-smoke provider success
  is not proof of a scheduled report or client-visible receipt.
- Follow-up Work Item: none at intake.
