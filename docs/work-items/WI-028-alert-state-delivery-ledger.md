---
id: WI-028
title: Implement alert state and delivery ledger
status: proposed
type: change
owner: owner
decision_refs: ADR-021, ADR-023, ADR-024, V2-ADR-007, V2-ADR-010, V2-ADR-012
requirement_refs: DEC-026..028, DEC-030, DEC-038, DEC-041, DEC-044, DEC-049
milestone_ref: MS-002
delivery_refs: V2-W0507
parent_work_item: none
depends_on: WI-019, WI-023, WI-025, WI-033
architecture_impact: implements approved signal evaluation state separate from notification transport
data_impact: versioned rules alert candidates state transitions dispatch claims and delivery ledger
security_impact: redacted candidate metadata; no Telegram credential in analytics tables
cost_impact: three scale-to-zero evaluation slots and bounded ledger writes
---

# WI-028 — Implement alert state and delivery ledger

## Problem and evidence

Metrics do not yet produce governed alert candidates or stateful de-duplication, recovery and dispatch claims.

## Classification and contract

- `change` implementing V2-W0507 before any external send.
- Signal evaluation, dispatch idempotency and transport outcomes remain separate.

## Scope

- Include rule versions, severity, fingerprints, transitions, recovery and delivery ledger/claims, consuming the
  separately governed WI-033 valuation-change contribution.
- Include ETF securities using their own price, trend, valuation-change and lot/thread inputs; constituent exposure is
  unavailable/missing coverage and must never be inferred.
- Exclude Telegram API calls and final threshold activation.
- Exclude ETF constituent, nested sector/country/currency and internal contribution alerts under DEC-049.

## Acceptance criteria

- [ ] identical state is not redelivered; escalation/re-entry rules are deterministic.
- [ ] 10:00, 14:30 and 16:00 slots plus the US close summary have stable identity.
- [ ] partial/stale inputs and sensitive fields fail closed.

## Change impact

- Gold/Control alert state only; delivery feature flag remains off.

## Plan

1. Freeze rule/fingerprint/state contracts.
2. Implement evaluation and dispatch-claim repositories.
3. Verify concurrency, retries and redaction without network calls.

## Sub-items

- `none`.

## Evidence

- Pending.

## Closeout

- Result: proposed; metric dependencies incomplete.
- Remaining risk: threshold calibration and delivery destination approval.
- Follow-up Work Item: WI-029.
