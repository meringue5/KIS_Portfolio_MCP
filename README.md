# KIS Portfolio Service

[![Python 3.13+](https://img.shields.io/badge/python-3.13+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-yellow.svg)](./LICENSE)

한국투자증권(KIS) Open API를 기반으로 만든 개인 포트폴리오 서비스입니다.
여러 계좌의 국내/해외 자산을 한 번에 조회하고, MotherDuck/DuckDB에 스냅샷을 쌓아 이력과 비중 변화를 분석할 수 있습니다.
장기 비전은 개인 자산 포트폴리오 관리와 데이터 분석 기반 투자 의사결정 war-room입니다.

이 프로젝트는 원래 `migusdn/KIS_MCP_Server` 포크에서 출발했지만, 현재는 OAuth Remote MCP, managed batch와
Firestore/MotherDuck 데이터 경계를 가진 포트폴리오 서비스로 재설계되었습니다. 현재 문서의 단일 진입점은
[docs/README.md](./docs/README.md)입니다.

한국투자증권과 무관한 비공식 오픈소스 프로젝트입니다.

## 한눈에 보기

- 여러 KIS 계좌를 OAuth Remote custom connector `KIS Portfolio` 하나로 조회
- 국내 자산 + 해외 주식 + 해외 예수금까지 합친 canonical 총자산 계산
- 국내 상장 해외 ETF/REIT를 `해외우회투자`로 분리 표시
- MotherDuck/DuckDB에 스냅샷을 저장하고 총자산 이력/일간 변화/추세 분석
- Claude web/Desktop/mobile와 Codex에서 함께 쓰는 OAuth Remote MCP V2 단일 연결
- 원격 MCP 배포를 위한 HTTP 엔트리포인트와 컨테이너 베이스라인 포함

## 이런 분에게 맞습니다

- 한국투자증권 계좌를 여러 개 운용하고 있고, 전체 자산을 한 번에 보고 싶은 분
- 국내/해외/현금/해외우회투자 비중을 LLM 대화로 확인하고 싶은 분
- MCP를 단순 조회 도구가 아니라 개인 투자 데이터 레이어로 키우고 싶은 분
- 나중에 웹 서비스, 배치 분석, 원격 MCP까지 확장할 구조를 원하는 분

## 현재 제공 기능

### 1. 포트폴리오와 분석

- 저장된 전체 자산현황, 계좌 alias별 구성과 경제적 노출 조회
- 포지션 분석, 성과 이력, 총자산 변동과 기여도 분석
- freshness, completeness, reconciliation과 lineage를 포함한 명시적 품질 상태

### 2. 시세/이력

- 저장된 시장 snapshot과 가격·환율 이력
- 거래 원장, 거래 thread와 배당 요약

### 3. 전망·신호·운영 명령

- fundamental outlook, exposure와 signal 상태
- data catalog, quality, pipeline run과 journal review queue
- 고정된 managed pipeline 실행과 owner journal/thread revision
- 주문·정정·취소 tool은 공개 catalog에 없음

### 4. 데이터 저장

- Bronze: KIS 잔고·주문·거래·손익 raw observation
- Silver: 정규화 시세/환율, canonical 총자산·보유종목·주문/거래
- Gold: 일별 대표 스냅샷과 분석용 view
- Control: migration, 시장 달력, 종목마스터, 분류 override
- Operational state: Firestore의 OAuth/KIS token·lease·run-request state
- Security: Secret Manager의 장기 credential/key와 analytics DB 밖의 보안 경계

현재 V2 registry의 79개 table과 27개 view, 그리고 보존된 legacy `main` 객체의 grain, key, 적재 방식,
민감도와 백업 정책은
[데이터 저장소 거버넌스와 카탈로그](./docs/data-catalog.md)에 정리되어 있습니다.

## 중요한 현재 상태

이 프로젝트는 현재 **조회/분석 및 제한된 수집·일지 명령 중심**입니다. V2 공개 catalog에는 주문 권한과
주문 tool이 없습니다. 과거 V1의 disabled 주문 stub도 공개 표면에서 제거되었습니다.

## 예시 질문

Claude Desktop 같은 MCP 클라이언트에서 아래처럼 물어볼 수 있습니다.

- `내 전체 자산현황 보여줘`
- `국내 자산 대비 해외 자산 비율 알려줘`
- `해외우회투자까지 포함해서 자산 비중 정리해줘`
- `최근 30일 총자산 변화 보여줘`
- `ISA와 연금 계좌를 따로 비교해줘`

## 설치

### 준비물

- Claude custom connector를 사용할 수 있는 계정 또는 Codex CLI/Desktop
- 운영 OAuth Remote MCP의 canonical HTTPS `/mcp` URL
- 저장소 개발·운영 작업에는 Python 3.13+와 [uv](https://astral.sh/uv)

## 빠른 시작

```bash
git clone https://github.com/meringue5/KIS_Portfolio_MCP.git
cd KIS_Portfolio_MCP
cp .env.example .env
```

`.env`에 운영 값을 복원하고 `KIS_RESOURCE_SERVER_URL`을 canonical HTTPS `/mcp` URL로 설정한 뒤:

```bash
uv sync
bash scripts/setup.sh
```

이 스크립트가 하는 일:

- V2 Remote MCP URL 검사
- 의존성 설치
- `var/` 런타임 디렉터리 생성
- 기존 Claude Desktop 설정의 로컬 `kis-portfolio` V1 항목만 백업 후 제거
- `KIS Portfolio` OAuth Remote custom connector 등록 절차 안내

Claude의 설정 > 커넥터에서 표시된 URL을 `KIS Portfolio`로 등록하고, 새 대화에서 권한을 승인합니다.
상세 절차는 [Remote MCP migration guide](./docs/remote-mcp-v2-migration.md)를 따릅니다.

## 환경변수

기본 패턴은 아래와 같습니다.

```env
KIS_APP_KEY_RIA=
KIS_APP_SECRET_RIA=
KIS_CANO_RIA=
KIS_ACNT_PRDT_CD_RIA=01

KIS_APP_KEY_ISA=
KIS_APP_SECRET_ISA=
KIS_CANO_ISA=
KIS_ACNT_PRDT_CD_ISA=01

KIS_APP_KEY_IRP=
KIS_APP_SECRET_IRP=
KIS_CANO_IRP=
KIS_ACNT_PRDT_CD_IRP=29

KIS_APP_KEY_PENSION=
KIS_APP_SECRET_PENSION=
KIS_CANO_PENSION=
KIS_ACNT_PRDT_CD_PENSION=22

KIS_APP_KEY_BROKERAGE=
KIS_APP_SECRET_BROKERAGE=
KIS_CANO_BROKERAGE=
KIS_ACNT_PRDT_CD_BROKERAGE=01

KIS_DB_MODE=motherduck
MOTHERDUCK_DATABASE=kis_portfolio
MOTHERDUCK_TOKEN=
KIS_DATA_DIR=var
KIS_ACCOUNT_TYPE=REAL
KIS_ENABLE_ORDER_TOOLS=false
KIS_REAL_API_MIN_INTERVAL_SECONDS=0.15
KIS_REAL_API_MAX_IN_FLIGHT=3
KIS_API_MAX_QUEUE_SIZE=50
```

전체 예시는 [.env.example](./.env.example)를 참고하세요. 각 시크릿의 source of truth, DB 저장 여부,
회전 절차는 [docs/security-and-secrets.md](./docs/security-and-secrets.md)에 정리되어 있습니다.
KIS 호출 간격은 [docs/kis-api-rate-limits.md](./docs/kis-api-rate-limits.md), timeout·재시도·bulkhead·circuit
breaker·stale fallback 계약은 [docs/kis-api-resilience.md](./docs/kis-api-resilience.md)를 따릅니다.

## 실행 방법

### 폐기된 로컬 V1 진입점

```bash
uv run kis-portfolio-mcp
```

또는 루트 shim:

```bash
uv run python server.py
```

두 명령은 더 이상 MCP 서버를 시작하지 않습니다. `v1_public_surface_retired`와 OAuth Remote MCP 연결
안내를 출력하고 실패 종료합니다. 내부 migration/data 호환 코드는 삭제하지 않습니다.

### 원격 MCP 서버

```bash
uv run kis-portfolio-remote
```

원격 배포는 `/mcp` HTTP endpoint를 사용합니다. ChatGPT 호환과 운영 배포는 `KIS_REMOTE_AUTH_MODE=oauth`를 권장하며, `KIS_REMOTE_AUTH_TOKEN` 기반 bearer는 빠른 실험용 fallback입니다. 자세한 내용은 [docs/deployment.md](./docs/deployment.md)를 참고하세요.

### 배치 CLI

```bash
uv run kis-portfolio-batch collect-domestic-order-history --date today
uv run kis-portfolio-batch collect-overseas-transaction-history --date today --account-label brokerage --exchange NAS
uv run kis-portfolio-batch warm-token-cache --account-label all --valid-through 16:30 --dry-run
uv run kis-portfolio-batch sync-market-calendar 2026 2027
```

`collect-domestic-order-history`는 Asia/Seoul 기준 `today` 날짜를 풀어 전 계좌의 당일 국내 주문/체결 이력을 조회하고, `order_history`에는 raw snapshot을 append-only로 저장하며 `domestic_orders`에는 KIS 주문 식별자 기준 canonical upsert를 수행합니다.
배치 실행 전에는 `market_calendar`를 조회하며, 휴장일이면 자동 skip 하고, 당일 실행은 KRX 마감 `15:30` 이후 5분 grace window가 지난 뒤에만 수집합니다.
`sync-market-calendar`는 KRX 거래 캘린더를 연도 단위로 생성해 `market_calendar`에 upsert 합니다.
`collect-overseas-transaction-history`는 지정 계좌/거래소의 해외주식 일별거래내역을 수집해 raw snapshot과 canonical transaction row를 함께 저장합니다.
`warm-token-cache`는 지정 시각까지 안전하게 유효하지 않은 KIS access token을 계좌별로 점검합니다. 초기 운영은 `--dry-run`으로만 예약해 실제 토큰 발급 없이 장중 만료 위험을 관측합니다.
Cloud Scheduler/cron 기준 첫 스케줄 예시는 평일 `15:35` KST, cron 표현으로는 `35 15 * * 1-5` 입니다.

### ChatGPT 앱 메타데이터 권장값

ChatGPT에서 custom app으로 연결할 때는 아래처럼 app-level metadata를 명시해 두는 편이 안정적입니다.

- Connector name: `KIS Portfolio`
- Description: `Use this app for stored KIS portfolio overview, position and performance analysis, market history, trade and dividend ledgers, governed data quality, and approved managed collection or journal commands. Prefer get-portfolio-overview for total assets and allocation. Do not use it for internet news, general market research, or live order placement; no order tool is exposed.`

도구 설명이나 입력 스키마를 바꾼 뒤에는 ChatGPT Settings에서 connector `Refresh`를 눌러 frozen metadata snapshot을 갱신하세요.

### GitHub 수동 Cloud Run 배포

이 저장소에는 GitHub Actions에서 `workflow_dispatch`로만 실행되는 수동 Cloud Run 배포 workflow가 포함되어 있습니다.

- workflow 파일: [.github/workflows/deploy-cloud-run.yml](./.github/workflows/deploy-cloud-run.yml)
- 기본 흐름: `workflow_dispatch -> full gate -> selected protected target`
- canonical release는 목적별 보호 target과 immutable digest/rollback 계약을 사용합니다. `all`과 개별 target은
  과거·긴급 호환 경로이며 현재 전체 운영 baseline을 의미하지 않습니다.
- `master` push만으로는 배포되지 않습니다.
- 로컬 수동 배포 예시:
  - `uv run python scripts/deploy_cloud_run.py batch`
  - `uv run python scripts/deploy_cloud_run.py scheduler`

필수 GitHub Environment secrets:

- `GCP_WORKLOAD_IDENTITY_PROVIDER`
  - Workload Identity Provider 전체 리소스 이름
- `GCP_SERVICE_ACCOUNT`
  - GitHub Actions가 impersonate할 Google service account 이메일

필수 GitHub vars:

- `GOOGLE_CLOUD_PROJECT`

선택 GitHub vars:

- `KIS_DEPLOY_REGION` 기본값 `asia-northeast3`
- `KIS_AUTH_SERVICE_NAME` 기본값 `kis-portfolio-auth`
- `KIS_REMOTE_SERVICE_NAME` 기본값 `kis-portfolio-remote`
- `KIS_CLOUD_RUN_AUTH_MAX_INSTANCES` 기본값 `1`
- `KIS_CLOUD_RUN_REMOTE_CONCURRENCY` 기본값 `20`
- `KIS_CLOUD_RUN_REMOTE_MIN_INSTANCES` 기본값 `0`
- `KIS_CLOUD_RUN_REMOTE_MAX_INSTANCES` 기본값 `1`
- `KIS_BATCH_JOB_NAME` 기본값 `kis-portfolio-domestic-order-history`
- `KIS_BATCH_SCHEDULER_NAME` 기본값 `kis-portfolio-domestic-order-history-1535`
- `KIS_OVERSEAS_BATCH_JOB_NAME` 기본값 `kis-portfolio-overseas-transaction-history`
- `KIS_OVERSEAS_BATCH_SCHEDULER_NAME` 기본값 `kis-portfolio-overseas-transaction-history-0735`
- `KIS_CLOUD_SCHEDULER_REGION` 기본값 `asia-northeast3`

Scheduler는 Cloud Run Job의 `jobs:run` Google API endpoint를 OAuth로 호출합니다. `KIS_CLOUD_SCHEDULER_INVOKER_SERVICE_ACCOUNT`를 명시하면 그 계정을 쓰고, 비워두면 `GOOGLE_CLOUD_PROJECT_NUMBER` 또는 gcloud 조회 결과를 바탕으로 기본 compute service account를 fallback으로 사용합니다. 이 계정에는 Cloud Run Job에 대한 `roles/run.invoker`가 필요합니다.

운영 credential은 GCP Secret Manager가 소유합니다. deprecated `KIS_DEPLOY_ENV`를 workflow에 다시 추가하지
않습니다. 포함되는 값과 회전 정책은 [docs/security-and-secrets.md](./docs/security-and-secrets.md)를 기준으로 합니다.

## Claude Desktop 연결

이 저장소는 로컬 stdio MCP를 등록하지 않습니다. 아래 스크립트는 과거 로컬 V1 등록을 안전하게 백업·제거하고
canonical Remote URL을 검사한 뒤 Claude custom connector 등록 절차를 출력합니다.

```bash
bash scripts/setup.sh
```

OAuth Remote MCP 연결 및 smoke 절차는 [Remote MCP migration guide](./docs/remote-mcp-v2-migration.md)에 있습니다.

## 대표 MCP Tool

### 포트폴리오 / 분석

- `get-portfolio-overview`
- `get-position-analysis`
- `get-performance-history`
- `get-exposure-analysis`

### 시세 / 이력

- `get-market-snapshot`
- `get-market-history`
- `get-trade-ledger`
- `get-trade-thread`
- `get-dividend-summary`

### 거버넌스 / 명령

- `get-fundamental-outlook`
- `get-signal-status`
- `get-data-catalog`, `get-data-quality`, `get-pipeline-run`
- `get-journal-review-queue`
- `run-managed-pipeline`
- `upsert-trade-journal`, `revise-trade-thread`

## 총자산 계산 방식

이 프로젝트의 canonical 총자산은 V2 `get-portfolio-overview`를 기준으로 조회합니다.

- 국내/연금 계좌 스냅샷 합계
- 해외 주식 평가액
- 해외 예수금/현금성

그리고 같은 금액을 두 관점으로 나눠 보여줍니다.

1. 계좌/통화 기준
   - 국내 자산
   - 해외 자산
   - 현금성

2. 경제적 노출 기준
   - `domestic_direct`
   - `overseas_direct`
   - `overseas_indirect`
   - `cash`
   - `unknown`

국내 상장 미국/Nasdaq/글로벌 ETF처럼 실제 투자 노출이 해외인 상품은 `overseas_indirect`, 즉 `해외우회투자`로 표시합니다.

## 종목 분류

종목 분류는 다음 우선순위를 따릅니다.

1. 로컬 override
2. KIS 종목마스터
3. 이름 heuristic
4. `unknown`

종목마스터 동기화:

```bash
uv run python scripts/sync_instrument_master.py
```

현재 구현은 실제 KRX master file에서 관찰된 그룹코드와 이름 규칙을 함께 사용합니다.

## 저장소 구조

```text
src/kis_portfolio/
├── adapters/     # MCP / remote / batch adapter
├── analytics/    # DB 기반 분석 쿼리
├── clients/      # KIS HTTP 연동
├── common/       # 순수 값 변환 / JSON-safe 공통 유틸
├── db/           # DuckDB / MotherDuck schema + repository
├── security/     # 암호화 / OAuth crypto / redaction primitives
├── services/     # 계좌/총자산/종목분류 서비스
└── remote.py     # remote MCP entrypoint
```

## 아키텍처 방향

이 프로젝트는 “MCP 툴 모음”보다 “포트폴리오 서비스”에 가깝게 설계되어 있습니다.

```text
KIS Open API
    ↓
clients / services
    ↓
DuckDB / MotherDuck / analytics
    ↓
adapters: OAuth Remote MCP, batch jobs, compatibility diagnostics, future web API
```

즉, MCP는 핵심 로직 위에 올라가는 인터페이스 중 하나입니다.
보안 primitives는 `security/`, 순수 공통 유틸은 `common/`에 두고, auth server나 DB 연결처럼 side effect가 있는 로직은 각 adapter/service/repository 경계에 둡니다.

## 로컬 저장소와 MotherDuck

기본 운영 모드는 MotherDuck입니다.

```env
KIS_DB_MODE=motherduck
```

로컬 DuckDB는 개발/백업/장애 대응용으로 사용할 수 있습니다.

```env
KIS_DB_MODE=local
```

상대경로 `KIS_DATA_DIR=var`는 프로젝트 루트 기준으로 해석됩니다.

데이터 계층, 전체 객체 카탈로그와 `main`에서 Bronze/Silver/Gold schema로 이행하는 계획은
[docs/data-catalog.md](./docs/data-catalog.md)를 참고하세요.

## 배포

- 사용자 제품 연결: `KIS Portfolio` OAuth Remote MCP
- 로컬 stdio 제품 연결: 폐기됨; 동일 이름의 진입점은 migration diagnostic만 반환
- Cloud Run auth/Remote와 managed Jobs: immutable build-once release
- Docker 베이스라인: 포함

배포 세부 내용은 [docs/deployment.md](./docs/deployment.md)를 참고하세요.
시크릿/토큰 관리 원칙은 [docs/security-and-secrets.md](./docs/security-and-secrets.md)를 참고하세요.

## 한계와 주의사항

- 투자 판단 책임은 사용자에게 있습니다.
- 이 서비스는 투자 의사결정을 지원하는 war-room이지, 투자 조언이나 자동매매 시스템이 아닙니다.
- 한국투자증권 Open API 호출 제한과 이용약관을 반드시 확인해야 합니다.
- 아직 주문 실행 기능은 활성화하지 않았습니다.
- 분석 로직은 계속 확장 중이며, 일부 상품 분류는 override 정책으로 보완될 수 있습니다.

## 공개 상태에 대해

이 저장소는 개인 실사용 기반으로 발전한 프로젝트입니다.
그래서 “예제 코드”보다는 “실제 계좌 운영과 데이터 축적”에 맞춘 구조적 선택이 많이 들어가 있습니다.

이 점이 비슷한 개인 투자/자산관리 자동화 프로젝트를 만드는 분들께는 오히려 참고가 될 수 있습니다.

## License

MIT License

이 프로젝트는 `migusdn/KIS_MCP_Server` 포크에서 출발했으며, 원본 역시 MIT License를 사용합니다.
