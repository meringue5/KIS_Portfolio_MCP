---
id: WI-037
title: Build filing actual and fundamental fact pipeline
status: proposed
type: change
owner: owner
decision_refs: ADR-021, ADR-023
requirement_refs: DEC-020, DEC-022, DEC-025, DEC-032
milestone_ref: MS-003
delivery_refs: V2-W0406
parent_work_item: none
depends_on: WI-012, WI-017
architecture_impact: none; activates approved source adapters
data_impact: filing events and point-in-time financial facts
security_impact: official public filings; private storage remains access controlled
cost_impact: bounded held-issuer daily batch
---

# WI-037 — Build filing actual and fundamental fact pipeline

## Problem and evidence

Approved OpenDART/SEC contracts have schema foundations but no production collection and parsing path.

## Classification and contract

- `change` activating approved actual-fact collection; KIS estimates remain experimental and labeled.

## Scope

- Include held-issuer mapping, immutable filings, corrections, taxonomy facts, quality and lineage.
- Exclude licensed consensus and valuation signals.

## Acceptance criteria

- [ ] corrections preserve knowledge time and original taxonomy facts.
- [ ] bounded source, object backup/restore and reconciliation gates pass.
- [ ] official facts are queryable without future leakage.

## Change impact

- Existing managed pipeline and private object boundary only.

## Plan

1. Record bounded fixtures. 2. Implement adapters/parsers. 3. Activate scheduled held-issuer shards.

## Sub-items

- `none`.

## Evidence

- Pending.

## Closeout

- Result: proposed.
- Remaining risk: taxonomy coverage requires incremental mapping.
- Follow-up Work Item: WI-038 and WI-041.
