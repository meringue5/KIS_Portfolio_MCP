# WI-045 isolated dual-run readiness verification

> Date: 2026-09-11
> Execution scope: isolated
> Production effects: none

## Outcome

The repository now has one fail-closed evaluator for the Wave 7 comparison, schedule, restore, cost and rollback
evidence. The checked-in ten-session example proves the contract and its failure modes only. It deliberately returns
`blocked` with `fixture evidence cannot satisfy the production dual-run gate`; it is not elapsed production evidence
and cannot authorize WI-046.

## Evidence contract

`kis-portfolio.dual-run-evidence/v1` requires ten or more unique dated sessions. Each session contains the exact six
comparison dimensions from V2-W0701: total asset, holding quantity, orders, prices, signals and freshness. A `match`
must contain numeric V1/V2 values and a non-negative tolerance. A `partial` must contain both a stable quality reason
and explicit missing coverage. An explicit difference or a match outside tolerance is an unexplained difference and
blocks readiness.

The same evaluation requires:

- every required schedule run succeeded and Telegram duplicate deliveries equal zero;
- measured restore RPO no greater than 24 hours and RTO no greater than 4 hours;
- normal-month actual/forecast cost no greater than the approved KRW 7,500 target and current cost evidence;
- the WI-035 target-specific release/rollback manifest validator to pass, including immutable image digests and
  successful restore evidence.

The result always emits `production_cutover_allowed=false`. A passing production observation is only an input to the
human/Project OS production gate; this local evaluator is never a cutover command.

## Local rehearsal

The synthetic fixture covers ten unique sessions, zero unexplained differences, one explained partial consensus gap,
20/20 required schedule runs, zero duplicate deliveries, RPO 720 minutes, RTO 45 minutes and a KRW 6,200 forecast.
The WI-035 manifest names an immutable active and rollback digest for every target. The existing V2 rehearsal test
continues to apply all migrations to a fresh DuckDB, run the fixture pipeline idempotently and verify Bronze, Gold,
quality and lineage evidence; no existing local database is opened or modified.

Review command:

```bash
uv run python scripts/assess_dual_run_readiness.py \
  tests/fixtures/wi045/dual-run-fixture-v1.json \
  tests/fixtures/wi035/release-manifest-v1.json \
  tests/fixtures/wi035/cost-snapshot-v1.json \
  --as-of 2026-09-09T12:00:00Z
```

The expected exit code is 3 because fixture-only evidence is intentionally blocked. Contract validation errors return
2; a fully passing production-observation input would return 0 but still would not apply a change.

Verification completed with 29 focused and recovery-adjacent tests, the quick gate and the full gate at 607 passed.

## Production gate left intact

No production system was queried or changed. This work did not read or write MotherDuck, activate a source, change a
credential/IAM/Secret, modify Cloud Run or Scheduler, register a public MCP connector, send Telegram, apply cleanup,
switch traffic or retire V1. Production completion still requires ten actual trading days, fresh production restore
and billing evidence, MS-002 `closed`, release approval and WI-046 execution.
