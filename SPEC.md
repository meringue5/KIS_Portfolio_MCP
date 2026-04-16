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

- [ ] DuckDB 로컬 캐시: 주가/환율 이력 자동 저장
- [ ] DuckDB 누적 저장: 계좌 잔고 스냅샷 시계열
- [ ] 볼린저 밴드 등 기술적 지표 분석
- [ ] 계좌 변동 추이 분석 및 이상치 탐지
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

### ADR-003: 로컬 데이터베이스로 DuckDB 선택

**결정**: SQLite 대신 DuckDB 사용

**이유**:
- 컬럼 기반 저장소 → 시계열 분석(볼린저 밴드, 이동평균) 쿼리 성능 우월
- 네이티브 window function 지원 → Python 없이 SQL만으로 기술적 지표 계산 가능
- `query().df()` 한 줄로 pandas DataFrame 변환 → 시각화 연동 용이
- Parquet 직접 쿼리 지원 → 향후 데이터 규모 확장 시 마이그레이션 무비용

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
