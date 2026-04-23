# Data Pipeline Direction

이 프로젝트의 현재 쓰기 경로는 MCP tool이 KIS API에서 데이터를 받아 MotherDuck에 저장하는
OLTP 성격이 강하다. 하지만 장기 목표는 포트폴리오 분석, 시계열 비교, 이상치 탐지 같은 OLAP
워크로드다. 따라서 저장 계층과 분석 계층을 섞지 않는 방향으로 설계한다.

## 원칙

1. Raw 데이터는 가능한 한 보존한다.
2. 중복 제거와 대표값 선택은 raw write path에서 하지 않는다.
3. 분석용 정제 데이터는 view, table, 또는 별도 pipeline 단계에서 만든다.
4. 로컬 DuckDB는 운영 중심 DB가 아니라 백업/검증/개발용이다.

## 계층

엄격한 medallion architecture를 지금 당장 도입하지는 않는다. 다만 같은 사고방식으로 계층을 둔다.

```text
raw tables
  price_history
  exchange_rate_history
  portfolio_snapshots
  overseas_asset_snapshots
  asset_overview_snapshots
  asset_holding_snapshots
  market_calendar
  order_history
  instrument_master
  instrument_classification_overrides
  trade_profit_history

canonical / curated tables
  domestic_orders

curated views / future tables
  portfolio_daily_snapshots
  asset_overview_daily_snapshots
  future: portfolio_minute_snapshots
  future: account_nav_daily

analytics functions
  bollinger bands
  portfolio anomalies
  portfolio trend
```

## 스냅샷 중복 처리

`portfolio_snapshots`는 append-only raw table이다. 같은 계좌를 같은 날 여러 번 조회해도 raw row는
보존한다. 이는 다음 이유 때문이다.

- LLM/MCP 호출 이력을 감사할 수 있다.
- API 응답 구조 변경이나 파싱 오류를 나중에 재처리할 수 있다.
- 분 단위/일 단위 대표값 정책을 나중에 바꿔도 raw를 잃지 않는다.

분석에서는 raw table을 직접 쓰지 않고 curated view를 먼저 사용한다.

`order_history`도 같은 원칙을 따른다. 같은 계좌와 같은 기간을 같은 날 여러 번 조회하거나,
오전 수동 조회 뒤 장마감 배치가 다시 적재하더라도 raw row는 보존한다. 이 테이블은 이제
주문조회 coverage와 raw audit 목적의 snapshot 저장소로 본다.

중복집계 방지를 위한 serving/analytics 기준 저장소는 `domestic_orders`다. 이 테이블은 append-only가 아니라
KIS 주문 식별자 기준 upsert를 사용한다. 현재 국내주식 주문의 canonical key는 다음과 같다.

- 계좌 식별: `(account_id, account_product_code)`
- 주문 식별: `(order_date, order_branch_no, order_no)`

즉 전체 primary key는 `(account_id, account_product_code, order_date, order_branch_no, order_no)`이다.
여기서 `order_no`와 `order_branch_no`는 KIS `주식일별주문체결조회(inquire-daily-ccld)` 응답의
`odno`, `ord_gno_brno`를 사용한다. `pdno`와 `ord_tmd`는 속성으로 저장하되 key에는 포함하지 않는다.

`get-order-list`와 `collect-domestic-order-history` 배치는 모두 같은 canonical upsert 경로를 탄다.
장중 수동 조회와 장마감 배치가 같은 주문을 다시 가져와도 기존 row를 최신 상태로 갱신하고, 통계는
`domestic_orders`만 읽도록 한다.

현재 제공하는 view:

```sql
portfolio_daily_snapshots
asset_overview_daily_snapshots
```

이 view들은 계좌별 또는 canonical snapshot별 일자 마지막 스냅샷을 대표값으로 사용한다.

## 향후 정제 작업 후보

- `portfolio_minute_snapshots`: 같은 계좌의 같은 분 내 마지막 스냅샷
- `account_nav_daily`: 계좌별 일별 평가금액, 현금, 보유 평가금액, 환산 금액
- `fx_daily`: 환율 데이터를 분석용 currency/date grain으로 표준화
- `trade_profit_normalized`: 손익 JSON을 종목/기간 단위로 정규화
- `domestic_order_fills_normalized`: 필요해지면 주문/체결 JSON을 체결 단위로 더 세분화
- `market_session_calendar`: 시장별 거래일/휴장일/마감시간 계약

이 작업들은 `scripts/`의 일회성/배치 스크립트나 향후 `pipelines/` 패키지로 분리할 수 있다.

## 구현 위치

- raw schema: `src/kis_portfolio/db/schema.py`
- raw repository: `src/kis_portfolio/db/repository.py`
- curated view DDL: `src/kis_portfolio/db/schema.py`
- analytics SQL: `src/kis_portfolio/analytics/`
- backup: `scripts/backup_motherduck.py`
