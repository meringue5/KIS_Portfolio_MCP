---
id: WI-029
title: Calibrate signals with replay and shadow evaluation
status: proposed
type: change
owner: owner
decision_refs: ADR-021, ADR-023, V2-ADR-007, V2-ADR-010, V2-ADR-012
requirement_refs: DEC-026..028, DEC-038, DEC-041, DEC-044
milestone_ref: MS-002
delivery_refs: V2-W0509
parent_work_item: none
depends_on: WI-028
architecture_impact: validates approved rule versions without changing transport boundaries
data_impact: replay reports shadow candidates threshold versions and quality evidence
security_impact: DB-only shadow with no external message
cost_impact: bounded three-year replay and three daily scale-to-zero shadow evaluations
---

# WI-029 — Calibrate signals with replay and shadow evaluation

## Problem and evidence

Alert thresholds must be tested against reconstructed history and observed in production-like shadow mode before the
owner can approve external delivery.

## Classification and contract

- `change` implementing V2-W0509.
- Reconstructed history calibrates but never impersonates historical live knowledge.

## Scope

- Include three-year replay, asset-class calibration, false-positive/miss review and two-week DB-only shadow.
- Exclude Telegram transmission.

## Acceptance criteria

- [ ] daily alert budget, maximum miss and quality limitations are documented.
- [ ] two-week shadow completes without external send and de-duplication is evidenced.
- [ ] owner approves the selected rule version before WI-030 becomes ready.

## Change impact

- Bounded analytical runs and shadow schedules only; transport disabled.

## Plan

1. Replay versioned rules over eligible history.
2. Calibrate by stock/ETF/REIT/leverage class.
3. Run and review two-week shadow evidence.

## Sub-items

- `none`.

## Evidence

- Pending.

## Closeout

- Result: proposed; depends on WI-028 and elapsed shadow evidence.
- Remaining risk: reconstructed-history bias.
- Follow-up Work Item: WI-030.
