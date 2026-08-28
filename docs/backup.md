# MotherDuck Backup

운영 데이터베이스는 MotherDuck이다. 로컬 DuckDB 파일은 운영 트랜잭션 중심이 아니라
개발, 장애 대응, 백업 검증을 위한 보조 산출물로 다룬다.

백업 대상과 민감도 결정은 [Data Store Governance and Catalog](./data-catalog.md)가 관리한다.
`scripts/backup_motherduck.py`의 대상 목록은 `src/kis_portfolio/db/catalog.py`에서 직접 파생하므로,
테이블을 추가할 때 백업 포함 여부를 명시하지 않으면 warehouse contract 검사를 통과할 수 없다.

2026-08-28 승인된 V2에서도 MotherDuck 분석 데이터의 off-vendor Parquet 백업 책임은 유지한다. Firestore의
active OAuth/token/lease state를 MotherDuck이나 이 Parquet 백업에 복제하지 않는다. V2 operational-state
복구는 OAuth connector 재연결, KIS token 재발급, immutable run summary와 idempotent 재실행을 기본으로 하며,
Firestore PITR/managed backup은 실제 비용·RPO 검토를 거친 별도 Work Item 전에는 활성화하지 않는다.
현재 V1 백업 대상과 실행 절차는 아래와 같이 유지된다.

## V2 parallel backup contract

V2 registry의 backup policy는 `V2_DATA_OBJECTS`와 `v2_backup_table_names()`에 machine-readable하게 있다.
운영 migration 전까지 현재 V1 `backup_motherduck.py`의 export 목록에는 자동 편입하지 않는다. V2가 live로
적용되면 qualified schema를 보존하는 새 backup manifest version으로 다음을 export한다.

```bash
uv run python scripts/backup_v2_motherduck.py
uv run python scripts/restore_v2_backup.py var/backup/v2-parquet/YYYYMMDD_HHMMSS --database :memory:
```

스크립트와 WI-021/WI-022 managed recovery Job은 동일한 `kis_portfolio.services.v2_recovery`
allowlist/export/upload/download/restore primitives를 호출한다. 두 S06 Job 모두 pre/post를 명시적인 fresh
DuckDB 파일로 복원하여 Job 종료 전 aggregate reconciliation을 다시 수행한다. WI-022-S06은 pre restore가
끝나기 전 reconstruction row를 쓰지 않으며, 현재 승인 범위에서는 Control exception만 append한다.

- Parquet: `bronze.source_observations`, `silver.accounts`, `silver.instruments`, `silver.instrument_versions`,
  `silver.position_snapshots`, `silver.cash_snapshots`, `silver.trade_events`, `silver.trade_event_revisions`, `silver.cash_flow_events`,
  `silver.cash_flow_event_revisions`,
  `silver.position_episodes`, `silver.position_episode_revisions`,
  `silver.purchase_lots`, `silver.purchase_lot_identities`, `silver.purchase_lot_revisions`,
  `silver.trade_threads`, `silver.trade_thread_lots`,
  `silver.sell_allocation_sets`, `silver.sell_allocation_revisions`,
  `silver.trade_journal_revisions`, `silver.trade_thread_risk_plan_revisions`,
  `silver.price_bars_daily`,
  `silver.price_bar_revisions_daily`,
  `silver.corporate_actions`, `silver.corporate_action_revisions`,
  `silver.corporate_action_adjustment_effects`,
  `silver.fx_rates_daily`, `silver.etf_constituent_snapshots`, `silver.filing_events`,
  `silver.financial_facts`, `silver.dividend_events`, `silver.macro_observations`,
  `gold.portfolio_daily_state`, `gold.metric_values`, `control.pipeline_definitions`,
  `control.metric_definitions`, `control.pipeline_runs`,
  `control.pipeline_stage_runs`, `control.quality_results`, `control.lineage_edges`, `control.watermarks`,
  `control.reconstruction_exceptions`, `control.reconstruction_exception_revisions`,
  `control.owner_review_items`, `control.owner_review_item_revisions`,
  `control.etf_instrument_routes`.
- Object metadata Parquet: `bronze.raw_object_manifest`, `bronze.owner_research_documents`,
  `silver.owner_research_extractions`. 이 세 table의 metadata row도 manifest에 포함한다.
- Private content-addressed object bytes: 위 metadata가 가리키는 실제 원문·추출물. MotherDuck metadata만으로
  원문 backup이 됐다고 간주하지 않는다.
- Rebuild/excluded: `silver.instrument_versions_effective`, `silver.instruments_current`,
  `silver.trade_events_current`, `silver.cash_flow_events_current`, `silver.purchase_lots_current`,
  `silver.position_episodes_current`, `silver.purchase_lot_states_current`, `silver.sell_allocations_current`,
  `silver.trade_thread_risk_plans_current`,
  `silver.corporate_actions_current`,
  `gold.portfolio_daily_summary`, `control.pipeline_run_summary`,
  `control.reconstruction_exceptions_current`,
  `control.owner_review_items_current`,
  `control.schema_migrations`.

owner research 원문과 추출물은 restricted다. local rehearsal에서는 owner-only directory의 0600 file로
검증하며, production object destination과 lifecycle은 별도 GCS provisioning/restore Work Item 전에는
활성화하지 않는다.

## Private GCS recovery foundation

WI-012에서 `gs://grand-forge-279904-kis-portfolio-private`를 Seoul regional Standard bucket으로
create-or-verify했다. Uniform bucket-level access와 public-access prevention은 강제되고, Google-managed
encryption, versioning, 7일 soft delete, noncurrent version 30일 삭제, incomplete multipart upload 7일
중단 정책을 사용한다. Current immutable raw/recovery object에는 자동 만료를 적용하지 않는다. Dataset별
retention 계약 없이 current object를 일괄 삭제하지 않기 위해서다.

`scripts/sync_v2_backup_gcs.py`는 backup file별 SHA-256을 가진 content-addressed object와 복원 index를
생성한다. Restore는 모든 파일 hash를 검증한 뒤 기존 `scripts/restore_v2_backup.py` gate로 이어간다.
Portfolio backup은 confidential payload이므로 실제 최초 업로드는 해당 payload의 외부 GCS 전송 승인을
확인한 뒤 수행한다. Firestore operational state는 이 경로에 포함하지 않는다.

## Parquet 백업

기본 백업 포맷은 Parquet이다. 이유는 다음과 같다.

- DuckDB에서 바로 읽을 수 있다.
- pandas, Polars, Spark 같은 분석 도구와 호환된다.
- 테이블별 파일로 나뉘어 장기 보관과 부분 복원이 쉽다.
- 로컬 DuckDB 파일 하나를 복사하는 방식보다 포맷 의존성이 낮다.

백업 실행:

```bash
uv run python scripts/backup_motherduck.py
```

기본 출력 위치:

```text
var/backup/parquet/YYYYMMDD_HHMMSS/
├── exchange_rate_history.parquet
├── overseas_asset_snapshots.parquet
├── asset_overview_snapshots.parquet
├── asset_holding_snapshots.parquet
├── market_calendar.parquet
├── instrument_master.parquet
├── instrument_classification_overrides.parquet
├── domestic_orders.parquet
├── order_history.parquet
├── overseas_order_history.parquet
├── overseas_orders.parquet
├── overseas_transaction_history.parquet
├── overseas_transactions.parquet
├── overseas_settlement_balance_snapshots.parquet
├── portfolio_snapshots.parquet
├── price_history.parquet
├── trade_profit_history.parquet
└── manifest.json
```

기본 백업은 analytics/raw/canonical 테이블만 대상으로 한다. OAuth 상태 테이블과 `kis_api_access_tokens`
같은 민감한 인증/캐시 테이블은 기본 Parquet 백업 대상에 포함하지 않는다.
다만 기본 백업에도 계좌 id, 보유 종목, 주문/체결 이력, 평가금액이 포함될 수 있으므로 백업 산출물은
민감 데이터로 취급한다. 자세한 분류와 보관 원칙은 [Security and Secrets](./security-and-secrets.md)를 따른다.

Gold view와 `schema_migrations`도 기본 백업에서 제외한다. Gold는 복원된 Bronze/Silver/Control table과
versioned migration으로 재생성하고, migration ledger는 복원 대상 database에서 새로 검증한다.

2026-08-28 병렬 적용과 실제 복원 리허설 결과는
[MotherDuck V2 Parallel Foundation](./operations/motherduck-v2-foundation-2026-08.md)에 기록한다.

최근 백업 N개만 남기려면:

```bash
uv run python scripts/backup_motherduck.py --keep 10
```

`--keep`을 지정하지 않으면 오래된 백업을 삭제하지 않는다.

## 환경변수

스크립트는 프로젝트 루트의 `.env`를 읽고, 다음 값을 사용한다.

```text
MOTHERDUCK_TOKEN=...
MOTHERDUCK_DATABASE=kis_portfolio
KIS_DATA_DIR=var
```

상대경로는 프로젝트 루트 기준으로 해석된다.

## 복원/검증 예시

Parquet 백업은 DuckDB에서 바로 읽을 수 있다.

```sql
SELECT count(*)
FROM read_parquet('var/backup/parquet/20260419_130000/portfolio_snapshots.parquet');
```

필요하면 새 로컬 DuckDB 파일로 적재할 수 있다.

```sql
CREATE TABLE portfolio_snapshots AS
SELECT * FROM read_parquet('var/backup/parquet/20260419_130000/portfolio_snapshots.parquet');
```
