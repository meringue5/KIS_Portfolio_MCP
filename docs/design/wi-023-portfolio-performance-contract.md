# WI-023 — Portfolio performance contract

## Formula boundary

For one governed prior/current portfolio state pair, beginning market value is `BMV`, ending market value is `EMV`
and signed external owner cash flows are `CF_i`. A deposit is positive and a withdrawal is negative. For a flow
effective at `t_i` inside `[start, end]`, `w_i = (end - t_i) / (end - start)`.

```text
denominator = BMV + sum(w_i * CF_i)
return = (EMV - BMV - sum(CF_i)) / denominator
component contribution_j = (EMV_j - BMV_j - sum(CF_ij)) / denominator
residual = return - sum(component contribution_j)
```

All ratio outputs use `DECIMAL(38,10)` half-even rounding. The residual is stored as a metric and must be within
`0.0000000001`. Owner cash flows are assigned only to the consolidated `cash|currency` component. Internal transfer,
trade settlement and FX legs are not external capital; fee, tax, dividend and interest remain investment performance.
Unknown classifications, unreconciled internal legs and unsupported non-KRW owner flows make the period unavailable.
Component contribution explains each component's share of total cash-flow-adjusted portfolio change, including
allocation changes caused by trading. It is not a pure security price-return attribution or the separate WI-033 KRW
valuation-change contribution.

## Wealth and drawdown

The first state has wealth base `1`. Each passing period applies `wealth_t = wealth_(t-1) * (1 + return_t)`.
High-water is the running maximum of this wealth series and `drawdown_t = wealth_t / high_water_t - 1`. A missing or
non-pass return breaks the chain. A later passing period does not silently restart at 1. Total-asset KRW peaks are not
used because deposits and withdrawals would distort them.

## Publish gates

The evaluator publishes numeric W0502 metrics only when all of the following are true:

1. both daily states exist at the same slot, contain only pass rows and cover the same complete active-account scope;
2. `main.market_calendar` covers every intervening date and the current state is the next open KRX session;
3. one named `control.quality_results` record proves cash-event coverage for the exact time range and hashed account
   scope;
4. the point-in-time cash classification known by the current cutoff is pass and not `unknown`;
5. owner-flow signs and currencies are valid and the Dietz denominator is non-zero;
6. component contributions plus residual reconcile to the return tolerance.

Failure creates nullable metric outcomes with an explicit quality status. It never interprets an empty cash-event
table as proof of zero cash flows, uses a future classification, converts foreign cash with a current-only FX row,
or restarts a broken wealth chain.

## Persistence and compatibility

The five versioned contracts use the existing `control.metric_definitions` and `gold.metric_values` objects. Exact
replay is a no-op; a different value or lineage for the same logical key fails. The repository read model requires an
explicit metric version and is compared with independent DuckDB SQL fixtures. Existing V1 `main.asset_return_daily`
remains unmanaged drift and is neither repaired nor adopted by WI-023.

This Work Item adds no migration, source call, Cloud Run target, Scheduler, public MCP tool, alert threshold or
Telegram delivery. Production evaluation remains gated by actual cash coverage and state continuity evidence.
