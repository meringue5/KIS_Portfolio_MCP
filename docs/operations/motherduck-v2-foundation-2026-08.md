# MotherDuck V2 Parallel Foundation — 2026-08-28

## Scope and authorization

DEC-045와 WI-005에 따라 기존 운영 `kis_portfolio.main` 객체와 데이터를 유지한 채 V2
`bronze`, `silver`, `gold`, `control` schema를 병렬로 추가했다. 기존 객체의 삭제·rename·writer 중지,
production consumer cutover와 과거 데이터 backfill은 수행하지 않았다.

## Preflight and preservation

- migration 전 live inventory에서 기존 managed V1 객체가 모두 존재함을 확인했다.
- 알려진 V1 drift는 `main.cash_flow`, `main.trade_journal`, `main.asset_return_daily`와
  `main.asset_overview_snapshots`의 추가 quality column뿐이며 자동 채택·삭제하지 않았다.
- migration 전 V1 Parquet backup:
  `var/backup/parquet/20260828_020109/`
- 주요 보존 row count: `portfolio_snapshots` 267, `overseas_asset_snapshots` 48,
  `order_history` 56, `overseas_transaction_history` 58, `price_history` 838,
  `exchange_rate_history` 100, `asset_overview_snapshots` 48,
  `asset_holding_snapshots` 1,619.

백업 경로는 로컬 운영 증거이며 Git에 포함하지 않는다. manifest가 전체 테이블별 row count를 소유한다.

## Applied result

```text
V2 migrations target=md:kis_portfolio applied: ['0001', '0002']
V2 migrations target=md:kis_portfolio applied: no-op
```

- V2 managed object: 32개
- schema별 object: `bronze` 3, `silver` 19, `gold` 2, `control` 8
- migration 후 missing managed object: 없음
- migration 후 신규 column drift: 없음
- 기존 `main` 객체와 알려진 drift: 유지

V2는 현재 pre-production foundation이다. live V2 business table에는 synthetic fixture나 과거 V1 row를
적재하지 않았으며, V1→V2 backfill은 source-to-target mapping, row reconciliation, quality gate와 rollback을
가진 별도 Work Item에서 실행한다.

## Backup and restore evidence

- V2 metadata/table backup: `var/backup/v2-parquet/20260827_170318/`
- manifest version: 2
- governed table: 29개
- private raw object bytes: 포함하지 않음
- fresh DuckDB restore rehearsal: 29개 table row count 및 2개 view compile 확인

```text
V2 restore verified: tables=29 target=:memory:
warning: restricted/raw object bytes require a separate private object restore
```

재현 명령은 [MotherDuck Backup](../backup.md)에 둔다. owner PDF 원문을 실제 운영 object store에 적재하고
복구하는 절차는 GCS destination과 lifecycle을 승인하는 후속 Work Item이 소유한다.

## Rollback and next gate

현재 V2 consumer와 writer가 없으므로 V1 runtime rollback은 traffic 변경 없이 성립한다. V2 schema 삭제는
데이터 손실 가능성이 있는 별도 destructive change이며 자동 rollback으로 수행하지 않는다. 다음 단계는
backfill dry-run과 reconciliation 보고서를 먼저 만들고, owner 승인 뒤 bounded live backfill을 실행하는 것이다.
