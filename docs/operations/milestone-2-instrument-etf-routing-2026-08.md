# Milestone 2 Instrument Classification and ETF Routing — 2026-08-28

## Implemented boundary

WI-017 added point-in-time instrument versions and exact ETF provider routing without enabling issuer collection.
Classification precedence is reasoned owner override, KIS instrument master, exact ETF route and explicit unknown.
Economic exposure remains unknown until constituent evidence exists; product names do not become canonical exposure.

Four provider profiles and parsers cover synthetic fixture shapes only:

- TIME: OOXML spreadsheet fixture.
- KoAct: exact-date JSON fixture.
- RISE: exact-date HTML-table fixture.
- PLUS: complete single-page JSON fixture.

The official product domains were verified as `timefolioetf.co.kr`, `samsungactive.co.kr`, `riseetf.co.kr` and
`plusetf.co.kr`. Rights fields remain unknown and activation is `fixture_only`; the production network registry has
zero profiles. No issuer/KRX source call, real constituent file, Cloud Run Job or Scheduler was created.

## Production reconciliation

- Additive MotherDuck migration: `0007`.
- Current-held scope: 18 instruments.
- Classification: 14 ETF, four explicit unknown.
- Point-in-time version rows: 18.
- Exact fixture-only routes: 14, one for every currently held domestic ETF.
- Classification governance observations: 18.
- Repeated apply returned the same counts; route and version writers are idempotent.

The four unknowns remain usable as held positions but are not ETF pipeline candidates. This is a deliberate
fail-closed result, not missing-value coercion.

## Recovery and verification

- Post-apply backup: `var/backup/v2-parquet/20260828_020836/`; 35 tables restored into a fresh DuckDB.
- Private GCS upload: 36 objects, 7,681,881 bytes.
- GCS index SHA-256: `c2225f5b7edd28a8d522c562c97f03763546a28c3476a3911d1a05d4d3f1b25f`.
- GCS-downloaded backup restored into a second fresh DuckDB; it retained 18 instrument versions, 14 routes and the
  `14 ETF / 4 unknown` current classification.
- `bash scripts/check.sh full`: 248 tests passed before production apply, including architecture, governance,
  migration, offline parser, point-in-time and idempotency gates.

Restricted raw object bytes remain governed separately and are not claimed as part of the Parquet table backup.
