# WI-033 Total-Asset Valuation-Change Contract

## Purpose

This contract explains a point-to-point change in total KRW valuation. It is not investment-return attribution.
For foreign holdings, price and exchange-rate effects remain combined and the public label is
`KRW valuation change including FX`.

The transition V1 `get-total-asset-daily-change` response and the V2 governed projection use the same application
calculation. V1 keeps all existing aggregate fields and adds `valuation_change_contribution`; V2 persists the approved
metric in the existing `gold.metric_values` ledger.

## Grain and formulas

The comparison grain is `(previous canonical daily state, current canonical daily state, instrument)`. Holdings with
the same governed instrument identity are consolidated across accounts. A caller may request an account breakdown,
but only configured account labels are emitted; raw account identifiers are never returned.

- `valuation_change_krw = current_value_krw - previous_value_krw`
- `total_asset_impact_pct = valuation_change_krw / previous_total_asset_krw * 100`
- `share_of_total_change_pct = valuation_change_krw / total_asset_change_krw * 100`
- `explained_change_sum_krw = holding_change_sum_krw + cash_change_krw`
- `unexplained_residual_krw = total_asset_change_krw - explained_change_sum_krw`

If a denominator is zero, the percentage is `null` with an explicit unavailable reason. Reconciliation tolerance is
the larger of KRW 1 and one part per million of the compared total-asset values.

## Comparability and fail-closed behavior

New-position and fully-sold inference is enabled only when all of the following hold:

1. both snapshots are complete and quality `pass`;
2. both snapshots declare the same required account coverage;
3. observed coverage equals required coverage on both days; and
4. holdings plus cash reconcile to the canonical total within tolerance.

When any gate fails, the response is `degraded`, blockers are returned, and new/sold flags are `null`. Diagnostic
previous/current/change values may still be shown so an operator can investigate. They are not an official metric:
the V2 evaluator stores a row with `value_decimal = NULL` and explicit quality instead of publishing a plausible
number. Replay uses the existing metric-ledger identity, so the same point-in-time evaluation is idempotent.

## Sources and persistence

- V1 source: the two latest rows of `asset_overview_daily_snapshots` plus their `asset_holding_snapshots` children.
- V2 source: adjacent governed `gold.portfolio_daily_state` evaluations and Silver instrument/account dimensions.
- V1 write behavior: none; the MCP read is DB-only.
- V2 write behavior: approved `metric.total-asset-valuation-change-contribution-krw` values in the existing
  `gold.metric_values` and definition in `control.metric_definitions`.
- Physical objects: none added. `asset_overview_snapshots` quality columns become managed by the V1 schema and writer.

Rollback removes the additive MCP field and V2 evaluator consumer. Canonical snapshots and metric-ledger history are
retained; no destructive migration is required.
