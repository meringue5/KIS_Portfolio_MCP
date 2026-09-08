---
id: WI-055
title: Deliver a scheduled privacy-safe total-asset Telegram digest
status: in_progress
type: change
owner: owner
decision_refs: DEC-054, DEC-048, DEC-053
requirement_refs: DEC-006, DEC-026, DEC-028, DEC-038, DEC-048, DEC-053, DEC-054
milestone_ref: MS-002
delivery_refs: none
parent_work_item: none
depends_on: WI-033, WI-030
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
- [ ] Focused, quick and full gates pass; tested master is deployed to the three existing core Jobs.

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

- `none`; implementation is one bounded outcome.

## Evidence

- Focused tests: 68 passed across digest, Telegram, valuation-change and deployment suites.
- `bash scripts/check.sh quick`: passed with 56 Work Items, one active WIP, 162 governed contracts and 35 MCP tools.
- `bash scripts/check.sh full`: 466 passed; Project OS, DGH, architecture, warehouse and MCP surface gates passed.
- Operational evidence: pending deployment and owner receipt.

## Closeout

- Result: pending.
- Remaining risk: first production receipt and unavailable-message ergonomics require owner observation.
- Follow-up Work Item: none identified.
