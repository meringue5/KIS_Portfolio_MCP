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
  trade_profit_history

curated views / future tables
  portfolio_daily_snapshots
  future: portfolio_minute_snapshots
  future: holdings_normalized
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

현재 제공하는 view:

```sql
portfolio_daily_snapshots
```

이 view는 계좌별/일자별 마지막 스냅샷을 대표값으로 사용한다.

## 향후 정제 작업 후보

- `portfolio_minute_snapshots`: 같은 계좌의 같은 분 내 마지막 스냅샷
- `holdings_normalized`: `balance_data` JSON에서 보유 종목을 행 단위로 펼친 테이블
- `account_nav_daily`: 계좌별 일별 평가금액, 현금, 보유 평가금액, 환산 금액
- `fx_daily`: 환율 데이터를 분석용 currency/date grain으로 표준화
- `trade_profit_normalized`: 손익 JSON을 종목/기간 단위로 정규화

이 작업들은 `scripts/`의 일회성/배치 스크립트나 향후 `pipelines/` 패키지로 분리할 수 있다.

## 구현 위치

- raw schema: `src/kis_mcp_server/db/schema.py`
- raw repository: `src/kis_mcp_server/db/repository.py`
- curated view DDL: `src/kis_mcp_server/db/schema.py`
- analytics SQL: `src/kis_mcp_server/analytics/`
- backup: `scripts/backup_motherduck.py`
