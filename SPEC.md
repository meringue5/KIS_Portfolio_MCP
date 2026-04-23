# KIS Portfolio Service — 요구사항 및 아키텍처 의사결정

## 프로젝트 목표

한국투자증권(KIS) Open API를 기반으로 개인 포트폴리오 조회, 이력 저장, 분석, 향후 원격 접근을
제공하는 서비스 구축.

MCP는 이 서비스의 주요 인터페이스 중 하나이며, 프로젝트의 중심은 MCP tool 자체가 아니라
KIS API client, 계좌 오케스트레이션, MotherDuck 기반 데이터 저장/분석, 보안 정책이다.

---

## 유즈케이스

### 현재 구현됨

| 유즈케이스 | 관련 Tool |
|-----------|----------|
| 전체 계좌 구성 조회 | `get-configured-accounts` |
| 전체 계좌 국내/연금 잔고 스냅샷 | `refresh-all-account-snapshots` |
| 국내/해외/환율 반영 전체 자산 요약 | `get-total-asset-overview` |
| 총자산 일별 변화/추이/비중 이력 | `get-total-asset-daily-change`, `get-total-asset-trend`, `get-total-asset-allocation-history` |
| 단일 계좌 국내주식 잔고 조회 | `get-account-balance` |
| 단일 계좌 해외주식 잔고 조회 | `get-overseas-balance` |
| 해외 예수금 + 적용환율 조회 | `get-overseas-deposit` |
| 국내주식 현재가/호가 조회 | `get-stock-price`, `get-stock-ask` |
| 해외주식 현재가 조회 | `get-overseas-stock-price` |
| 국내주식 가격 이력 | `get-stock-history` |
| 해외주식 가격 이력 | `get-overseas-stock-history` |
| 환율 이력 조회 | `get-exchange-rate-history` |
| 국내주식 기간별 매매손익 | `get-period-trade-profit` |
| 해외주식 기간별 손익 | `get-overseas-period-profit` |
| 주문 조회/상세 | `get-order-list`, `get-order-detail` |
| 주문 stub | `submit-stock-order`, `submit-overseas-stock-order` |
| 종목 기본정보 | `get-stock-info` |

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

**상태**: `baseline/pre-service-refactor` 이후 폐기. 현재 기본 MCP 표면은 단일 `kis-portfolio` 서버다.

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
`src/kis_portfolio/` 아래에 둔다.

**이유**:
- MCP 서버, KIS API client, DB repository, 분석 로직, 향후 Web API를 분리할 기반이 필요
- 테스트 코드가 실제 패키지 import 경로를 사용하도록 만들어 경로 의존성을 줄임
- 기존 Claude/Codex Desktop 설정은 루트 `server.py`를 실행하므로 호환 shim을 남겨 점진 이행
- 루트에 런타임 산출물과 소스가 섞이는 문제를 줄이고 보안/배포 문서화를 명확히 함

**현재 적용**:
- 루트 `server.py`: `src/kis_portfolio/app.py`의 `main()` 호출
- DB 레이어: `src/kis_portfolio/db/` 패키지
- 루트 `db.py` 호환 wrapper는 제거. 내부/테스트 코드는 `kis_portfolio.db`를 직접 import
- 기본 런타임 데이터 위치는 프로젝트 루트 기준 `var`
- KIS API access token cache는 `kis_api_access_tokens` 테이블에 암호화 저장
- legacy 토큰 파일 `var/tokens/token_{CANO}.json`은 1회 migration 입력값으로만 사용
- 토큰 refresh는 프로세스 내 keyed async lock으로 직렬화하고, 만료 10분 전부터 새 발급 대상으로 간주
- local 모드 DuckDB는 `var/local/kis_portfolio.duckdb`

**현재 구조 전환**:
- 패키지명은 `kis_portfolio`
- public MCP adapter는 `src/kis_portfolio/adapters/mcp/server.py`
- `clients/`, `services/`, `adapters/` 구조를 도입
- 루트 `server.py`는 새 MCP adapter shim

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

### ADR-008: Skill은 runbook, 반복 로직은 MCP tool로 승격

**결정**: 에이전트 공통 운용 절차는 `.agent/skills/` 아래에 둔다. 단, 합산/변화 계산처럼
결과가 결정적인 반복 로직은 skill 지침에만 의존하지 않고 MCP tool과 Python 함수로 구현한다.

**이유**:
- Claude, Codex, Gemini의 skill discovery 방식이 완전히 동일하다고 가정할 수 없음
- MCP tool은 클라이언트가 달라도 같은 schema와 서버 로직을 재사용할 수 있음
- 포트폴리오 합산, 일별 변화, 이상치 탐지는 재현성과 테스트가 중요함

**현재 적용**:
- 공통 skill: `.agent/skills/kis-portfolio-ops/SKILL.md`
- canonical 총자산 tool: `get-total-asset-overview`
- 글로벌 분석 tool: `get-total-asset-history`, `get-total-asset-daily-change`, `get-total-asset-trend`
- 국내/연금 feeder 분석 tool: `get-latest-portfolio-summary`, `get-portfolio-daily-change`
- 주문 tool 기본 비활성: `KIS_ENABLE_ORDER_TOOLS=false`

---

### ADR-009: 컨테이너와 bearer 인증 remote MCP 베이스라인

**결정**: Dockerfile을 추가해 배포 가능한 실행 환경을 준비한다. 기본 엔트리포인트는 local stdio MCP로
유지하고, 원격 클라이언트용 `kis-portfolio-remote` 엔트리포인트는 `/mcp` Streamable HTTP endpoint를
제공한다. remote endpoint는 `KIS_REMOTE_AUTH_TOKEN` 기반 bearer 인증을 요구한다.

**이유**:
- Fly.io, Render, Cloud Run 등은 컨테이너 배포와 runtime secret 관리가 자연스러움
- KIS/MotherDuck secret은 이미지에 포함하지 않고 배포 플랫폼의 runtime env로 주입해야 함
- `KIS_TOKEN_ENCRYPTION_KEY`는 remote/local KIS 조회 런타임의 필수 secret이며, ordinary redeploy만으로는 connector 재연결이 필요하지 않음
- local MCP 안정화와 remote MCP 인증/권한 설계를 분리해야 주문 기능 노출 위험을 줄일 수 있음
- 개인용 초기 배포에는 공유 bearer token이 단순하고 검증하기 쉬움
- 다중 사용자/조직 배포는 OAuth/OIDC로 승격해야 함

상세 방향은 `docs/deployment.md` 참고.

---

### ADR-010: 계좌별 MCP와 포트폴리오 오케스트레이터 병행

**결정**: 기존 계좌별 MCP 5개는 유지하고, 조회-only 단일 오케스트레이터 `kis-portfolio`를 추가한다.
오케스트레이터 실행 명령은 `kis-portfolio-mcp`이며, 계좌별 suffixed env를 `AccountRegistry`로 읽는다.

**이유**:
- Claude가 매번 5개 계좌 MCP를 직접 조합하지 않아도 전체 계좌 조회와 요약 분석을 수행할 수 있음
- 기존 계좌별 MCP를 유지하므로 전환 중 회귀 위험을 줄일 수 있음
- `os.environ` 기반 레거시 인증/토큰 경계가 남아 있으므로 v1에서는 scoped env와 순차 실행이 안전함
- 주문 tool을 오케스트레이터에 노출하지 않아 전체 계좌 자동화의 위험을 낮춤

**현재 적용**:
- `get-configured-accounts`: 계좌 목록 조회, 계좌번호 마스킹
- `get-all-token-statuses`: 전체 계좌 토큰 캐시 상태 조회, 토큰 값 비노출
- `get-account-balance`: 단일 계좌 잔고 조회 및 스냅샷 저장
- `refresh-all-account-snapshots`: 전체 계좌 순차 조회 및 계좌별 성공/실패 반환
- `get-latest-portfolio-summary`, `get-portfolio-daily-change`: 기존 DB-only 분석 tool 재노출

**상태**: `baseline/pre-service-refactor` 이후 단일 MCP 전환으로 대체. 계좌별 MCP 5개는 기본 설정에서 제거한다.

---

### ADR-011: Forked MCP에서 KIS API 기반 포트폴리오 서비스로 설계 기준 전환

**결정**: 신규 기능 설계의 primary source를 fork 원본 MCP 구현이 아니라 한국투자 공식 Open API
문서와 공식 예제 저장소로 둔다. 기존 fork는 출처, 초기 구현 자산, 일부 회귀 호환성 기준으로만 유지한다.

**이유**:
- 요구사항의 중심이 단일 MCP tool 묶음에서 다계좌 포트폴리오 서비스, 데이터 적재, 분석, 원격 배포로 이동함
- 계좌 오케스트레이션, MotherDuck, token audit, 조회-only remote MCP는 fork 원본보다 우리 도메인 요구가 강함
- KIS API 문서가 주문/계좌, 기본시세, 종목정보, 실시간시세, OAuth 등 capability 경계를 제공함
- MCP, HTTP, batch job은 같은 core service를 호출하는 adapter로 분리하는 편이 장기 유지보수에 적합함

**현재 적용**:
- 오케스트레이터 `kis-portfolio`를 primary MCP로 삼고, 계좌별 MCP 5개는 기본 설정에서 제거
- 신규 API 기능은 `docs/api-capability-map.md`의 capability map에 먼저 위치시킨 뒤 구현
- 공식 KIS 예제는 endpoint/파라미터/종목 마스터 처리의 참조 구현으로 사용
- README와 문서는 fork attribution을 남기되, 프로젝트 설명은 포트폴리오 서비스 중심으로 전환

---

### ADR-012: 단일 `kis-portfolio` MCP와 `kis_portfolio` 패키지 전환

**결정**: Python package를 `kis_portfolio`로 rename하고, public MCP는 `kis-portfolio-mcp` 단일
entrypoint로 제공한다. 기존 fork의 `inquery-*` tool alias와 계좌별 MCP 5개는 기본 노출하지 않는다.

**이유**:
- Claude가 여러 계좌별 MCP를 서로 다른 서비스로 오인하지 않게 single point of truth를 명확히 함
- 프로젝트 정체성이 MCP wrapper에서 포트폴리오 서비스로 이동했으므로 import/package 이름도 일치시킴
- 신규 기능은 clean `get-*` tool 표면으로 제공하고, legacy naming은 내부 구현 세부사항으로만 남김

**현재 적용**:
- `kis-portfolio-mcp`, `kis-portfolio-remote`, `kis-portfolio-batch` CLI를 제공
- `scripts/setup.sh`는 `kis-portfolio` 서버 하나만 Claude config에 생성
- `submit-stock-order`, `submit-overseas-stock-order`는 disabled stub이며 실제 주문 API를 호출하지 않음
- KIS raw 응답은 `raw`에 보존하고 MCP wrapper metadata를 덧붙임

**저장소 전략**:
- 당장은 기존 저장소와 git history를 유지한다.
- 구조 전환이 충분히 진행되어 upstream MCP와의 병합 가능성이 실질적으로 사라지면 GitHub repository rename을
  우선 검토한다.
- 새 repository 생성은 공개 배포/브랜딩을 완전히 분리하거나, 기존 fork 관계를 GitHub UI상에서도 끊어야 할
  명확한 이유가 있을 때 선택한다.

---

### ADR-013: `get-total-asset-overview`를 canonical 총자산 API로 승격

**결정**: 총자산, 대시보드, 국내/해외 비중, 경제적 노출 분석의 기준 API를
`get-total-asset-overview` 하나로 고정한다. 국내/연금 raw feeder는 `portfolio_snapshots`에
계속 저장하되, 총자산 분석은 `asset_overview_snapshots`와 관련 정규화 계층을 사용한다.

**이유**:
- 사용자가 실제로 원하는 총액에는 해외주식 평가액뿐 아니라 해외 예수금/현금성이 포함된다.
- 국내/연금 feeder 요약과 글로벌 총자산 요약을 같은 이름으로 혼용하면 대시보드와 설명이 어긋난다.
- 계좌 기준 비중과 경제적 노출 기준 비중은 같은 총액을 다른 관점으로 분해하는 문제이므로 canonical
  aggregate와 normalized holding row가 필요하다.

**현재 적용**:
- raw feeder:
  - `portfolio_snapshots`
  - `overseas_asset_snapshots`
- canonical aggregate:
  - `asset_overview_snapshots`
- normalized holdings:
  - `asset_holding_snapshots`
- curated view:
  - `asset_overview_daily_snapshots`
- 글로벌 분석 tool:
  - `get-total-asset-history`
  - `get-total-asset-daily-change`
  - `get-total-asset-trend`
  - `get-total-asset-allocation-history`
- 기존 `get-latest-portfolio-summary`, `get-portfolio-daily-change`, `get-portfolio-trend`,
  `get-portfolio-anomalies`는 국내/연금 feeder 분석으로 의미를 축소한다.

---

### ADR-014: 국내 상장 해외 ETF/REIT는 `해외우회투자`로 분류

**결정**: 국내 상장 ETF/REIT 중 해외 노출 상품은 총자산 합산에서 국내 계좌 자산으로 유지하되,
경제적 노출 차트에서는 `overseas_indirect`(`해외우회투자`)로 별도 표시한다.

**이유**:
- 계좌/통화 기준으로는 원화 국내 계좌 자산이 맞지만, 투자 노출 기준으로는 해외자산 성격이 강하다.
- 총액을 이중 가산하지 않으면서 두 관점을 모두 제공하려면 분류 레이어가 필요하다.
- KIS 공식 종목마스터만으로 실제 해외 노출을 완전히 판별하기 어렵다. 공식 예제/문서에는 `EF`, `FE`,
  `RT` 같은 구분이 보이지만, 2026년 4월 19일 동기화한 실제 KRX master file에서는 `E`(ETF), `R`(REIT),
  `S`(국내주), `F`(외국기업 국내상장) 같은 그룹코드도 관찰되므로 구현은 문서 코드와 observed code를 함께 다룬다.

**분류 우선순위**:
1. `instrument_classification_overrides`
2. KIS 종목마스터 group code
3. ETF/REIT 이름 heuristic
4. `unknown`

**현재 적용**:
- 종목마스터 테이블: `instrument_master`
- 로컬 override 테이블: `instrument_classification_overrides`
- v1 이름 heuristic:
  - 해외 힌트: `미국`, `나스닥`, `S&P`, `글로벌`, `Global`, `해외`, `선진국`, `신흥국`, `중국`, `일본`, `인도`, `베트남`
  - 국내 힌트: `Korea`, `코리아`, `K수출`, `삼성전자`, `SK하이닉스`, `밸류업`
- 경고 목록은 `classification_warnings`로 반환한다.

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
> 모든 쿼리는 `kis_portfolio.db.get_connection()`으로 얻은 커넥션에서 실행한다.
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
6. **DB 패키지 역할 경계**: 분석 쿼리는 analytics 모듈에서 실행. `kis_portfolio.db`는 연결, 스키마 초기화, 저장(upsert/insert), 기본 조회 함수만 담당
