---
id: WI-016
title: Correct broker history semantics and append reversible trade corrections
status: in_progress
type: defect
owner: owner
decision_refs: ADR-021, ADR-023, V2-ADR-006, V2-ADR-010, V2-ADR-012
requirement_refs: DEC-009..014, DEC-030, DEC-041, DEC-044
architecture_impact: corrects source adapters and V2 event identity without changing approved ledger boundaries
data_impact: additive correction evidence; polluted source rows are retained and never silently rewritten
security_impact: confidential broker rows remain in governed Bronze and Silver; evidence is aggregate only
cost_impact: bounded three-year correction reads under existing scale-to-zero batch assumptions
---

# WI-016 — Correct broker history semantics and append reversible trade corrections

## Problem and evidence

Read-only readiness audit found three source-contract defects: overseas period transactions are returned in `output1`
but current normalization reads `output2`; domestic history still uses one outdated recent TR without old-range routing or
continuation keys; and the V1→V2 lot migration labels every filled domestic order as `buy`, including sells.

## Classification and contract

- Classification: `defect` against approved DEC-010 through DEC-014 and `dataset.trade-event`.
- Official domestic side codes remain `01=sell`, `02=buy`; unknown values fail closed.
- Source events remain immutable. Corrections append evidence/version state and do not delete or update polluted rows.
- Overseas cash/transaction rows remain distinct from order events; candidate links are reversible.

## Scope

- Include: domestic recent/old TR routing and bounded pagination, side normalization, overseas `output1` and official
  source price/fee/FX/settlement fields, additive V2 correction schema, migration dry-run and limited correction evidence.
- Exclude: inferred opening lots, FIFO sell allocation, metric activation, Telegram and arbitrary Remote MCP backfill.

## Acceptance criteria

- [ ] domestic recent/old endpoint, TR ID and FK/NK continuation contracts have deterministic fixtures.
- [ ] official side codes produce buys and sells; unknown codes never create a purchase lot.
- [ ] overseas transactions normalize from `output1` with execution price, fee, FX and settlement provenance.
- [ ] V2 trade natural identity includes market/product/execution dimensions needed to avoid false collisions.
- [ ] existing polluted rows remain preserved and corrections are append-only, versioned and reversible.
- [ ] production correction dry-run reports affected rows without confidential values.
- [ ] limited production correction passes aggregate reconciliation, backup/restore and full Project OS gates.

## Change impact

- Architecture/data: additive migration and governed correction pipeline; no V1 destructive rewrite.
- Security/cost: aggregate-only evidence and bounded KIS reads; no new secret or always-on service.
- Rollback: disable correction writer/read projection; retain raw and correction rows for audit.
- MCP compatibility: existing response fields remain; corrected row counts and side semantics may change.

## Plan

1. Freeze official domestic/overseas response and continuation fixtures.
2. Correct adapters and normalization with fail-closed side rules.
3. Add correction/version schema and migration logic without rewriting source rows.
4. Run local reconciliation, production dry-run, bounded correction and recovery gates.

## Evidence

- Read-only readiness audit: `docs/design/milestone-2-data-readiness-review.md`.
- Commands/tests: pending.

## Closeout

- Result: in progress.
- Remaining risk: IRP recent-period source gap remains provisional by approved DEC-011.
- Follow-up Work Item: WI-017 held-instrument classification and rights-gated ETF connector fixtures.
