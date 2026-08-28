# WI-025 — Lot, episode and thread risk metric contract

## Metric boundary

W0504 V1 publishes three related but distinct products:

1. purchase-lot adjusted-price path: MFE and MAE from the lot's effective unit cost through its own episode/close
   cutoff;
2. position-episode path: adjusted episode high and current drawdown, with no prices after an episode returns to zero;
3. owner-plan risk: open quantity by thread, planned loss in KRW and risk ratio, plus reconciled instrument totals.

```text
lot_mfe = max(adjusted_high / adjusted_entry_cost - 1)
lot_mae = min(adjusted_low / adjusted_entry_cost - 1)
episode_high = max(adjusted_high)
episode_drawdown = last_adjusted_close / episode_high - 1
thread_planned_loss_krw = open_quantity * (reference_price - stop_price) * point_in_time_fx
thread_risk_ratio = thread_planned_loss_krw / canonical_total_assets_krw
```

The long-position owner plan contract requires `stop < reference`. ATR20 `2N` remains suggestion metadata and never
produces an official planned-loss value when the owner stop is missing. These metrics do not claim a thread investment
return: additions and partial exits affect the selected point-in-time open quantities, while a future cash-flow-adjusted
thread-return product would require its own explicit formula contract.

## Publish gates

- episode and lot revisions are selected only from facts known and effective by the evaluation cutoff;
- reconstruction and lot quality pass, and lot remaining quantities reconcile exactly to each episode quantity;
- open episode quantities reconcile to the same-slot canonical Gold position quantities and required account coverage;
- every open lot belongs to exactly one current thread for official thread/instrument aggregation;
- adjusted price revisions are `operational_strict`, pass, and bounded by the lot/episode lifecycle;
- the owner-authoritative risk plan, point-in-time FX and complete positive canonical total assets are present;
- an instrument total is numeric only when every open thread underneath it is numeric and quantities reconcile.

Any missing or partial input creates a nullable metric value with a specific quality status. Closed episode paths stop
at `closed_at`; a later position episode for the same instrument starts a new high-water path.

## Persistence and activation

Eight approved metric contracts reuse `control.metric_definitions` and `gold.metric_values`; there is no migration.
Exact replay is a no-op and conflicts fail. This Work Item adds no source call, production schedule, MCP surface,
Telegram delivery or order capability. Production numeric publication remains unavailable until reconstruction,
owner-plan, price, FX and canonical-state coverage pass together.
