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

- `none`.

## Evidence

- Pending.

## Closeout

- Result: proposed.
- Remaining risk: overseas and pension receipt coverage may require manual provenance.
- Follow-up Work Item: WI-040.
