---
id: WI-036
title: Establish corporate-action identity and adjustment lineage
status: proposed
type: change
owner: owner
decision_refs: ADR-021, ADR-023
requirement_refs: DEC-015..017
milestone_ref: MS-002
delivery_refs: V2-W0307
parent_work_item: none
depends_on: WI-015
architecture_impact: none; completes the approved price and ledger model
data_impact: versioned corporate-action identity and price/lot adjustment lineage
security_impact: internal market facts only
cost_impact: bounded held-instrument collection and replay
---

# WI-036 — Establish corporate-action identity and adjustment lineage

## Problem and evidence

Dual-basis price and FX ledgers are present, but split, reverse split, symbol change, merger and spin-off identity is not
yet a governed ledger that downstream lot and performance logic can cite.

## Classification and contract

- `change` completing V2-W0307; it does not reinterpret existing raw/adjusted prices.
- Contract-first source, dataset and pipeline changes are required before collection.

## Scope

- Include immutable action identity, effective/knowledge time, source provenance and price/lot adjustment links.
- Exclude tax advice and unsupported historical inference.

## Acceptance criteria

- [ ] actions and revisions are point-in-time and idempotent.
- [ ] price/quantity adjustment lineage is explicit; unknown action blocks false return claims.
- [ ] migration, repository, backup/restore and full gates pass.

## Change impact

- Additive Silver/Control contracts; no public MCP or external send.

## Plan

1. Approve source/dataset contract. 2. Add migration/repository. 3. Reconcile split fixtures and recovery.

## Sub-items

- `none`.

## Evidence

- Pending.

## Closeout

- Result: proposed.
- Remaining risk: source coverage varies by market.
- Follow-up Work Item: WI-022.
