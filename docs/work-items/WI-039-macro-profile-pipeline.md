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
architecture_impact: pending owner decision on proposed ADR-027 profile source revision and time semantics
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
- `WI-039-S02` — ready: freeze the implementation-ready profile scope, transport, series registry, heterogeneous
  revision, interpretation, migration, rights, source-budget and capacity design without adoption or implementation.

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
- Follow-up Work Item: formal WI-039 contract hardening after owner review.

## Contract design checkpoint — 2026-09-02

- The recommended `macro_profile_v1` follows C-5 exactly: five Korean and twelve U.S./global concepts. Korean M2 and
  U.S. industrial production remain later profile-version additions.
- The proposed ADR-027 uses FRED/ALFRED for all U.S./global transport, including Cboe-owned/copyrighted `VIXCLS`, and
  keeps direct Cboe collection dormant. Raw values remain owner-only with source-specific attribution.
- A typed heterogeneous revision ledger replaces fabricated realtime fields. `system_as_of` is the default and
  backfilled/latest-only history remains labeled retrospective.
- The package proposes a checked `macro_series` registry, five transparent metrics, additive migration 0016, FRED
  32/256 and ECOS 16/96 budgets, 10-page caps and 512 MiB/500k/100k capacity stop lines.
- Exact ECOS table/item IDs remain gated on `WI-039-S03` official metadata discovery plus one bounded sample per concept;
  canonical adoption is reserved for S04 after that evidence.
- Evidence: `docs/operations/wi-039-s02-contract-design-2026-09.md`.
- Result: `WI-039-S02` is ready for owner decision. Parent `WI-039` and MS-003 remain proposed; no contract adoption,
  code, DDL, source call, credential, data, infrastructure, schedule or MCP change occurred.
