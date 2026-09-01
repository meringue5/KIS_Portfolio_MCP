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
architecture_impact: proposed ADR-025 required before implementation because layer, grain, key and time semantics change
data_impact: proposed Bronze filing artifacts, issuer aliases, filing/fact revisions and point-in-time views
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

- `WI-037-S01` — research filing sources, issuer identity, taxonomy and point-in-time controls (`closed`).
- `WI-037-S02` — freeze the implementation-ready issuer identity, filing/fact point-in-time, Bronze/Silver,
  correction, raw-object, source-budget and approval-gate design without code, DDL, source calls or activation
  (`ready`; owner decision pending).

## Pre-research checkpoint

`WI-037-S01` is a research-only sub-item. Parent `WI-037` remains `proposed`; MS-003's formal start gate remains
closed.

| Checkpoint | State | Evidence |
| --- | --- | --- |
| research start and boundary | complete | 2026-08-31; this Work Item and registry entry |
| approved contract and current-code audit | complete | logical/physical layer, grain and PIT gaps identified; live target tables empty |
| official OpenDART/SEC capability and rights audit | complete | official API, fair-access, quota, taxonomy and private-retention boundaries recorded |
| implementation inputs and unknowns | complete | `docs/operations/wi-037-pre-research-2026-08.md` |

Allowed scope is read-only repository and official-source research covering held-issuer identity, filing/correction
semantics, taxonomy facts, knowledge time, source limits and permitted retention. It excludes external collection,
credential use, fixtures containing provider payloads, DB/schema changes, contract lifecycle changes, deployment and
scheduled activation.

## Evidence

- `WI-037-S01` start checkpoint: 2026-08-31.
- `docs/operations/wi-037-pre-research-2026-08.md`: closed evidence and contract-hardening inputs.
- `WI-037-S02` start checkpoint: 2026-09-02.
- `docs/operations/wi-037-s02-contract-design-2026-09.md`: implementation-ready compatibility, identity/time,
  object, budget, migration and approval package; no production mutation.

## Closeout

- Result: parent proposed; `WI-037-S01` research closed without opening the MS-003 formal gate.
- Remaining risk: S02 requires owner approval of the proposed ADR/contract boundary; taxonomy coverage requires
  incremental mapping and bounded fixtures.
- Follow-up Work Item: after approval, append a sequential WI-037 implementation sub-item; WI-038 and WI-041 remain
  downstream of the parent outcome.
