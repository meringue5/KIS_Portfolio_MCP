---
id: WI-070
title: Restore permanent held-position Telegram signal delivery
status: closed
type: defect
owner: owner
decision_refs: DEC-051, DEC-052, DEC-053, DEC-061, ADR-021, ADR-023
requirement_refs: DEC-006, DEC-026..030, DEC-038, DEC-041, DEC-044, DEC-051..053, DEC-061
milestone_ref: MS-006
delivery_refs: none
parent_work_item: none
depends_on: WI-059
discovered_from: WI-059, WI-030
supersedes: none
rollback_of: none
work_lane: stabilization_recovery
execution_scope: closed after permanent-rule production observation, one detail delivery and explicit owner receipt
production_effects: permanent held-position rule activated; three existing owned-core Jobs updated to one immutable image digest
architecture_impact: none; preserve the existing batch, alert warehouse and outbound Telegram boundaries
data_impact: append immutable rule and approval revisions plus future candidates/state/delivery evidence; no historical replay or row rewrite
security_impact: preserve owner-only destination aliases, Secret Manager references and public-context redaction
cost_impact: no new source or service; bounded evaluation remains inside the three existing scale-to-zero Jobs
user_visible_impact: yes
real_use_acceptance: required
real_use_evidence_refs: deterministic positive/no-send/error scenarios; GitHub run 38359853705; Rich smoke execution kis-portfolio-wi070-vbk5w sent; activation execution kis-portfolio-wi070-ccmf6 passed; owner receipt and next eligible scheduled transition pending; governance/project/evidence/acceptance-review-2026-10-21/signal-owner-acceptance.json
stabilization_window: immediate activation/baseline evidence plus the next eligible scheduled transition and owner receipt
stabilization_exit_refs: protected release identity, rule approval/revocation ledger, three-Job candidate counts, delivery ledger and owner-visible Telegram acceptance; 2026-10-21 owner confirmed exact post-baseline detail message
rollback_plan: disable KIS_TELEGRAM_REAL_USE_ENABLED or restore the prior Job revision; preserve immutable rule/candidate/delivery history and do not replay missed slots
---

# WI-070 — Restore permanent held-position Telegram signal delivery

## Problem and evidence

After production cutover, daily total-asset Telegram reports continued but held-position signal alerts stopped. On
2026-10-07 all three Cloud Run Jobs and Schedulers were healthy, Telegram delivery configuration and secret references
were present, and owner reports were provider-confirmed. The external evaluator nevertheless returned `expired` and
`candidate_count=0` because immutable rule `rc-2026-09-07.1` ended on 2026-09-14. DB-only shadow evaluation continued
to create candidates/transitions, proving that the monitoring input path had not stopped.

## Classification and contract

- Classification: production defect inside the existing MS-006 Telegram recovery outcome.
- Existing contract: DEC-051/052/053 production-value semantics, baseline-only first active state, Rich Message,
  pass-quality transition delivery, immutable rules and owner approval.
- Owner decision: approve a permanent held-position successor and the five-step Project OS/recovery plan.
- Product boundary: currently held instruments only. Unheld watchlist monitoring remains a separate change.

## Scope

- Include: immutable no-expiry successor rule, explicit activation/approval and prior-RC revocation evidence.
- Include: baseline-only initialization, future transition delivery, no historical replay and three-Job operation.
- Include: deterministic positive, no-send, expired/unsupported and transport failure scenarios.
- Exclude: unheld watchlists, threshold recalibration, new metrics/providers, manual historical slot replay and message
  reconstruction from expired candidates.

## Acceptance criteria

- [x] Production evaluation no longer returns `expired` after the permanent rule's `valid_from`.
- [x] First active observation is baseline-only and does not create a Telegram delivery in deterministic verification.
- [x] A later pass-quality watch-or-higher transition creates one eligible Rich Message and one terminal attempt in deterministic verification.
- [x] Replay, quality failure, unsupported slot and transport error remain bounded and do not duplicate delivery in deterministic verification.
- [x] Only current `quantity > 0` held instruments are selected; unheld watchlists are not silently added.
- [x] Protected release, provider-confirmed evidence and owner-visible receipt pass before closure.

## Change impact

- Architecture: no boundary change.
- Data/schema/backup: no DDL; append-only control/gold evidence using existing governed datasets.
- Security/privacy: no new secrets or identifiers; existing redaction and alias-only destination remain.
- MCP/API compatibility: none.
- Deployment/rollback: protected same-image Job release and explicit enable/disable rollback; no historical send replay.
- Cost/SLO: same three scheduled jobs and zero new source calls.

## Plan

1. Freeze the expired-rule regression and permanent-rule activation fixtures.
2. Add the immutable successor and append-only owner approval/revocation command.
3. Verify baseline-only, transition, replay, quality and transport boundaries.
4. Run focused, quick and full gates, then protected release with exact runtime evidence.
5. Execute immediate production-equivalent scenarios and collect the next owner-visible eligible receipt.

## Sub-items

- `none`.

## Stabilization plan

- Observation period/sample: activation plus all three slots; at least one eligible post-baseline transition or an
  approved deterministic actual-transport positive scenario, followed by owner receipt.
- Signals: rule version/status/validity, candidate/transition/eligible/attempt/sent counts, terminal delivery outcome,
  shadow comparison and owner receipt.
- Rollback trigger and safe state: duplicate, unsafe, unapproved, false or unexplained alerts; disable real-use
  evaluation or restore the prior Job revision while retaining evidence.
- Exit evidence and owner acceptance: provider-confirmed Rich Message, no duplicate/replay, exact held-position scope
  and owner confirmation.

## Real-use acceptance

- User-visible basis: the signal alert is the primary owner notification value.
- Actual approved client/transport: the production Cloud Run Job path and verified private Telegram destination.
- Immediate positive: a controlled post-baseline watch transition renders and sends once through the actual transport.
- Immediate partial/no-send: baseline-only and pass/no-change produce zero attempts with explicit counts.
- Immediate error: unsafe payload or transport failure becomes a bounded terminal/retryable outcome without fallback.
- Findings: held-position defects remain in WI-070; unheld watchlist scope requires a separately approved change.

## Evidence

- 2026-10-07 live logs: three Jobs succeeded, external rule `expired`, external `candidate_count=0`, delivery
  `eligible_count=0`, `attempt_count=0`; independent owner reports were sent and shadow candidates remained present.
- Deterministic signal/release suite: 130 passed across activation, baseline-only, later Rich transition, one-send
  replay suppression, held-only selection, transport and protected deploy target.
- `bash scripts/check.sh quick`: passed with 70 tracked Work Items and WI-070 as the only active implementation WIP.
- `bash scripts/check.sh full`: 824 passed with one pre-existing Authlib deprecation warning.
- PR #150 merged as `fdb8f4037f0eee51bdb100409eb5459c61be26a7`; protected GitHub run
  `38359853705` passed from that exact `master` SHA.
- The release built once and pinned Rich smoke, activation and all three owned-core Jobs to
  `sha256:2bacb77326598623649b19692edcf15f4aa1fbc2cd40bb566122a7acb3d6bc9e`.
- Rich transport execution `kis-portfolio-wi070-vbk5w` completed successfully and reported
  `status=passed`, `outcome=sent`, `error_code=null` without evaluating or replaying financial signals.
- Activation execution `kis-portfolio-wi070-ccmf6` completed successfully and appended
  `permanent-2026-10-13.1` under `DEC-061`: `valid_to=null`, `scope=held-positive-quantity-only`,
  `initial_active_policy=baseline_only`, `historical_replay=false`, shadow sensitive violations 0 and external sends 0.
  The prior approved RC had 25 owner sends before revocation.
- Jobs `kis-portfolio-owned-core-v2-1000`, `-1430` and `-1600` carry the same digest, merge SHA/run labels,
  real-use and delivery enabled, owner destination approved, and the existing V2 total-asset report preserved.
- First post-activation production candidate counts and owner receipt of the next eligible held-position transition:
  pending stabilization evidence; no manual historical slot was executed.

## Historical closeout checkpoint (superseded 2026-10-21)

- Result: stabilizing after protected production release and permanent rule activation.
- Remaining risk: the next scheduled observation must prove non-expired production evaluation and establish the
  baseline; a later eligible held-position transition and owner receipt remain the user-visible exit evidence.
- Follow-up Work Item: unheld watchlist monitoring only if separately approved.

## Closeout

- Result: closed after permanent rule activation, bounded live observation and explicit owner acceptance on
  2026-10-21. The precise post-baseline detail header was reconstructed read-only from the sent candidate; the
  owner confirmed that detail was received and appropriate. It is distinct from the already-accepted WI-076 summary.
- [Runtime evidence](../../governance/project/evidence/acceptance-review-2026-10-21/signal-audit.json): active
  permanent-2026-10-13.1 with no expiry; all Oct19/20 candidates pass; Oct19 10:00 detail sent1, duplicate successful
  dispatch0. Existing baseline/no-change/replay/error tests remain passing; no historical detail was replayed.
- [Held scope](../../governance/project/evidence/acceptance-review-2026-10-21/held-scope.json): every sampled
  permanent candidate maps to a same-date/source-slot positive-quantity held position. No unheld watchlist activation.
- [Direct owner detail receipt](../../governance/project/evidence/acceptance-review-2026-10-21/signal-owner-acceptance.json)
  completes the user-visible exit; regular summary receipt was not used to infer detail receipt.
- Current operation retains immutable rules, independent disable/rollback flags, fail-closed quality and terminal
  delivery history. No unresolved same-outcome defect blocks this accepted scope. New product scope remains separate.
- Review production changes, data writes, source calls and notifications: zero.
