---
id: WI-038
title: Build declared entitled and received dividend ledger
status: proposed
type: change
owner: owner
decision_refs: ADR-021, ADR-023
requirement_refs: DEC-023
milestone_ref: MS-003
delivery_refs: V2-W0407
parent_work_item: none
depends_on: WI-020, WI-021, WI-037
architecture_impact: none
data_impact: append-only dividend states and reconciliation links
security_impact: account-level received amounts remain confidential
cost_impact: bounded filing and account-history processing
---

# WI-038 — Build declared entitled and received dividend ledger

## Problem and evidence

Dividend tables exist as foundations, but declared, entitled, received and corrected states are not populated and
reconciled to positions and cash events.

## Classification and contract

- `change` implementing the approved dividend state machine.

## Scope

- Include gross/tax/net/currency, dates, account entitlement, cash receipt and manual provenance.
- Exclude tax advice and invented receipts.

## Acceptance criteria

- [ ] state gaps and corrections remain explicit and reversible.
- [ ] cash and filing reconciliation, restore and full gates pass.
- [ ] monthly history and change can be reproduced.

## Change impact

- Additive confidential Silver ledger; no Telegram payload activation.

## Plan

1. Freeze state transitions. 2. Implement reconciliation. 3. Verify account/source gaps.

## Sub-items

- `WI-038-S01` — closed: research dividend action, account entitlement, received cash, correction, reconciliation and
  source/account coverage boundaries without implementation or activation.

## Research checkpoint — 2026-09-01

- The approved four-state intent remains valid, but immutable issuer action, account entitlement and cash receipt
  identities should not be represented as one mutable lifecycle row.
- KIS domestic account rights are a semantic candidate for entitlement/allocation/tax, while prior IRP zero-row
  coverage remains a source gap. Overseas rights are schedule/per-share facts, not account receipt evidence.
- WI-021 cash history only normalized trade settlement, fee and tax facts; its existing cash events cannot be
  retrospectively labelled as dividend receipts without source evidence.
- The current logical/physical contract lacks state-specific dates, eligible quantity/rate, bitemporal provenance,
  correction/reversal lineage, cash links and coverage evidence; contract hardening precedes implementation.
- Received cash is the monthly-income monetary SSOT. Declared/entitled estimates remain separate, and manual evidence
  may reconcile gaps but never overwrite a broker event.
- Evidence: `docs/operations/wi-038-pre-research-2026-09.md`.

## Evidence

- `docs/operations/wi-038-pre-research-2026-09.md`
- `bash scripts/check.sh quick`

## Closeout

- Result: parent remains proposed; `WI-038-S01` research-only checkpoint closed.
- Remaining risk: action/entitlement grain, KIS domestic field semantics, historical PIT positions and overseas/IRP
  receipt coverage require formal contract decisions and bounded fixtures.
- Follow-up Work Item: formal WI-038 contract hardening after WI-037.
