---
id: WI-064
title: Eliminate duplicate current trade events without erasing source history
status: proposed
type: defect
owner: owner
decision_refs: DEC-009, DEC-010, DEC-015
requirement_refs: DEC-009, DEC-010
milestone_ref: MS-008
delivery_refs: none
parent_work_item: none
depends_on: WI-063
discovered_from: WI-063
supersedes: none
rollback_of: none
execution_scope: pending_gate
production_effects: none
architecture_impact: current-read identity may need a governed business-key projection while Bronze remains append-only
data_impact: preserve all observations and revisions; correct only canonical current-event projection and evidence
security_impact: no new public identifiers or raw provider payloads
cost_impact: DB-only diagnosis and projection work expected
user_visible_impact: yes
real_use_acceptance: required
real_use_evidence_refs: direct Codex OAuth get-trade-ledger 2026-08-25 ria query on 2026-09-24
---

# WI-064 — Eliminate duplicate current trade events without erasing source history

## Problem and evidence

The WI-063 direct Codex OAuth populated-window check returned four current RIA trade rows for 2026-08-25, but the
rows formed two pairs with the same account, market, instrument, execution timestamp, side, quantity, price and
currency while differing in `trade_event_id` and `knowledge_at`. A read-only production aggregate on 2026-09-30
found 19 such duplicate business-key groups in `silver.trade_events_current`.

This is not evidence that source history should be deleted. It is evidence that the current-event identity and
revision projection need a separate review before a user-facing ledger can be called economically deduplicated.

## Classification and contract

- Initial classification: independent data-correctness defect discovered during WI-063 real-use acceptance.
- Contract: Bronze observations and revisions remain append-only; a current Silver read must not double-count one
  economic event merely because it was observed again.
- Approval: diagnosis may be read-only; implementation starts only after WI-063 is no longer the active Work Item.

## Scope

- Include: prove whether duplicates are repeat observations or legitimately distinct fills; define stable business
  identity, revision ordering and reconciliation evidence; repair the current projection and MCP fixture.
- Exclude: deleting Bronze observations, guessing trades from positions, or silently collapsing distinct executions.

## Acceptance criteria

- [ ] Every candidate duplicate group is classified from governed source fields without exposing account numbers.
- [ ] Repeated observations resolve to one current economic event while legitimate equal-price fills remain distinct.
- [ ] Historical and populated-window MCP results reconcile to the corrected Silver projection.
- [ ] Direct Codex OAuth positive/partial/error scenarios and full repository gate pass.

## Change impact

- Architecture: likely Silver identity/projection correction, not a new source producer.
- Data/schema/backup: append-only inputs retained; any view or migration change follows warehouse governance.
- Security/privacy: aggregate evidence only.
- MCP/API compatibility: row counts may decrease where repeated observations were double-counted.
- Deployment/rollback: additive projection/migration with prior view definition retained.
- Cost/SLO: DB-only read path; no additional KIS calls.

## Plan

1. Trace duplicate groups through Bronze, normalized revisions and current-view partition keys.
2. Freeze a fixture that distinguishes repeated observation from identical legitimate fills.
3. Implement and replay the smallest governed Silver correction.
4. Verify through the owner-authenticated Codex MCP connection.

## Sub-items

- `none`.

## Stabilization plan

- Observation: aggregate duplicate count and representative populated windows before/after correction.
- Signals: input observation count, classified economic-event count, revision selection and MCP row count.
- Rollback: restore the prior current projection; never delete source observations.
- Exit: zero unexplained duplicate groups plus owner acceptance of direct MCP evidence.

## Real-use acceptance

- Actual client: owner-authenticated Codex OAuth MCP.
- Positive: populated historical window returns reconciled unique current events.
- Partial: an uncovered account/window remains explicit.
- Error: invalid request stays owner-debuggable without raw identifiers.

## Evidence

- Direct MCP RIA query for 2026-08-25 returned four rows representing two identical business-key pairs.
- Production aggregate on 2026-09-30 counted 19 duplicate business-key groups.

## Closeout

- Result: proposed; no implementation or production mutation authorized by registration.
- Remaining risk: user-facing trade counts may be overstated in affected historical windows.
- Follow-up Work Item: none.
