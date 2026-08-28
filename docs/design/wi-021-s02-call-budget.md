# WI-021-S02 — Call and Page Budget Contract

## Scope

This sub-item instantiates the approved `pipeline.owned-portfolio-core-v2` source-call budget for the WI-021 trade
and cash backfill. It adds deterministic preflight reservation and a physical-call guard. It does not add source
adapters, resume state, warehouse writes, reconciliation or production execution.

The budget is a public, versioned contract containing only source operation names and integer ceilings. Partition
identity continues to come from WI-021-S01; applying a budget creates a separate `budget_hash`, so changing an
operational ceiling never reinterprets a source partition or checkpoint.

## Default policy

| Source operation | Page budget per 60-day partition | Reason for bounded default |
| --- | ---: | --- |
| domestic order history | 3 | at most 300 order aggregates under the verified 100-row page contract |
| overseas order history | 3 | at most 60 order aggregates under the verified 20-row page contract |
| overseas period transaction | 2 | sparse owner history, while retaining a second continuation page |
| global physical calls | 400 | same bounded one-off ceiling used by the approved price backfill |

The limits are safety ceilings, not completeness assertions. If KIS advertises another page after the partition
limit, the next call is rejected and later quality/reconciliation work must publish the partition as incomplete. The
implementation never treats a capped response as complete merely because rows were returned.

For the deterministic five-account `2023-08-28..2026-08-28` plan, preflight reserves:

```text
domestic order       93 partitions × 3 pages = 279
overseas order       19 partitions × 3 pages =  57
overseas transaction 19 partitions × 2 pages =  38
                                                   ---
reserved worst case                               374 / 400
headroom                                            26
```

Known-gap partitions reserve zero calls.

## Fail-closed sequence

1. Build and hash the complete S01 source plan.
2. Normalize the budget policy; reject invalid IDs, versions, duplicate/unknown sources, non-positive limits and
   limits over the application source-helper cap of ten pages.
3. Reserve the worst-case page allowance for every callable partition. If the complete reservation exceeds the
   global ceiling, fail before constructing a call gate.
4. Immediately before each physical source request, `BackfillCallBudget.reserve(partition_key)` atomically reserves
   one partition page and one global call.
5. Unknown partition keys, named gaps, page exhaustion and global exhaustion raise before the physical callable is
   invoked. Failed network attempts still consume the reservation because a physical request was attempted.

`run_budgeted_physical_call` is the only S02 call wrapper. Tests prove that the physical callable is not invoked after
budget exhaustion. Its callable must represent exactly one low-level HTTP request; wrapping an existing
`inquery_*` helper is prohibited because those helpers may paginate internally. The later executor Work Item must
either inject this guard immediately around `request_kis` or provide a one-page fetcher that uses it.

## CLI and evidence boundary

`plan-trade-cash-backfill-v2` now applies the default budget and returns `budget_enforced=true`, the policy/hash,
partition page budgets, reserved ceiling and headroom. Operators may lower or raise individual limits only within the
hard ten-page application cap; a global ceiling too small for the complete plan exits fail-closed.

```bash
uv run kis-portfolio-batch plan-trade-cash-backfill-v2 \
  --start-date 20230828 --end-date 20260828 --as-of-date 20260828 \
  --max-physical-calls 400 \
  --domestic-order-pages 3 \
  --overseas-order-pages 3 \
  --overseas-transaction-pages 2
```

No database object, secret, schedule, provider or infrastructure is added. Resume/checkpoint persistence and actual
source execution remain outside WI-021-S02.
