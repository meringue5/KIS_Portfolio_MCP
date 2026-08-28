# WI-021-S05 — Trade/cash production preflight

## Purpose

The production command reuses the S01 partition manifest, S02 call budget, S03 resume ledger and S04 canonical
normalizer. Without `--apply` it performs no database connection, source call or write.

## Immutable execution gate

An applied run requires all of the following:

- exact `YYYYMMDD` start, end and as-of dates;
- matching `--expected-plan-hash` and `--expected-budget-hash` from a reviewed preflight;
- `KIS_DB_MODE=motherduck`;
- a complete V2 pre-backup manifest containing the affected Bronze, Silver and Control tables;
- explicit `--apply`.

Each KIS business page calls the durable reservation hook before HTTP I/O. Domestic route/TR selection is fixed by
the partition (`TTTC0081R`/`CTSC9215R`, virtual equivalents); overseas order uses `TTTS3035R`/`VTTS3035R` and maps
the planner exchange to the official order code, while period transactions use `CTOS4001R`. OAuth token acquisition
is not counted as a business-data page.

## Approved reference preflight

For `2023-08-28..2026-08-28`, five configured accounts and brokerage `NAS` overseas scope:

- plan hash: `0755656ed8151a91`
- budget hash: `0a4abf9b795f9d73`
- 131 callable partitions and six known gaps
- 374 worst-case calls under the hard 400-call ceiling

The hash is an execution lock, not a secret. A scope, route, date or policy change produces a different hash and
requires a new reviewed preflight.
