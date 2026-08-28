# Milestone 2 Dual-Basis Price Backfill — 2026-08-28

## Scope and safety boundary

WI-015 applied the approved `pipeline.price-history-v2` only to the 18 instruments present in each account's latest
position snapshot. The range ended at the last completed market date, 2026-08-27, so an in-progress 2026-08-28 KRX
bar was not published. Both `raw` and `adjusted` basis were collected. All history is labelled
`retrospective_reconstructed` and cannot satisfy strict point-in-time replay or alert activation.

## Migration and recovery evidence

- MotherDuck migration: `0004` and additive price-ledger migration `0005` applied successfully.
- Pre-backfill V2 backup: `var/backup/v2-parquet/20260828_012540/`; 32 tables restored into fresh memory DB.
- Private GCS verification: 33 content-addressed objects, 3,515,014 bytes, index hash
  `389869a45eb62ebbf404c18b5589bdcbbda51bd50af9667ac92ef7c173d706e1`; download hashes and fresh DB restore passed.
- Post-backfill V2 backup: `var/backup/v2-parquet/20260828_013726/`; 32 tables restored into fresh memory DB.
- Post-backfill private GCS backup: 33 objects, 7,656,751 bytes, index hash
  `3ae7ff10b0981c55a13fb0dd8a78c54e4d07b60d9b411c3fdd526cb7eee10541`.
- Private raw object bytes are governed separately and are not claimed as included by the Parquet manifest.

The first pre-migration backup attempt stopped because the target catalog already required the not-yet-created 0005
revision table. It made no database change. Existing successful backup evidence plus the additive-only migration allowed
0005 to proceed; a complete backup and restore was then performed immediately after migration.

## Plan, execution and reconciliation

The first dry-run failed closed at 480/400 calls and exposed stale sold holdings in the original planner. The corrected
planner uses only rows at each account's latest snapshot time. Its accepted dry-run result was 18 instruments,
36 dual-basis partitions and 288 estimated calls under the hard 400-call ceiling.

Run `7f3f6735-3e75-446d-b845-74900951489a` succeeded after an interrupted, idempotent performance rehearsal was resumed
with page-level bulk writes.

| Evidence | Result |
| --- | ---: |
| Physical KIS history calls | 174 |
| Governed partitions passed | 36 / 36 |
| Watermarks published | 36 |
| Raw current bars | 7,576 rows / 18 instruments |
| Adjusted current bars | 7,576 rows / 18 instruments |
| Covered session range | 2023-08-28 through 2026-08-27 |
| Non-pass current price rows | 0 |

Estimated calls were higher than actual because newer instruments required fewer than eight pages. Raw pages remain in
`bronze.source_observations`; append-only revisions and current projection are in
`silver.price_bar_revisions_daily` and `silver.price_bars_daily` respectively.

## Verification and remaining boundary

- Full Project OS gate: 234 tests passed after the planner correction and bulk-write change.
- Synthetic contracts cover domestic 100/101-row sharding, overseas continuation, endpoint-specific basis options,
  cursor stall, call-budget exhaustion, revision idempotency and strict/reconstructed as-of selection.
- This backfill enables reconstructed analysis. It does not create historical knowledge that was unavailable at the
  original date, and it does not activate metrics, signals or Telegram delivery.
