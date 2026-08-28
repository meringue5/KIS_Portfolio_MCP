# WI-021-S01 — Trade and Cash Backfill Partition Plan

## Decision status and scope

This design implements the planning-only sub-item of WI-021 against approved
`collection.owned-portfolio-core-v1`, `dataset.trade-event`, `dataset.cash-transaction-event` and
`pipeline.owned-portfolio-core-v2`. It does not call KIS, write a database, enforce a run budget, create a resume
claim or perform a production backfill.

The planner accepts only public account capabilities: account label, product code, real/virtual profile and the
explicit overseas exchanges enabled for that account. App keys, secrets and account numbers are neither inputs to
partition identity nor outputs of the plan.

## Partition contract

The default shard is 60 inclusive calendar days, with a hard design maximum of 90. Sixty days follows the
live-verified safe overseas history probe and is also a conservative interpretation of the domestic old-history
guidance to use short post-close ranges. Shards cover the requested range exactly, with no overlap or missing date.

| Source operation | Account scope | Route boundary | Outputs | Planning disposition |
| --- | --- | --- | --- | --- |
| domestic order history | every configured account | split at `as_of_date - 90 days`; a shard never crosses old/recent | trade event | callable, except IRP recent |
| overseas order history | explicitly enabled overseas account/exchange | 60-day shards | trade event | callable |
| overseas period transaction | explicitly enabled overseas account/exchange | 60-day shards | trade and cash event candidates | callable for real account; virtual support is a named gap |
| domestic cash history | every configured account | full requested range | cash event | named gap until an approved source exists |

IRP product code `29` recent history is one `known_gap` partition with reason
`irp_recent_history_endpoint_unavailable`. It is not replaced by a balance-derived transaction. Domestic order rows
do not expose an approved cash-transaction history, so each account also carries
`no_selected_domestic_cash_transaction_history_source`. Overseas orders and overseas period transactions remain
separate immutable source streams; the planner does not join them.

Each key is stable and non-secret:

```text
1.0.0|<source-operation>|<account-label>|<product-code>|<account-type>|<exchange-or-KRX>|<source-route>|<start>|<end>
```

Product code and real/virtual profile are included because they change the KIS source route even when the human label
does not. Stable keys are the future resume unit. Changing the key grammar requires a plan-version change rather than
silently reinterpreting existing checkpoints.

## Deterministic reference plan

For `2023-08-28..2026-08-28`, as-of `2026-08-28`, five configured accounts and `brokerage/NAS`, the default plan is:

| Measure | Count |
| --- | ---: |
| all partitions | 137 |
| callable partitions | 131 |
| named gaps | 6 |
| domestic order callable | 93 |
| overseas order callable | 19 |
| overseas period-transaction callable | 19 |
| domestic cash-source gaps | 5 |
| IRP recent-order gap | 1 |

The plan reports 131 minimum physical calls and a deliberately pessimistic 1,310-call page-cap projection based on
the existing ten-page source helper. These are planning facts, not an approved execution budget. A later sub-item must
set per-source/page/global ceilings, reserve them before calls and fail closed when the approved budget is exceeded.

## Invariants and next boundary

- A requested window cannot exceed three calendar years or end after its explicit as-of date.
- Input order, duplicate exchange spelling and credential values cannot change the plan.
- A callable partition is at most 60 days by default and 90 days by contract.
- Known gaps consume zero projected source pages and stay visible in the public plan.
- The planner has no source client, warehouse connection or mutation path.
- Call-budget enforcement, managed-run evidence, resume/checkpoints, normalization, reconciliation and live approval
  are intentionally deferred beyond WI-021-S01.

The read-only command is:

```bash
uv run kis-portfolio-batch plan-trade-cash-backfill-v2 \
  --start-date 20230828 --end-date 20260828 --as-of-date 20260828
```

It prints the complete public partition manifest and performs no external request or database write.
