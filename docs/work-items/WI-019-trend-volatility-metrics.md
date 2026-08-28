---
id: WI-019
title: Implement replay-safe trend and volatility metrics
status: closed
type: change
owner: owner
decision_refs: ADR-021, ADR-023, V2-ADR-006, V2-ADR-010, V2-ADR-012
requirement_refs: DEC-015..017, DEC-026, DEC-038, DEC-041, DEC-044
milestone_ref: MS-002
delivery_refs: V2-W0503
parent_work_item: none
depends_on: WI-013, WI-015
architecture_impact: implements approved Gold metrics on the existing point-in-time engine
data_impact: versioned SMA, volume, RSI, Bollinger and ATR metric values
security_impact: confidential derived values remain in MotherDuck; no external delivery
cost_impact: scale-to-zero batch computation over the bounded held-instrument price ledger
---

# WI-019 — Implement replay-safe trend and volatility metrics

## Problem and evidence

The corrected dual-basis price ledger is live, but approved SMA20/50/120, volume ratio, RSI14, Bollinger context and
ATR20 are not yet calculated by the governed metric engine.

## Classification and contract

- `change` implementing approved V2-W0503 after WI-013 and WI-015.
- Adjusted daily bars drive trend/path metrics; slot quotes remain separate shock inputs.
- Missing history yields explicit unavailable/partial quality, never neutral values.

## Scope

- Include metric contracts, independent SQL/Python golden fixtures, point-in-time evaluation and persistence.
- Exclude alert thresholds, Telegram and source/backfill changes.

## Acceptance criteria

- [x] SMA20/50/120, volume ratio, RSI14, Bollinger context and ATR20 match independent fixtures.
- [x] reconstructed history cannot impersonate strict historical knowledge.
- [x] quality, lineage, backup/restore and full gates pass.

## Change impact

- Existing Gold metric boundary only; no provider, MCP or external-send change.

## Plan

1. Freeze formulas and metric versions.
2. Implement reference fixtures and evaluator paths.
3. Verify point-in-time, quality and recovery behavior.

## Sub-items

- `none`.

## Evidence

- Eleven approved metric contracts cover adjusted-close SMA20/50/120, vendor-volume SMA/ratio20, Wilder RSI14,
  Bollinger lower/upper/percent-B/bandwidth with population standard deviation and Wilder ATR20.
- The application evaluator selects revision-aware adjusted bars at the strict knowledge cutoff and writes the
  existing versioned Gold metric ledger with exact input refs, definition/formula hashes and lineage.
- Missing history/fields, non-pass inputs, zero denominators and retrospective reconstruction persist as null plus
  explicit quality rather than zero or neutral official results.
- Independent DuckDB `avg/stddev_pop` fixtures and independently coded Python Wilder recurrences match the Decimal
  production formulas; a future revision cannot alter a past evaluation.
- Focused tests: 14 passed. `bash scripts/check.sh quick`: passed. `bash scripts/check.sh full`: 262 passed with
  one third-party Authlib deprecation warning. Existing metric-value/definition Parquet recovery coverage remains green.

## Closeout

- Result: closed; replay-safe trend and volatility metric calculation and persistence are implemented locally.
- Remaining risk: production replay and threshold calibration belong to WI-029.
- Follow-up Work Item: WI-021 is now dependency-ready; WI-029 remains downstream of alert-state work.
