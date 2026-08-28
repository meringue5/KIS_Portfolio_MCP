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

- `none`.

## Evidence

- Pending.

## Closeout

- Result: proposed.
- Remaining risk: source revision policies differ.
- Follow-up Work Item: WI-040.
