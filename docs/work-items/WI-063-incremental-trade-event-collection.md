---
id: WI-063
title: Restore governed incremental trade-event collection and coverage evidence
status: proposed
type: defect
owner: owner
decision_refs: DEC-009, DEC-010, DEC-015, DEC-030, DEC-044, DEC-059
requirement_refs: DEC-009, DEC-010, DEC-059
milestone_ref: MS-008
delivery_refs: none
parent_work_item: none
depends_on: WI-062
discovered_from: WI-062
supersedes: none
rollback_of: none
execution_scope: planning
production_effects: none
architecture_impact: restore a bounded incremental producer without coupling trade availability to unrelated portfolio capabilities
data_impact: future append-only trade observations revisions quality evidence and per-partition coverage watermarks
security_impact: preserve account aliases only in public responses and existing confidential ledger controls
cost_impact: bounded KIS order-history calls must be measured before activation
user_visible_impact: yes
real_use_acceptance: required
real_use_evidence_refs: pending
---

# WI-063 — Restore governed incremental trade-event collection and coverage evidence

## Problem and evidence

The 2026-09-23 real-use investigation found 282 governed current trade events through 2026-08-25 and eleven
`pipeline.trade-cash-backfill-v2` watermarks whose latest value is 2026-08-28. The recurring
`pipeline.owned-portfolio-core-v2` has current successful runs, but its implementation collects balances, prices and
FX rather than order history and does not advance a trade source coverage watermark. Its catalog nevertheless names
`dataset.trade-event` as an output. A September empty result therefore cannot prove that no trades occurred.

## Classification and contract

- Classification: defect and architecture correction discovered from actual MCP use.
- Contract: approved trade-event facts remain append-only and source-derived; no trade may be inferred from holdings.
- Immediate containment: WI-062 exposes `collection_watermark_before_query_end` instead of false empty-window pass.

## Scope

- Include: choose and implement one bounded incremental producer, per-source/account coverage watermark, quality rule,
  immediate fixture/replay and direct MCP verification.
- Include: reconcile the core pipeline catalog output with the chosen producer boundary without silently weakening it.
- Exclude: fabricating trades from position deltas, arbitrary unbounded backfill, live ordering or coupling unrelated
  portfolio reads to trade collection health.

## Acceptance criteria

- [ ] The reviewed producer collects every approved current account/market partition within a bounded call budget.
- [ ] A successful partition advances an explicit contiguous source coverage watermark only after quality/publish.
- [ ] Empty-window trade-ledger pass is possible only when every requested partition covers the query end date.
- [ ] Source failure degrades trade features without blocking portfolio overview, market data or verified partials.
- [ ] Immediate replay and actual Codex OAuth MCP positive/partial/error scenarios pass after guarded deployment.

## Change impact

- Architecture: independent incremental producer preferred; no request-scoped long collection.
- Data/schema/backup: append-only existing ledger is preserved; any new control evidence needs catalog/migration/backup review.
- Security/privacy: no raw account number or provider payload in MCP or test evidence.
- MCP/API compatibility: retain WI-062 query status and coverage metadata.
- Deployment/rollback: protected pipeline/Remote release with prior revisions retained.
- Cost/SLO: measure exact KIS calls and latency before approval; no standing worker.

## Plan

1. Compare the existing daily domestic/overseas jobs and backfill runtime against an independent incremental design.
2. Approve the producer, watermark grain, quality rule, call budget and failure isolation contract.
3. Implement fixture/replay first, then guarded production release.
4. Verify direct MCP current-window behavior without waiting for a future trade or scheduler slot.

## Sub-items

- None yet; append only after architecture review.

## Stabilization plan

- Observation: immediate controlled replay plus one guarded current-date production run.
- Signals: per-partition watermark, source calls, rows published, quality evidence and unaffected portfolio reads.
- Rollback: restore prior producer/Remote revisions; never delete ledger events.
- Exit: owner accepts direct current-window MCP evidence and independent feature behavior.

## Real-use acceptance

- Required through the owner-authenticated Codex OAuth MCP connection.
- Must demonstrate a covered empty window, a populated window and an explicit source/coverage failure.

## Evidence

- Initial evidence is the read-only MotherDuck aggregate recorded by WI-062; implementation evidence pending.

## Closeout

- Result: proposed; no production mutation or source call is authorized by registration.
- Remaining risk: the trade ledger is historical-only beyond its coverage watermark.
- Follow-up Work Item: none.
