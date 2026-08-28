---
id: WI-017
title: Classify held instruments and establish rights-gated ETF routing
status: closed
type: defect
owner: owner
decision_refs: ADR-023, V2-ADR-006, V2-ADR-010, V2-ADR-012
requirement_refs: DEC-005, DEC-018, DEC-019, DEC-030, DEC-041, DEC-044
milestone_ref: MS-002
delivery_refs: V2-W0405, V2-W0505
parent_work_item: none
depends_on: WI-014, WI-016
architecture_impact: adds point-in-time instrument versions and exact ETF provider routing without enabling external collection
data_impact: additive classification/version and routing state; current compatibility table remains intact
security_impact: route registry is public instrument metadata only; account and holding facts are prohibited
cost_impact: local fixture-only pipeline and scale-to-zero database migration; zero issuer network calls
---

# WI-017 — Classify held instruments and establish rights-gated ETF routing

## Problem and evidence

The V2 owned-portfolio adapter currently publishes every held instrument with `asset_type=unknown`, while the logical
instrument-master contract requires versioned classification. ETF issuer selection has no executable exact route and
provider rights are not machine-gated, so a generic heuristic or network connector would be unsafe.

## Classification and contract

- Classification: `defect` against `dataset.instrument-master` and prerequisite implementation for
  `pipeline.etf-lookthrough-v2`.
- Classification precedence is valid owner override, explicit KIS/reference master, conservative type evidence, then
  unknown. Economic exposure remains separate and is not inferred from a product name.
- Issuer routing is exact-instrument allowlist only; brand/name heuristics cannot select a provider.
- Provider rights use `allowed`, `prohibited` or `unknown`. Production activation fails unless automation, cloud
  processing, raw retention and derived use are all allowed.

## Scope

- Include: canonical instrument helper, point-in-time instrument versions, current compatibility projection, governed
  provider profiles and exact routes, four provider-specific synthetic parsers, offline fixture pipeline and tests.
- Exclude: issuer/KRX network calls, real provider payloads, Cloud Run Job/Scheduler activation, constituent backfill,
  metric activation and Telegram.

## Acceptance criteria

- [x] current held instruments resolve through governed precedence and unknown quality remains explicit.
- [x] instrument versions are point-in-time, replay-idempotent and reject overlapping conflicting intervals.
- [x] exact ETF routes contain no account, quantity or valuation data and have valid profile/product-key references.
- [x] unknown/prohibited rights structurally block production adapter registration.
- [x] TIME, KoAct, RISE and PLUS synthetic fixtures parse through provider-specific offline adapters.
- [x] malformed/incomplete inputs fail or remain partial; KIS composition cannot be a completeness fallback.
- [x] additive migration, catalog, backup/restore and full Project OS gates pass.
- [x] production classification/routing migration and held-scope reconciliation complete without external issuer calls.

## Change impact

- Architecture/data: additive Silver version ledger and Control route projection; `silver.instruments` remains a current
  compatibility table.
- Security/cost: public route metadata only and zero provider calls; no new secret or always-on runtime.
- Rollback: stop the offline pipeline/read model and retain version/route evidence; no destructive V1 rewrite.
- MCP compatibility: none; no public tool is added.

## Plan

1. Register rights-aware provider profiles and exact held-instrument route contracts.
2. Add canonical identity, classification domain and point-in-time repositories.
3. Add four provider parsers with synthetic fixtures and an offline-only pipeline.
4. Apply the additive migration, reconcile held scope, verify backup/restore and close.

## Sub-items

- `none`. Follow-up rights activation is WI-026; WI-017 identity and outcome remain closed.

## Evidence

- Read-only readiness audit: `docs/design/milestone-2-data-readiness-review.md`.
- `bash scripts/check.sh full`: 248 tests passed before production apply; all Project OS contract gates passed.
- Production dry-run/apply: 18 held instruments, 14 ETF and four explicit unknown; 18 versions and 14 exact routes.
- Rights gate: four fixture-only profiles and zero production network profile.
- Recovery evidence: `docs/operations/milestone-2-instrument-etf-routing-2026-08.md`.

## Closeout

- Result: closed. Migration 0007, point-in-time classification and fixture-only exact ETF routing are live.
- Remaining boundary: every provider remains fixture-only until a separate rights approval activates it.
- Follow-up Work Item: W0503 trend/volatility metrics against the corrected price ledger.
