# KIS MCP Server — 요구사항 및 아키텍처 의사결정

## 프로젝트 목표

한국투자증권(KIS) Open API를 Claude Desktop에서 자연어로 조회·분석할 수 있는 MCP 서버 구축.
단순 API 게이트웨이를 넘어, 로컬 데이터베이스 기반의 이력 관리 및 분석 플랫폼으로 확장.

---

## 유즈케이스

### 현재 구현됨

| 유즈케이스 | 관련 Tool |
|-----------|----------|
| 계좌별 국내주식 잔고 조회 | `inquery-balance` |
| 계좌별 해외주식 잔고 조회 | `inquery-overseas-balance` |
| 해외 예수금 + 적용환율 조회 | `inquery-overseas-deposit` |
| 국내주식 현재가/호가 조회 | `inquery-stock-price`, `inquery-stock-ask` |
| 해외주식 현재가 조회 | `inquery-overseas-stock-price` |
| 국내주식 가격 이력 | `inquery-stock-history` |
| 해외주식 가격 이력 | `inquery-overseas-stock-history` |
| 환율 이력 조회 | `inquery-exchange-rate-history` |
| 국내주식 기간별 매매손익 | `inquery-period-trade-profit` |
| 해외주식 기간별 손익 | `inquery-overseas-period-profit` |
| 주문 조회/상세 | `inquery-order-list`, `inquery-order-detail` |
| 종목 기본정보 | `inquery-stock-info` |
| KIS API 문서 검색 | `kis-api-search` 서버 |

### 예정

- [x] DuckDB(MotherDuck) 캐시: 주가/환율 이력 자동 저장
- [x] DuckDB(MotherDuck) 누적 저장: 계좌 잔고 스냅샷 시계열
- [ ] 볼린저 밴드 등 기술적 지표 분석 (→ [DuckDB 분석 플랜](#duckdb-분석-플랜) 참고)
- [ ] 계좌 변동 추이 분석 및 이상치 탐지 (→ [DuckDB 분석 플랜](#duckdb-분석-플랜) 참고)
- [ ] 클라우드 컨테이너 배포 (환경변수 .env 방식)

---

## 아키텍처 의사결정

### ADR-001: 계좌별 독립 MCP 서버 인스턴스

**결정**: 5개 계좌를 단일 서버가 아닌 별도 인스턴스로 실행

**이유**:
- Claude가 계좌를 명확히 구분하여 도구 호출 가능
- 환경변수(CANO, ACNT_PRDT_CD)만으로 계좌 구분 → 코드 변경 없이 계좌 추가 가능
- 토큰 파일을 `token_{CANO}.json`으로 분리하여 충돌 방지

**대안 검토**: 단일 서버 + 계좌 파라미터 → 자연어 인식 정확도 저하 우려로 기각

---

### ADR-002: IRP와 연금저축의 API 분기

**결정**: ACNT_PRDT_CD=29(IRP)만 pension API 사용, 22(연금저축)는 표준 API 사용

**근거**: KIS MTS에서 확인
- IRP: 별도 잔고 화면 사용 → pension API(`TTTC2208R`) 필요
- 연금저축: 일반 계좌(-01)와 동일 화면 → 표준 API(`TTTC8434R`) 사용

**코드**:
```python
is_pension = acnt_prdt_cd == "29"
```

---

### ADR-003: 분석 데이터베이스로 DuckDB/MotherDuck 선택

**결정**: SQLite 대신 DuckDB 계열을 사용하고, 운영 중심 DB는 MotherDuck으로 둔다.

**이유**:
- 컬럼 기반 저장소 → 시계열 분석(볼린저 밴드, 이동평균) 쿼리 성능 우월
- 네이티브 window function 지원 → Python 없이 SQL만으로 기술적 지표 계산 가능
- `query().df()` 한 줄로 pandas DataFrame 변환 → 시각화 연동 용이
- Parquet 직접 쿼리 지원 → 향후 데이터 규모 확장 시 마이그레이션 무비용
- MotherDuck을 사용하면 여러 MCP 인스턴스와 향후 웹 호스팅 환경에서 로컬 파일 락 문제를 피할 수 있음

**대안 검토**: SQLite + pandas → 분석 로직을 Python에서 처리해야 하므로 복잡도 증가

---

### ADR-004: 캐시형 vs 누적형 데이터 분리

**결정**: 데이터 성격에 따라 저장 방식 구분

| 데이터 | 저장 방식 | 이유 |
|--------|----------|------|
| 주가 이력 | INSERT OR IGNORE | 과거 종가는 불변 (수정주가 재동기화 시에만 UPDATE) |
| 환율 이력 | INSERT OR IGNORE | 과거 환율은 불변 |
| 계좌 잔고 스냅샷 | 순수 INSERT (append-only) | 같은 날도 시점마다 다른 값 → 전부 누적 |
| 손익 리포트 | 순수 INSERT (append-only) | 조회 시점의 스냅샷으로 보존 |

---

### ADR-005: 루트 문서/설계, `src/` 애플리케이션 코드 구조

**결정**: 루트 디렉터리는 문서, 설정, 호환 진입점 중심으로 유지하고 실제 애플리케이션 코드는
`src/kis_mcp_server/` 아래에 둔다.

**이유**:
- MCP 서버, KIS API client, DB repository, 분석 로직, 향후 Web API를 분리할 기반이 필요
- 테스트 코드가 실제 패키지 import 경로를 사용하도록 만들어 경로 의존성을 줄임
- 기존 Claude/Codex Desktop 설정은 루트 `server.py`를 실행하므로 호환 shim을 남겨 점진 이행
- 루트에 런타임 산출물과 소스가 섞이는 문제를 줄이고 보안/배포 문서화를 명확히 함

**현재 적용**:
- 루트 `server.py`: `src/kis_mcp_server/app.py`의 `main()` 호출
- 루트 `db.py`: `src/kis_mcp_server/db.py` re-export
- 기본 런타임 데이터 위치는 프로젝트 루트 기준 `var`
- 토큰 파일은 `var/tokens/token_{CANO}.json`
- local 모드 DuckDB는 `var/local/kis_portfolio.duckdb`

**후속 과제**:
- `app.py`를 `auth`, `kis_client`, `tools`, `analytics` 모듈로 분해
- pytest 기반 테스트 추가
- 웹 배포용 secret 관리 정책 확정

---

### ADR-006: MotherDuck을 운영 DB로 사용하고 로컬 DuckDB는 명시적 local/backup 용도로 제한

**결정**: `KIS_DB_MODE=motherduck`을 기본값으로 둔다. `MOTHERDUCK_TOKEN`이 없으면 조용히 로컬
DuckDB로 fallback하지 않고 서버 시작/DB 연결 시 명확히 실패한다.

**이유**:
- 계좌별 MCP 인스턴스와 멀티 에이전트 작업이 동시에 로컬 DuckDB 파일을 열면 락 충돌이 발생할 수 있음
- token 누락 등 설정 실수로 데이터가 로컬 DB와 MotherDuck에 나뉘어 저장되는 사고를 방지
- 로컬 DuckDB는 운영 트랜잭션 중심이 아니라 개발, 장애 대응, 주기적 백업 타겟으로 다루는 것이 명확함

**환경변수**:
```text
KIS_DB_MODE=motherduck
MOTHERDUCK_DATABASE=kis_portfolio
MOTHERDUCK_TOKEN=...
KIS_DATA_DIR=var
```

**로컬 모드**:
```text
KIS_DB_MODE=local
KIS_DATA_DIR=var
```

상대경로로 지정한 `KIS_DATA_DIR`, `KIS_TOKEN_DIR`, `KIS_LOCAL_DB_PATH`는 현재 작업 디렉터리가 아니라
프로젝트 루트 기준으로 해석한다.

**백업**: MotherDuck 백업은 Parquet을 기본 포맷으로 사용한다. `scripts/backup_motherduck.py`는
핵심 테이블을 `var/backup/parquet/YYYYMMDD_HHMMSS/` 아래로 export하고 `manifest.json`을 함께 남긴다.

---

### ADR-007: Raw append-only 저장과 curated view 기반 분석

**결정**: `portfolio_snapshots`는 같은 계좌/같은 날/짧은 시간 내 중복 조회라도 raw row를 삭제하거나
덮어쓰지 않는다. 분석은 raw table이 아니라 curated view 또는 향후 pipeline 산출물을 사용한다.

**이유**:
- API 원본 응답을 보존해야 나중에 파싱 로직 변경이나 데이터 정제를 재수행할 수 있음
- LLM/MCP 호출로 생성된 관측 이력을 감사할 수 있음
- 일 단위, 분 단위, 장 마감 기준 등 대표값 정책이 바뀌어도 raw를 잃지 않음

**현재 적용**:
- raw table: `portfolio_snapshots`
- curated view: `portfolio_daily_snapshots`
- `portfolio_daily_snapshots`는 계좌별/일자별 마지막 스냅샷을 대표값으로 사용
- 분석 함수는 이 view를 우선 사용

상세 방향은 `docs/data-pipeline.md` 참고.

---

## API 제한사항

- 대량 이력 조회 시 KIS 서버에서 차단 가능 → 로컬 캐시 도입의 주요 이유
- `inquire-daily-chartprice`: 미국 주식은 다우30/나스닥100/S&P500 종목만 조회 가능. 전체 종목은 `dailyprice`(HHDFS76240000) API 사용
- 환율 조회 TR_ID: `FHKST03030100` (실전/모의 공통)
- 연속 조회(페이징): `CTX_AREA_FK*` / `CTX_AREA_NK*` 파라미터로 처리

---

## 환경 구성

### Claude Desktop (로컬)
환경변수를 `claude_desktop_config.json`의 `env` 블록에서 주입.

### 클라우드 배포 (예정)
`python-dotenv`로 `.env` 파일 로드. `server.py`는 `os.environ`만 사용하므로 코드 변경 불필요.

---

## DuckDB 분석 플랜

> 이 섹션은 Codex(또는 다른 AI 코딩 도구)에 구현을 위임하기 위한 상세 명세다.
> 모든 쿼리는 `db.py`의 `get_connection()`으로 얻은 커넥션에서 실행한다.
> 결과는 DuckDB cursor 결과를 JSON 직렬화 가능한 `list[dict]`로 변환해 MCP tool의 응답에 포함한다.

---

### 1. 볼린저 밴드 (Bollinger Bands)

**목적**: 특정 종목의 주가가 과매수/과매도 구간에 있는지 탐지

**구현 위치**: `server.py`에 신규 tool `get-bollinger-bands` 추가

**파라미터**:
- `symbol` (str): 종목 코드 (예: `005930`)
- `exchange` (str): `KRX`, `NAS`, `NYS` 등 `price_history.exchange`에 저장된 거래소 코드 (기본값: `KRX`)
- `window` (int): 이동평균 기간 (기본값: 20)
- `num_std` (float): 표준편차 배수 (기본값: 2.0)
- `limit` (int): 반환할 최근 행 수 (기본값: 60)

**DuckDB SQL 구현**:
```sql
WITH price_stats AS (
  SELECT
    symbol,
    exchange,
    date,
    close,
    COUNT(close) OVER (
      PARTITION BY symbol, exchange
      ORDER BY date
      ROWS BETWEEN {window-1} PRECEDING AND CURRENT ROW
    ) AS observations,
    AVG(close) OVER (
      PARTITION BY symbol, exchange
      ORDER BY date
      ROWS BETWEEN {window-1} PRECEDING AND CURRENT ROW
    ) AS sma,
    STDDEV(close) OVER (
      PARTITION BY symbol, exchange
      ORDER BY date
      ROWS BETWEEN {window-1} PRECEDING AND CURRENT ROW
    ) AS std
  FROM price_history
  WHERE symbol = ? AND exchange = ? AND close IS NOT NULL
)
SELECT
  symbol,
  exchange,
  date,
  close,
  ROUND(sma, 2)                          AS sma,
  ROUND(sma + {num_std} * std, 2)        AS upper_band,
  ROUND(sma - {num_std} * std, 2)        AS lower_band,
  ROUND((close - sma) / NULLIF(std, 0), 2) AS z_score,
  CASE
    WHEN close > sma + {num_std} * std THEN '과매수'
    WHEN close < sma - {num_std} * std THEN '과매도'
    ELSE '중립'
  END AS signal
FROM price_stats
WHERE observations >= {window}
ORDER BY date DESC
LIMIT ?;
```

**응답 형식 (JSON)**: 최근 60일 데이터 + 현재 signal 요약

---

### 2. 이상치 탐지 (Anomaly Detection) — 계좌 잔고 기반

**목적**: 일별 포트폴리오 평가금액 변동률이 통계적으로 비정상적인 날을 탐지
(급락/급등 경보, 오입력 탐지 등)

**구현 위치**: `server.py`에 신규 tool `get-portfolio-anomalies` 추가

**파라미터**:
- `account_id` (str): 계좌번호(CANO). 빈값이면 현재 MCP 인스턴스의 `KIS_CANO`
- `z_threshold` (float): 이상치 기준 z-score (기본값: 2.0)
- `lookback_days` (int): 분석 기간 (기본값: 90)
- `limit` (int): 반환할 최대 행 수 (기본값: 20)

**DuckDB SQL 구현**:
```sql
WITH daily_snapshots AS (
  -- 하루에 여러 번 저장될 수 있으므로 일별 최종값만 사용
  SELECT
    account_id,
    CAST(snapshot_at AS DATE) AS snap_date,
    ARG_MAX(total_eval_amt, snapshot_at) AS total_eval_amt
  FROM portfolio_snapshots
  WHERE account_id = ?
    AND snapshot_at >= CURRENT_DATE - INTERVAL '{lookback_days} days'
    AND total_eval_amt IS NOT NULL
  GROUP BY account_id, snap_date
),
daily_returns AS (
  SELECT
    account_id,
    snap_date,
    total_eval_amt,
    LAG(total_eval_amt) OVER (
      PARTITION BY account_id ORDER BY snap_date
    ) AS prev_total_eval_amt
  FROM daily_snapshots
),
stats AS (
  SELECT
    account_id,
    AVG(return_pct)    AS mean_return,
    STDDEV(return_pct) AS std_return
  FROM (
    SELECT
      account_id,
      (total_eval_amt - prev_total_eval_amt)
        / NULLIF(prev_total_eval_amt, 0) * 100 AS return_pct
    FROM daily_returns
    WHERE prev_total_eval_amt IS NOT NULL
  )
  WHERE return_pct IS NOT NULL
  GROUP BY account_id
)
SELECT
  d.snap_date,
  d.total_eval_amt,
  ROUND((d.total_eval_amt - d.prev_total_eval_amt)
    / NULLIF(d.prev_total_eval_amt, 0) * 100, 2) AS return_pct,
  ROUND(((
    d.total_eval_amt - d.prev_total_eval_amt
  ) / NULLIF(d.prev_total_eval_amt, 0) * 100 - s.mean_return)
    / NULLIF(s.std_return, 0), 2) AS z_score,
  CASE
    WHEN ABS((((d.total_eval_amt - d.prev_total_eval_amt)
      / NULLIF(d.prev_total_eval_amt, 0) * 100) - s.mean_return)
      / NULLIF(s.std_return, 0)) >= {z_threshold}
    THEN '이상치'
    ELSE '정상'
  END AS status
FROM daily_returns d
JOIN stats s ON d.account_id = s.account_id
WHERE d.prev_total_eval_amt IS NOT NULL
ORDER BY ABS((((d.total_eval_amt - d.prev_total_eval_amt)
  / NULLIF(d.prev_total_eval_amt, 0) * 100) - s.mean_return)
  / NULLIF(s.std_return, 0)) DESC NULLS LAST
LIMIT ?;
```

**응답 형식**: 이상치 날짜 목록 + 해당일 변동률 + z-score

---

### 3. 포트폴리오 추이 분석 (Portfolio Trend)

**목적**: 계좌별 자산 시계열을 단기/중기 이동평균으로 시각화, 추세 방향 판단

**구현 위치**: `server.py`에 신규 tool `get-portfolio-trend` 추가

**파라미터**:
- `account_id` (str): 계좌번호(CANO). 빈값이면 현재 MCP 인스턴스의 `KIS_CANO`
- `short_window` (int): 단기 이동평균 일수 (기본값: 7)
- `long_window` (int): 중기 이동평균 일수 (기본값: 30)
- `lookback_days` (int): 조회 기간 (기본값: 90)

**DuckDB SQL 구현**:
```sql
WITH daily_snapshots AS (
  SELECT
    account_id,
    CAST(snapshot_at AS DATE) AS snap_date,
    ARG_MAX(total_eval_amt, snapshot_at) AS total_eval_amt
  FROM portfolio_snapshots
  WHERE account_id = ?
    AND snapshot_at >= CURRENT_DATE - INTERVAL '{lookback_days} days'
    AND total_eval_amt IS NOT NULL
  GROUP BY account_id, snap_date
),
trend_rows AS (
  SELECT
    account_id,
    snap_date,
    total_eval_amt,
    COUNT(total_eval_amt) OVER (
      PARTITION BY account_id
      ORDER BY snap_date
      ROWS BETWEEN {long_window-1} PRECEDING AND CURRENT ROW
    ) AS long_observations,
    ROUND(AVG(total_eval_amt) OVER (
      PARTITION BY account_id
      ORDER BY snap_date
      ROWS BETWEEN {short_window-1} PRECEDING AND CURRENT ROW
    ), 0) AS short_sma,
    ROUND(AVG(total_eval_amt) OVER (
      PARTITION BY account_id
      ORDER BY snap_date
      ROWS BETWEEN {long_window-1} PRECEDING AND CURRENT ROW
    ), 0) AS long_sma
  FROM daily_snapshots
)
SELECT
  account_id,
  snap_date,
  total_eval_amt,
  short_sma,
  long_sma,
  CASE
    WHEN short_sma > long_sma THEN '상승추세'
    WHEN short_sma < long_sma THEN '하락추세'
    ELSE '중립'
  END AS trend
FROM trend_rows
WHERE long_observations >= {long_window}
ORDER BY snap_date DESC;
```

**응답 형식**: 날짜별 평가금액 + SMA7 + SMA30 + 추세 신호

---

### 4. 구현 가이드라인 (Codex용)

1. **신규 tool 추가 패턴**: 기존 `get-portfolio-history` tool의 구조를 참고. FastMCP 함수 파라미터로 입력을 받고, DB 커넥션은 `kisdb.get_connection()`으로 획득한다. 연결은 프로세스 싱글톤이므로 tool 내부에서 닫지 않는다.
2. **SQL 파라미터 바인딩**: DuckDB Python API는 `?` 플레이스홀더 사용 (`conn.execute(sql, [param1, param2])`)
3. **window 변수**: SQL 문자열 안의 `{window-1}` 같은 표현은 f-string 또는 `.format()`으로 치환 (SQL injection 위험 없는 정수값)
4. **결과 직렬화**: DuckDB cursor의 `description`과 `fetchall()`로 `list[dict]`를 만들고, `date`/`datetime`은 ISO 문자열로 변환한다.
5. **데이터 부족 처리**: 스냅샷이 window보다 적을 경우 `"데이터가 부족합니다 (현재 N일, 최소 {window}일 필요)"` 메시지 반환
6. **db.py 역할 경계**: 분석 쿼리는 `server.py`에서 직접 `conn.execute()` 호출. `db.py`는 스키마 초기화, 저장(upsert/insert), 기본 조회 함수만 담당
