# WI-068 — V1 Cloud batch provenance follow-up, 2026-10-13

## Result

The owner correctly recalled separate Google Cloud batch execution and tables accumulated before V2.
The pre-V2 documents and current preserved resources identify **three V1 batches**. Their code collects domestic
orders, overseas transactions and token/health warm-up; **none of these three commands collects account balance or
portfolio total snapshots**. A fourth total-asset collector exists in a retained branch, but its deployment/execution
was not established. This is a reconciliation of observed records, not a conclusion that the owner never ran any
other program.

Daily total assets remain the first recovery objective. Existing totals are retained and useful as scoped source
observations. The investigation must not confuse `order_history` query snapshots with `portfolio_snapshots`, or an
execution's terminal success with complete daily total-asset coverage.

[Sanitized provenance evidence](../../governance/project/evidence/wi068/v1-batch-provenance-2026-10-13.json) contains
aggregate audit outcomes, non-secret commands/DB routing, table periods and GitHub source checks; no raw payload,
account identifier, token, backup URI or endpoint URI is included.

## Before-V2 documents located

- [V2 system design](../design/kis-portfolio-v2-system-design.md), section 2, records the 2026-08-27 inspection:
  three Jobs, domestic-order/overseas-transaction/token batch commands; 07:35/08:30/15:35 enabled schedules;
  retained `main` 27 tables + 3 views, with known drift.
- [Cost baseline](cost-baseline-2026-08.md), Cloud Run Jobs and MotherDuck sections, records three Jobs and
  `MOTHERDUCK_DATABASE=kis_portfolio` on MCP/auth/all three batches; known `my_db` is empty.
- [MotherDuck V2 foundation](motherduck-v2-foundation-2026-08.md) records preserved pre-migration counts:
  portfolio 267, overseas feeder 48, domestic-order raw 56, overseas-transaction raw 58, price 838, FX 100.
- [Data pipeline](../data-pipeline.md), raw snapshots and order dedup sections, explains that scheduled order
  collection stores query envelopes and normalized orders, while portfolio snapshots are balance observations.

The earlier documents do indeed contain the batch/table evidence requested by the owner. They do not establish a
pre-July daily total-asset collector. Existing inventory checks show the compared V1 snapshot/overview/holding rows
are preserved, so sparse coverage cannot be attributed to WI-066's view-only quarantine or V2 deletion.

## Actual V1 jobs, table routing and retained outcomes

| V1 job / command | creation (KST) | tables written / purpose | retained terminal audit, Apr 1–Aug 27 KST |
| --- | --- | --- | --- |
| `kis-portfolio-domestic-order-history` / `collect-domestic-order-history` | Apr 23 22:41 | `main.order_history`, `main.domestic_orders`; order/execution history, not asset totals | 9 success records; 82 failed records (status code 10) |
| `kis-portfolio-overseas-transaction-history` / `collect-overseas-transaction-history` | May 15 23:13 | `main.overseas_transaction_history`, `main.overseas_transactions`; transaction envelopes/normalization | 57 success; 17 failed |
| `kis-portfolio-token-warmup-dry-run` / `warm-token-cache` | May 15 23:55 | token cache/health warm-up; no analytical total-asset rows | 65 success; 10 failed |

The complete paginated audit query returned **313 records**, including administrative events and terminal records.
They concern these three job names and Seoul region. A separate complete July-only query confirms domestic
failed 23, overseas succeeded 18/failed 5, token warm-up succeeded 23 terminal records. Failure messages identify
failed executions but do not establish the application exception that caused them. Historic CreateJob audit contains
job identity but not full container/env configuration; historical command/routing is corroborated by the pre-V2
runtime inspection, deployment source and current preserved definitions. Counts above are audit records, not a count of expected days,
source calls, or confirmed total-asset writes. Current Job routing is MotherDuck `kis_portfolio`, with `var` as data
path. Current retained legacy schedules remain visible (domestic/overseas are paused after the later V2 trade cutover,
token warm-up is enabled). No total-asset legacy schedule is present in this current Seoul inventory.

The global wildcard for Cloud Run Job list is unsupported (400), so the current Job list is explicitly regional.
All-region current service listing and the historical job audit were also examined. A CLI scheduler/listing failure
and broad logging timeout were repaired by bounded REST metadata queries; unavailable commands were never treated
as evidence of empty data.

## Data confirms partial and failed collection, not daily totals

- `main.order_history` before Aug 28: April has one manual-range envelope; **May–July have no rows**; August has
  55 envelopes on 12 fetch dates, beginning Aug 11. Domestic terminal success first appears Aug 11.
  Failed executions can still leave partial writes; success/failed counts cannot be directly equated to envelope rows.
- `main.domestic_orders`: 5 rows last marked `batch` on 2 trade dates; 15 rows last marked `kis_api` on 4 dates.
  Neither raw nor normalized order facts encode complete account asset values.
- `main.overseas_transaction_history`: May 9 envelopes/8 days, June 16/16, July 17/17, August through 27th 17/17.
  The last included August fetch requests Aug 28 (date resolution differs from fetch date); request dates and fetched
  timestamps must remain separate. Legacy fetched_at is naive: Cloud Run uses UTC while local writers may use KST;
  cross-month/day matching requires writer timezone evidence. The July 18 successful terminals and 17 naive-date
  envelopes are therefore not sufficient proof of exactly one missing write. This table demonstrably accumulated pre-V2 batch-like daily observations.
- Overseas normalized transaction rows are only 2, with summary fields and missing trade quantity/side/FX. A raw
  query footer can summarize buys/sells/fees without containing account totals. Empty trade arrays are not asset
  holdings or cash balance statements.
- Overview observation times are irregular; July's only overview is 7/24 at 14:22 KST. The snapshot families have
  no source/run/batch/writer columns identifying the invoking client. Manual MCP origin is plausible but **unproven**.

The code of the three batch commands agrees with this table evidence: domestic invokes order-history endpoints;
overseas invokes transaction-history endpoints; warm-up refreshes credentials and requests service health. They do
not invoke the all-account balance collector or insert an asset overview.

A separate historical failure exists in domestic collection, but source-level cause is not established by terminal
audit alone. No remediation, source replay or current scheduler change was performed in WI-068.

## The fourth collector and release history

Retained commit `9dea94c` on `codex/portfolio-pipeline-reliability`, Aug 2 KST, adds:

- command `collect-asset-overview-snapshot --overseas-account-label brokerage`;
- Job `kis-portfolio-asset-overview-snapshot` and every-day 16:10 schedule target;
- all-account balance refresh, overseas balance/deposit and FX resolution;
- writes to portfolio/overseas/overview/holding snapshot families.

This code is a real collector proposal and could explain the owner's intended daily collection. It is not in
current master ancestry. GitHub PR #1 is currently **closed, unmerged**, containing three unique commits. The earlier
branch-cleanup note described it as open at that time; live PR state was rechecked and not assumed from memory.

37 retained `deploy-cloud-run.yml` runs before Aug 28, across 21 source SHAs, all reference master. None of those
21 source batch CLIs contains `collect-asset-overview-snapshot` or the later V2 owned-core collector. The workflow's
master-only guard is also present. This does not cover arbitrary local deployment, external workflows or other
standalone code. The exact asset Job name has **0 retained pre-V2 audit records** in a complete query, and the current
Seoul inventory contains no such Job/Scheduler. No production deployment of this fourth collector was established.

V2 owned-core Job creation is Aug 28 at 09:19 KST, aligning with the start of scheduled V2 portfolio collection.
Those current V2 Jobs, later releases and WI-066 quarantine were read only and remain outside this investigation's
mutation scope.

## Interpretation and remaining boundaries

Established:

1. Cloud batches existed and some retained pre-V2 tables accumulated data.
2. The three documented/observed batches collected trades/transactions/tokens, not daily total assets.
3. Domestic history collection had substantial failed terminal outcomes and no May–July raw rows.
4. Compared snapshot families are preserved. No alternate populated DB destination was established by the pre-V2
   runtime review or current known DB inventory.
5. The preserved fourth total-asset collector's code is present; deployment/execution is still unproven within scope.

Not established:

- whether another externally deployed collector, another project, a Cloud Function/service or an earlier standalone
  program performed the owner's remembered total-asset daily collection;
- where that program's amounts were stored, if it existed;
- detailed source-level failure causes or a universal assertion that historical data was never collected/lost.

The configured-project evidence presently supports a **collection/operations coverage gap** over a proven V2 data
loss. It does not authorize dismissing the owner's recollection or presenting estimates as historical observations.
The source of an independently deployed total-asset collector must be identified before a definitive history-loss
classification. No speculative synthetic totals or trades were published.

Next architecture decision remains gated. A practical daily-total output can later separate retained observed totals,
repaired reference valuations using external exact-date FX, and estimates for unobserved days. It cannot silently
fill cash/opening state/corporate-action gaps. This follow-up introduces no new API, DDL, backfill or production effect.

## Verification

- Repository Python 3.13.3; direct MotherDuck SELECT, GCP metadata/audit reads and GitHub read-only queries.
- Quick and final full shared gates passed: 815 tests, one warning; linked in WI-068 Evidence.
- Existing work-tree intake changes preserved; WI-068 remains `proposed` and read-only.
