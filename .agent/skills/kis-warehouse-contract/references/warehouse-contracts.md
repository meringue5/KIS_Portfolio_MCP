# Warehouse Contracts

The canonical object inventory and detailed contracts live in `docs/data-catalog.md`.
This reference is intentionally limited to invariants used while implementing changes.

## Layer Invariants

- Bronze is append-only and preserves KIS observations needed for replay.
- Silver owns normalized rows, keyed deduplication, and canonical total-asset snapshots.
- Gold is reproducible from Silver plus governed Control data.
- Control owns migration state and reference/override data.
- Security is isolated from analytics and default Parquet backups.
- Current physical schema is `main`; target schemas are the layer names above. Physical moves require a versioned migration and reconciliation.
- `asset_overview_snapshots`, not domestic-only feeder data, is the canonical global total-asset source.
- Daily representative policy is implemented in Gold view/query logic, never by deleting Bronze rows.

## Secret Policy

- KIS access token cache may live in `kis_api_access_tokens` when the token value is encrypted at rest.
- legacy `var/tokens/token_{CANO}.json` is migration-only input, not the steady-state source of truth.
- MotherDuck/local DuckDB must never receive raw token values or app secrets.

## Backup Policy

- Parquet backup tables are selected by `src/kis_portfolio/db/catalog.py`.
- Backup manifest should describe exported tables and timestamp.
- Live objects absent from the registry are drift and are never automatically deleted.
