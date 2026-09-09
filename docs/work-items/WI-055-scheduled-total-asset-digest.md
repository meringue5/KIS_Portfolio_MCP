---
id: WI-055
title: Deliver a scheduled privacy-safe total-asset Telegram digest
status: stabilizing
type: change
owner: owner
decision_refs: DEC-054, DEC-048, DEC-053
requirement_refs: DEC-006, DEC-026, DEC-028, DEC-038, DEC-048, DEC-053, DEC-054
milestone_ref: MS-002
delivery_refs: none
parent_work_item: none
depends_on: WI-033, WI-030
stabilization_window: first scheduled 10:00 and 16:00 KST owner receipts plus delivery-ledger reconciliation
stabilization_exit_refs: owner receipts for both slots and terminal Control-ledger evidence
rollback_plan: disable total-asset digest composition or restore the last safe image and append a linked corrective Work Item
architecture_impact: reuses the fixed-slot V2 core Jobs and Rich Telegram adapter without a new service or schedule
data_impact: reads exact same-slot V2 canonical states and records redacted control-ledger evidence; no schema change
security_impact: omits absolute assets, changes, account values and identifiers while reusing pinned Telegram secrets
cost_impact: two additional bounded Telegram calls per open market day; no always-on compute
---

# WI-055 — Deliver a scheduled privacy-safe total-asset Telegram digest

## Problem and evidence

WI-033 already calculates reconciled instrument and cash contributions, but no scheduled user-facing total-asset report
consumes it. On 2026-09-08 the owner requested reports after the 10:00 and 16:00 collections with the largest held-stock
impacts. Silence must not make an unavailable comparison indistinguishable from a delivery failure.

## Classification and contract

- `change` under owner-approved DEC-054, consuming rather than redefining WI-033.
- Compare the prior open KRX date and current date at the exact same V2 evaluation slot.
- Rank by KRW valuation change and expose only total-asset impact percentage points; this is not return attribution.
- Use a separate pipeline idempotency key and terminal-unknown boundary from event-driven alert delivery.

## Scope

- Include: 10:00 and 16:00 Rich Message, total change percent, positive/negative Top 3, cash impact, reconciliation,
  FX caveat, explicit unavailable rendering, control-ledger evidence and scale-to-zero deployment target.
- Exclude: 14:30 digest, absolute portfolio or change amounts, account breakdown, inbound bot commands, a new Scheduler,
  table, secret, service or alert-rule change.

## Acceptance criteria

- [x] Exactly one digest is terminally handled for each logical date and enabled slot; 14:30 is skipped.
- [x] A provider-ambiguous or interrupted send is sealed `unknown` and never automatically replayed.
- [x] A pass report shows same-slot total change, Top 3 each direction, cash and reconciliation without absolute amounts.
- [x] Missing, partial or non-reconciled states send `계산 보류` without fabricated values.
- [x] Existing event alert production behavior remains unchanged.
- [x] Focused, quick and full gates pass; tested master is deployed to the three existing core Jobs.

## Change impact

- Architecture: one composed post-collection service in the existing modular monolith.
- Data/schema/backup: existing Gold states and Control ledgers only; no migration or backup allowlist delta.
- Security/privacy: existing Telegram secrets; public payload contains percentages and safe instrument labels only.
- MCP/API compatibility: no MCP or REST response change.
- Deployment/rollback: `wi055` manual target; disable `KIS_TELEGRAM_TOTAL_ASSET_REPORT_ENABLED` to roll back independently.
- Cost/SLO: at most two added Telegram calls per applicable weekday and negligible incremental Job duration.

## Plan

1. Freeze DEC-054 and governance contracts.
2. Implement privacy-safe renderer and exact same-slot report builder.
3. Add terminal idempotency, batch composition and deployment flag.
4. Verify, merge, deploy and observe the first 10:00/16:00 receipts.

## Sub-items

- `WI-055-S01` (`stabilizing`): correct the owner-visible report after the first 10:00/16:00 receipts showed that
  the DEC-054 absolute-value suppression made a "total asset" report materially incomplete. DEC-055 permits exact
  owner-only amounts, alias-only composition and a deterministic chart while retaining fail-closed quality,
  no-sensitive-log and terminal-unknown boundaries. Current execution scope is repository-only and
  `production_effects: none`; no Cloud Run/Scheduler/secret/DB/public MCP mutation is authorized in this stage.
- `WI-055-S02` (`closed`): correct the protected workflow dispatch after run `34335622544` accepted the new
  target but skipped every deploy step. The run changed no external resource and sent no Telegram message. S02 adds
  the missing exact target condition/command and a regression assertion before the release is retried.
- `WI-055-S03` (`in_progress`): add the owner-requested Top 5 total-asset change-impact infographic. Rank eligible
  holdings by absolute KRW valuation change, then show the signed KRW contribution and signed total-asset impact
  percentage points in a diverging bar chart and caption. This is a DEC-055 presentation clarification that reuses
  WI-033 values; it does not change calculation, storage or public MCP contracts. Current execution scope is
  repository-only with `production_effects: none`; no Telegram request, production DB write, Cloud Run/Scheduler,
  IAM/secret, source activation or public cutover is authorized during implementation.

## Stabilization plan

- Observe the first scheduled 10:00 and 16:00 KST deliveries and reconcile each with terminal Control-ledger state.
- If a delivery defect appears, preserve the logical run and provider result, disable only digest composition or restore
  the prior safe image, and append a corrective Work Item instead of erasing this deployment history.
- Exit requires both slot receipts and explicit owner acceptance of the digest's information value.

## Evidence

- Focused tests: 68 passed across digest, Telegram, valuation-change and deployment suites.
- `bash scripts/check.sh quick`: passed with 56 Work Items, one active WIP, 162 governed contracts and 35 MCP tools.
- `bash scripts/check.sh full`: 466 passed; Project OS, DGH, architecture, warehouse and MCP surface gates passed.
- PR #55 merged as master `1025f4a`; GitHub Actions run `34225691712` passed.
- All three existing core Jobs use image digest `sha256:98bb6dc9...747e4`, deploy label
  `wi055-total-asset-digest` and `KIS_TELEGRAM_TOTAL_ASSET_REPORT_ENABLED=true`. The 14:30 runtime remains a
  pre-ledger/pre-provider skip by contract; only 10:00 and 16:00 can send.
- Operational evidence: first scheduled owner receipt remains pending.
- `WI-055-S01` intake evidence: on 2026-09-09 the owner supplied the 16:00 receipt and rejected its information value
  because it showed only percentage-point contributors. Cloud Run executions `...1000-tc9mf` and `...1600-886tl`
  both succeeded on master `1025f4a`; the Control ledger recorded `quality_status=pass` and `outcome=sent` for both
  slots. This is an approved presentation/privacy contract correction, not a calculation or transport defect.
- `WI-055-S01` repository evidence: focused report/transport/release tests passed 69; `bash scripts/check.sh quick`
  passed during implementation and `bash scripts/check.sh full` passed 501 tests. A synthetic 1200x800 chart was
  rendered and visually inspected. Tests verify exact amount/allocation reconciliation, allowlisted aliases, verified
  owner destination, no internal ID in caption, content-hash-only ledger evidence, single `sendPhoto`, terminal
  ambiguous-send sealing, finance-free same-image smoke and atomic legacy-off/v2-on release flags.
- Production effects: none. No Telegram request, production DB write, Cloud Run/Scheduler/IAM/secret change, public
  MCP activation or source call was performed by S01 repository verification.
- `WI-055-S02` incident evidence: GitHub Actions run `34335622544` passed tests and authentication but displayed the
  WI-055 deploy step as skipped because `.github/workflows/deploy-cloud-run.yml` had no step whose condition matched
  `wi055-s01`. This is a release-workflow defect and a safe no-op, not a provider or runtime failure.
- `WI-055-S02` correction evidence: the workflow now has an exact `wi055-s01` condition and invokes that exact script
  target with the existing smoke Job. The focused workflow/deploy suite passed 39 and the full gate passed 502 tests;
  production remained unchanged during verification.
- Release evidence: PR #59 merged the report as master `8105652`; PR #60 merged the workflow correction as master
  `23707e7`. Protected deploy run `34336332698` passed. Same-image finance-free photo smoke execution
  `kis-portfolio-wi030-s03-prjlf` succeeded before core Job updates. All three fixed-slot Jobs now reference image
  `sha256:b54a9819...9ffd`, git SHA `23707e7`, GitHub run `34336332698`, deploy target
  `wi055-s01-owner-report`, `legacy=false`, `v2=true`, `owner-approved=true` and `dest.owner.primary`.
- Provider confirmation: the smoke command returns zero only for `outcome=sent`; both its Cloud Run execution and the
  protected workflow succeeded. Raw provider response, chat ID and message content were not copied into evidence.

## Closeout

- Result: repository implementation, governance contracts and production deployment are verified; production use is
  `stabilizing` pending scheduled owner evidence.
- Remaining risk: first production receipt and unavailable-message ergonomics require owner observation.
- Follow-up Work Item: WI-055-S03 is the active presentation correction. Complete repository verification first;
  production release and owner receipt observation remain separate guarded steps.
