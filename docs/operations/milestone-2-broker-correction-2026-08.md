# Milestone 2 Broker History Correction — 2026-08-28

## Contract correction

WI-016 corrected the broker-history source contract before any broader historical collection. Domestic history now
splits old and recent ranges across the official TR routes and consumes FK/NK continuation. IRP recent history remains
an explicit provisional gap. Overseas period transactions are read from `output1` and retain the official execution
price, fee, domestic fee, applied FX and settlement-date fields.

Domestic side code `01` maps to sell and `02` maps to buy. Unknown side values fail before a trade event or purchase
lot is created. New event identity includes account, market, product code, instrument, broker order, execution time and
execution sequence.

## Production migration and reconciliation

- Additive MotherDuck migration `0006` created `silver.trade_event_revisions`,
  `silver.trade_events_current` and `silver.purchase_lots_current`.
- Aggregate-only dry-run found 19 source trade events, all with known side and product code.
- All 19 events were eligible; the legacy base side already agreed with the source in all 19 rows.
- The correction applied 19 append-only baseline revisions. It did not update or delete legacy rows.
- Current projection: 19 buys, zero sells; corrected lot projection suppresses zero lots.
- Re-running the correction is idempotent because source event and revision identity are unique.

The result does not assert that three years of broker history are complete. It only establishes correct source
semantics and a reversible projection for the currently migrated events.

## Recovery and verification

- Post-correction backup: `var/backup/v2-parquet/20260828_015300/`; 33 tables restored into a fresh DuckDB.
- Private GCS upload: 34 objects, 7,666,574 bytes.
- GCS index SHA-256: `8bab6eb3bd0c46ffa7d449e0c10d72c04dfd30c5334acf14a5d1227997b6a66a`.
- GCS-downloaded backup restored into a second fresh DuckDB; aggregate source reconciliation remained 19 known,
  zero unknown side/product and zero base-side mismatch.
- `bash scripts/check.sh full`: 239 tests passed with every Project OS contract gate passing.

Restricted raw object bytes remain governed by their separate private-object contract and are not claimed as part of
the Parquet table backup.
