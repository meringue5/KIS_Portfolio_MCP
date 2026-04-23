# MotherDuck Backup

운영 데이터베이스는 MotherDuck이다. 로컬 DuckDB 파일은 운영 트랜잭션 중심이 아니라
개발, 장애 대응, 백업 검증을 위한 보조 산출물로 다룬다.

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
├── portfolio_snapshots.parquet
├── price_history.parquet
├── trade_profit_history.parquet
└── manifest.json
```

기본 백업은 analytics/raw/canonical 테이블만 대상으로 한다. OAuth 상태 테이블과 `kis_api_access_tokens`
같은 민감한 인증/캐시 테이블은 기본 Parquet 백업 대상에 포함하지 않는다.

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
