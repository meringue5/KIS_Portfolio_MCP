---
id: WI-014
title: Re-sequence Milestone 2 from production data readiness
status: closed
type: clarification
owner: owner
decision_refs: ADR-021, ADR-023, V2-ADR-006, V2-ADR-010, V2-ADR-012
requirement_refs: DEC-015..019, DEC-026, DEC-038, DEC-041, DEC-044
milestone_ref: MS-002
delivery_refs: none
parent_work_item: none
depends_on: WI-013
architecture_impact: orders approved work by upstream data readiness without changing the target architecture
data_impact: aggregate inventory audit only; no production row or schema mutation
security_impact: only non-sensitive counts and contract states may be recorded
cost_impact: no new runtime service or collection call
---

# WI-014 — Re-sequence Milestone 2 from production data readiness

## Problem and evidence

WI-013 made deterministic point-in-time metric evaluation possible, but a formula implementation can still be only a
synthetic fixture if its governed upstream data is missing, mislabelled or too short. The next production Work Item
must therefore be selected from verified data readiness rather than the nominal Wave 5 list alone.

## Classification and contract

- Classification: `clarification` of implementation order, not a change to approved requirements or architecture.
- Approved formulas, ETF source hierarchy, three-year replay and Telegram shadow gates remain unchanged.
- This Work Item is read-only with respect to MotherDuck, GCP, KIS and Telegram.

## Scope

- Include: non-sensitive live aggregate inventory, code/contract inspection, dependency ordering and fixture-only
  boundaries for V2-W0502 through V2-W0505.
- Exclude: source activation, backfill, schema migration, metric implementation, secret payload access and Telegram send.

## Acceptance criteria

- [x] each W0502-W0505 family has a production readiness verdict and explicit blockers.
- [x] synthetic-only work is distinguished from production-ready work.
- [x] prerequisite and metric Work Items are ordered so data provenance is not retrofitted after calculation.
- [x] Telegram onboarding and delivery remain separately gated with no external call.
- [x] Project OS quick gate passes with no other active implementation Work Item.

## Change impact

- Architecture/data: no target contract or production object changes; delivery order becomes evidence-driven.
- Security/cost: aggregate read-only inspection only; no secret payload, source call or external message.
- Rollback: remove the clarification if its evidence is invalidated; approved requirements remain intact.

## Plan

1. Audit W0502-W0505 live aggregate coverage and current code semantics.
2. Separate fixture-ready from production-ready scope and document hard blockers.
3. Order independent prerequisite Work Items and the metrics that consume them.
4. Record Telegram safety research without crossing the external-send gate.

## Sub-items

- `none`.

## Evidence

- `docs/design/milestone-2-data-readiness-review.md` records non-sensitive live aggregate coverage and the selected
  prerequisite order.
- Six read-only research tracks covered formula fixtures, live readiness, Telegram safety, dual-basis price history,
  official ETF source rights and cash/trade reconstruction.
- No KIS source call, Telegram API call, external message, secret payload read, infrastructure mutation or production
  DB write was performed.
- The review found and recorded three blockers before downstream use: nullable unavailable metric outcomes (corrected
  in WI-013), recurrent adjusted-price mislabelling and the all-buy trade migration defect.
- ETF public availability was separated from automation/retention rights; KRX website scraping is prohibited and
  issuer connectors remain fail-closed until provider-specific approval.
- Project OS quick gate passed with exactly one active Work Item during review.

## Closeout

- Result: W0502-W0505 remain fixture-ready but production no-go; prerequisite order and safety gates are explicit.
- Follow-up Work Item: dual-basis, revision-aware price ledger and bounded reconstructed three-year backfill.
