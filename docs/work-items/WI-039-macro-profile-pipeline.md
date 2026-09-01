---
id: WI-039
title: Build the governed macro profile pipeline
status: proposed
type: change
owner: owner
decision_refs: ADR-021, ADR-023
requirement_refs: DEC-024, DEC-026, DEC-041
milestone_ref: MS-003
delivery_refs: V2-W0408
parent_work_item: none
depends_on: WI-012
architecture_impact: none
data_impact: versioned macro observations and vintages
security_impact: API keys remain in Secret Manager
cost_impact: small allowlisted series set and source budgets
---

# WI-039 — Build the governed macro profile pipeline

## Problem and evidence

The approved ECOS/FRED-ALFRED/Cboe macro contract is not yet collected or published.

## Classification and contract

- `change` activating only the approved macro_profile_v1 series and interpretations.

## Scope

- Include series metadata, vintages, revisions, publication cadence, license and quality.
- Exclude arbitrary series discovery and paid feeds.

## Acceptance criteria

- [ ] vintage replay excludes later revisions and preserves units/frequency.
- [ ] license, call budget, freshness, backup and full gates pass.
- [ ] missing observations remain explicit.

## Change impact

- Existing scale-to-zero pipeline; no always-on collector.

## Plan

1. Freeze series allowlist. 2. Implement source adapters. 3. Replay and activate cadence-aware jobs.

## Sub-items

- `WI-039-S01` — closed: research exact-series candidates, source-specific vintage semantics, rights and call-budget
  constraints without implementation or activation.

## Research checkpoint — 2026-09-01

- The U.S./global candidate IDs and native metadata were verified against official FRED pages; they remain candidates,
  not an activated allowlist.
- Exact ECOS table/item IDs remain gated on official metadata discovery and bounded samples; guessed codes are rejected.
- Requirements and the approved collection basket disagree on Korean M2/exports and U.S. industrial activity versus
  payrolls/real GDP/WTI, so the profile version must be reconciled before freeze.
- The current all-source natural key cannot safely represent FRED vintages and latest-only/download sources without a
  heterogeneous revision decision.
- FRED third-party rights and Cboe automated-use/attribution require per-series/source review before publish.
- Evidence: `docs/operations/wi-039-pre-research-2026-09.md`.

## Evidence

- `docs/operations/wi-039-pre-research-2026-09.md`
- `bash scripts/check.sh quick`

## Closeout

- Result: parent remains proposed; `WI-039-S01` research-only checkpoint closed.
- Remaining risk: exact ECOS identity, profile-scope reconciliation, rights and heterogeneous source revision contract.
- Follow-up Work Item: WI-040.
