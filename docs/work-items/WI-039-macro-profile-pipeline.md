---
id: WI-039
title: Build the governed macro profile pipeline
status: verified
type: change
owner: owner
decision_refs: ADR-021, ADR-023, ADR-027
requirement_refs: DEC-024, DEC-026, DEC-041
milestone_ref: MS-003
delivery_refs: V2-W0408
parent_work_item: none
depends_on: WI-012
architecture_impact: ADR-027 approved; exact registry and heterogeneous revision clocks on the shared runtime
data_impact: versioned macro observations and vintages
security_impact: API keys remain in Secret Manager
cost_impact: small allowlisted series set and source budgets
execution_scope: isolated
production_effects: none
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

- [x] vintage replay excludes later revisions and preserves units/frequency.
- [x] license, call budget, freshness, backup and full gates pass.
- [x] missing observations remain explicit.

## Change impact

- Existing scale-to-zero pipeline; no always-on collector.

## Plan

1. Project the exact approved registry into runtime definitions. 2. Add migration 0016 and append-only repositories.
3. Implement offline parsers, PIT selection and five transparent metrics with safe fixtures. 4. Verify local
backup/restore and stop at `verified`; source and schedule activation remain production-gated.

## Isolated implementation checkpoint — 2026-09-10

- Activated after WI-038 reached `verified` under the MS-003 continuous isolated-overlap gate; WI-012 is already
  closed and no other implementation Work Item is `in_progress`.
- This phase is limited to the exact 17-series runtime registry, additive migration 0016, repository code, synthetic
  ECOS/FRED fixtures, local DuckDB migration/recovery and deterministic metric verification.
- Production DB migration, live DB writes, source calls or activation, credentials/IAM/Secret changes,
  Cloud Run/Scheduler, public MCP/Telegram activation, cleanup and cutover remain prohibited.
- Exit line: typed observed-content/provider-vintage revisions are append-only and PIT-correct; missing observations
  remain explicit; the five approved metrics, call/capacity guards and fresh local restore reconcile under full gate.

## Sub-items

- `WI-039-S01` — closed: research exact-series candidates, source-specific vintage semantics, rights and call-budget
  constraints without implementation or activation.
- `WI-039-S02` — closed after owner approval: freeze the implementation-ready profile scope, transport, series
  registry, heterogeneous revision, interpretation, migration, rights, source-budget and capacity design without
  adoption or implementation.
- `WI-039-S03` — closed: verify the five exact ECOS table/item/dimension/cycle/unit identities through public bounded
  official metadata and samples without retaining values or using a credential.
- `WI-039-S04` — closed: adopted the owner-approved ADR, requirements clarification and exact `approved-inactive`
  macro contracts into the canonical SSOT without implementation or activation.

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
- `docs/operations/wi-039-s02-contract-design-2026-09.md`
- `docs/operations/wi-039-s03-ecos-source-sampling-2026-09.md`
- `docs/operations/wi-039-s04-contract-adoption-2026-09.md`
- `docs/operations/wi-039-isolated-verification-2026-09.md`
- `bash scripts/check.sh quick`
- `bash scripts/check.sh full`

## Closeout

- Result: `verified` in isolated scope with no production effects.
- Remaining production gate: migration application, live source data, credential, schedule, deployment and consumer
  activation remain prohibited until MS-002 closes and a separately approved release is executed.
- Follow-up Work Item: dependency-ready WI-041; future WI-039 production activation stays a release-gated operation.

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

## ECOS verification checkpoint — 2026-09-02

- The owner approved the complete S02 package and bounded S03 verification. S02 is closed as an approved design input.
- Exact ECOS identities are `722Y001/D/0101000`, `731Y001/D/0000001`, `901Y009/M/0`,
  `901Y033/M/A00/2` and `901Y118/M/T002` for base rate, USD/KRW, headline CPI, seasonally-adjusted all-industry
  production excluding agriculture/forestry/fishing, and customs-basis exports respectively.
- The public sample exposed current period/content but no defensible publication timestamp or historical revision
  interval. ECOS therefore uses `observed_content`, nullable realtime interval, `knowledge_at=fetched_at` and a labeled
  retrospective backfill.
- All 16 bounded calls were accounted for, including five responses discarded by a local output-filter error. No value,
  credential or raw payload was retained.
- Evidence: `docs/operations/wi-039-s03-ecos-source-sampling-2026-09.md`.
- Result: `WI-039-S03` is closed. Parent `WI-039` and MS-003 remain proposed; exact-series owner review and S04
  canonical adoption remain. No code, DDL, DB, infrastructure, schedule, contract lifecycle or MCP change occurred.

## Canonical adoption checkpoint — 2026-09-02

- The owner approved S04 after reviewing the complete design and exact ECOS identities.
- ADR-027, requirements and V2 system design now own the exact profile, heterogeneous revision clocks, five transparent
  metrics, migration 0016 boundary, call/capacity budgets and shared-implementation constraint.
- DGH now registers 17 exact `macro_series` contracts, all `approved + inactive`, and cross-checks collection/pipeline
  source coverage and duplicate provider identity.
- Existing contracts were upgraded to FRED/ALFRED 1.1, dormant Cboe reference 1.1, collection 2.0, observation dataset
  2.0 and pipeline 2.0. A Gold profile snapshot and five approved metrics were added.
- Evidence: `docs/operations/wi-039-s04-contract-adoption-2026-09.md`.
- Result: `WI-039-S04` is closed. Parent `WI-039` and MS-003 remain proposed; implementation and every external or
  production mutation remain gated. No DDL, DB, credential, infrastructure, source call, schedule, deployment or MCP
  activation occurred.

## Isolated implementation verification — 2026-09-10

- The exact 17 approved-inactive series project into immutable Control definitions. Unknown series and source calls
  fail closed before any I/O.
- Additive migration 0016 adds an append-only heterogeneous revision ledger, current/system-as-of projections and an
  immutable Gold profile snapshot. A non-empty legacy foundation aborts migration without adopting or deleting rows.
- Synthetic FRED/ALFRED fixtures preserve provider vintage intervals. Synthetic ECOS fixtures append observed-content
  revisions without fabricating provider realtime intervals; retrospective source-as-of is therefore unavailable and
  labeled rather than silently substituted.
- Missing provider markers remain null with an explicit reason. Five approved Decimal metrics have deterministic
  missing/denominator and regime boundary behavior.
- Routine/backfill physical-call ceilings, ten-page partition caps, 80% capacity review thresholds, hard stop lines,
  passing-quality-only watermarks and monotonic cursor checks are implemented as inactive planning guards.
- Governed Parquet export and fresh local DuckDB restore reproduce the new tables and compile both macro views.
- Evidence: `docs/operations/wi-039-isolated-verification-2026-09.md`.
- Result: parent `WI-039` is `verified` in `execution_scope: isolated`, `production_effects: none`. No production DB,
  source, credential, infrastructure, schedule, public MCP, Telegram, cleanup or cutover effect occurred.
