---
id: WI-026
title: Activate rights-approved ETF constituent collection
status: proposed
type: change
owner: owner
decision_refs: ADR-023, V2-ADR-006, V2-ADR-010, V2-ADR-012
requirement_refs: DEC-018, DEC-019, DEC-025, DEC-030, DEC-038, DEC-041, DEC-044
milestone_ref: MS-002
delivery_refs: V2-W0405
parent_work_item: none
depends_on: WI-012, WI-017
architecture_impact: activates only provider profiles that pass the approved rights and host gate
data_impact: official ETF constituent raw manifests and daily canonical snapshots
security_impact: public market metadata; secrets and holding facts remain outside route/profile contracts
cost_impact: bounded scale-to-zero collection and storage measured per provider
---

# WI-026 — Activate rights-approved ETF constituent collection

## Problem and evidence

WI-017 completed exact routing and offline parsers, but every provider remains `fixture_only` because automation,
cloud processing, raw retention and derived-use rights are unknown.

## Classification and contract

- `change`; each provider stays fail-closed until its rights profile is explicitly approved.
- KIS partial composition is cross-check only, never a completeness fallback.

## Scope

- Include provider-specific rights review, bounded official-source adapter, raw landing, quality and forward snapshots.
- Exclude unapproved scraping and reconstruction of unavailable historical holdings.

## Acceptance criteria

- [ ] each activated profile has allowed rights fields, host restrictions, budget and evidence date.
- [ ] incomplete or changed formats fail partial/quarantine without publishing official look-through.
- [ ] production collection, cost, lineage and restore evidence exist per activated provider.

## Change impact

- Provider-specific network activation; each source retains its own rollback switch.

## Plan

1. Complete provider sub-items without weakening unknown-rights gates.
2. Activate only approved profiles through fixed-argument jobs.
3. Measure one-month coverage/storage and reconcile snapshot completeness.

## Sub-items

- `WI-026-S01`: review and activate TIME ETF profile.
- `WI-026-S02`: review and activate KoAct ETF profile.
- `WI-026-S03`: review and activate RISE ETF profile.
- `WI-026-S04`: review and activate PLUS ETF profile.

## Evidence

- Pending.

## Closeout

- Result: proposed; provider rights evidence is pending.
- Remaining risk: current-only source history cannot be recreated later.
- Follow-up Work Item: WI-027.
