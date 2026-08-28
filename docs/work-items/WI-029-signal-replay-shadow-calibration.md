---
id: WI-029
title: Calibrate signals with replay and shadow evaluation
status: in_progress
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

- `WI-029-S01`: freeze bootstrap rule and replay/report contracts.
- `WI-029-S02`: implement deterministic replay, asset-class calibration and tests.
- `WI-029-S03`: audit live eligibility and execute only a bounded, provenance-labelled replay.
- `WI-029-S04`: activate DB-only shadow schedules with external delivery impossible.
- `WI-029-S05`: collect two elapsed weeks of evidence and record owner rule-version approval.

## Evidence

- Activated after WI-028 merged as PR #25 (`a9dc2ccd96660be2b4f89e4b95e50e2a0efb9d46`).
- `WI-029-S01` closed: bootstrap severity, stateful budget, provenance, coverage and owner-review contracts are frozen in
  `docs/design/wi-029-signal-replay-shadow-contract.md`.
- `WI-029-S02` closed: deterministic pure replay, per-class multiplier calibration, immutable evidence repository and
  local golden tests are implemented.
- `WI-029-S03` closed: bounded aggregate-only live audit and reconstructed replay are recorded in
  `docs/operations/wi-029-replay-readiness-2026-08.md`. The official-evidence replay hash is
  `a9048d06d758d5923899f15f2a6a034e9bb5f2b7e9efc2844706df6ebf13dc8d`; no DB or external-send write occurred.
- `WI-029-S04` closed: the three existing scale-to-zero jobs land operational-strict
  raw/adjusted bars and compose KR slots plus morning U.S. close shadow evaluation; the morning job resolves only
  current overseas unknown holdings through bounded KIS+SEC evidence. The `wi029-s04` target enforces migration 0013,
  one initial morning run, zero external transport and private GCS backup/download/fresh restore. Live execution
  evidence is recorded in `docs/operations/wi-029-shadow-activation-2026-08.md`: PRs #26/#27 and deployment runs
  `33180964201`/`33182018996` completed; the first shadow evaluation produced 18 quality-suppressed candidates, zero
  transitions and zero external sends, while the final recovery check restored all 58 governed tables. The approved
  replay hash is persisted once and the 2026-08-28 through 2026-09-10 shadow window is `collecting`.
- `WI-029-S05` is active. It is an elapsed-time and owner-review gate, not an implementation shortcut: scheduled
  session evidence must accumulate through 2026-09-10 before reconciliation and explicit owner approval.

## Closeout

- Result: in progress; S01-S04 are closed and S05 is collecting elapsed evidence.
- Remaining risk: reconstructed-history bias.
- Follow-up Work Item: WI-030.
