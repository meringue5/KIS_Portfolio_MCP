# KIS Portfolio Service

[![Python 3.13+](https://img.shields.io/badge/python-3.13+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-yellow.svg)](./LICENSE)

한국투자증권(KIS) Open API를 기반으로 만든 개인 포트폴리오 서비스입니다.
여러 계좌의 국내/해외 자산을 한 번에 조회하고, MotherDuck/DuckDB에 스냅샷을 쌓아 이력과 비중 변화를 분석할 수 있습니다.

이 프로젝트는 원래 `migusdn/KIS_MCP_Server` 포크에서 출발했지만, 현재는 단일 MCP 서버와 포트폴리오 분석 서비스 구조를 중심으로 재설계된 상태입니다.

한국투자증권과 무관한 비공식 오픈소스 프로젝트입니다.

## 한눈에 보기

- 여러 KIS 계좌를 하나의 MCP 서버 `kis-portfolio`로 묶어서 조회
- 국내 자산 + 해외 주식 + 해외 예수금까지 합친 canonical 총자산 계산
- 국내 상장 해외 ETF/REIT를 `해외우회투자`로 분리 표시
- MotherDuck/DuckDB에 스냅샷을 저장하고 총자산 이력/일간 변화/추세 분석
- Claude Desktop에서 바로 사용할 수 있는 로컬 MCP 셋업 스크립트 제공
- 원격 MCP 배포를 위한 HTTP 엔트리포인트와 컨테이너 베이스라인 포함

## 이런 분에게 맞습니다

- 한국투자증권 계좌를 여러 개 운용하고 있고, 전체 자산을 한 번에 보고 싶은 분
- 국내/해외/현금/해외우회투자 비중을 LLM 대화로 확인하고 싶은 분
- MCP를 단순 조회 도구가 아니라 개인 투자 데이터 레이어로 키우고 싶은 분
- 나중에 웹 서비스, 배치 분석, 원격 MCP까지 확장할 구조를 원하는 분

## 현재 제공 기능

### 1. 계좌/포트폴리오

- 등록된 계좌 목록 조회
- 전체 계좌 국내/연금 스냅샷 갱신
- 특정 계좌 잔고 조회
- 전체 자산현황 요약
  - 국내 자산
  - 해외 주식 평가액
  - 해외 예수금/현금성
  - 총자산
  - 계좌 기준 비중
  - 경제적 노출 기준 비중

### 2. 시세/이력

- 국내 주식 현재가 / 호가 / 기본정보
- 국내 주식 가격 이력
- 해외 주식 현재가 / 가격 이력
- 환율 이력

### 3. 손익/분석

- 국내 주식 기간별 손익
- 해외 주식 기간별 손익
- 총자산 이력
- 총자산 일간 변화
- 총자산 추세
- 총자산 allocation history
- 국내/연금 feeder 기준 포트폴리오 변화, 추세, 이상치

### 4. 데이터 저장

- `portfolio_snapshots`: 국내/연금 raw 스냅샷
- `overseas_asset_snapshots`: 해외 자산 raw/aggregate 스냅샷
- `asset_overview_snapshots`: canonical 총자산 스냅샷
- `asset_holding_snapshots`: 총자산 스냅샷 기준 정규화 보유 row
- `order_history`: 국내 주문/체결 raw observation
- `instrument_master`: KIS 종목마스터 적재 결과
- `instrument_classification_overrides`: 로컬 수동 분류 override

## 중요한 현재 상태

이 프로젝트는 현재 **조회/분석 중심**입니다.

- `submit-stock-order`
- `submit-overseas-stock-order`

두 주문 tool은 **disabled stub**이며, 실제 주문 API를 호출하지 않습니다.
즉, 지금 단계에서는 실수로 주문이 나가는 구조가 아닙니다.

## 예시 질문

Claude Desktop 같은 MCP 클라이언트에서 아래처럼 물어볼 수 있습니다.

- `내 전체 자산현황 보여줘`
- `국내 자산 대비 해외 자산 비율 알려줘`
- `해외우회투자까지 포함해서 자산 비중 정리해줘`
- `최근 30일 총자산 변화 보여줘`
- `ISA와 연금 계좌를 따로 비교해줘`

## 설치

### 준비물

- Python 3.13+
- [uv](https://astral.sh/uv)
- 한국투자증권 Open API 앱 키 / 시크릿
- 계좌번호 및 계좌상품코드
- MotherDuck 토큰 권장

## 빠른 시작

```bash
git clone https://github.com/meringue5/KIS_Portfolio_MCP.git
cd KIS_Portfolio_MCP
cp .env.example .env
```

`.env`에 실제 값을 채운 뒤:

```bash
uv sync
bash scripts/setup.sh
```

이 스크립트가 하는 일:

- `.env` 필수값 검사
- 의존성 설치
- `var/` 런타임 디렉터리 생성
- Claude Desktop용 `claude_desktop_config.json` 생성
- `kis-portfolio` MCP 서버 등록

마지막으로 Claude Desktop을 재시작하면 됩니다.

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
```

전체 예시는 [.env.example](./.env.example)를 참고하세요.

## 실행 방법

### 로컬 MCP 서버

```bash
uv run kis-portfolio-mcp
```

또는 루트 shim:

```bash
uv run python server.py
```

### 원격 MCP 서버

```bash
uv run kis-portfolio-remote
```

원격 배포는 `/mcp` HTTP endpoint를 사용합니다. ChatGPT 호환과 운영 배포는 `KIS_REMOTE_AUTH_MODE=oauth`를 권장하며, `KIS_REMOTE_AUTH_TOKEN` 기반 bearer는 빠른 실험용 fallback입니다. 자세한 내용은 [docs/deployment.md](./docs/deployment.md)를 참고하세요.

### 배치 CLI

```bash
uv run kis-portfolio-batch collect-domestic-order-history --date today
```

이 명령은 Asia/Seoul 기준 `today` 날짜를 풀어 전 계좌의 당일 국내 주문/체결 이력을 조회하고 `order_history`에 append-only로 저장합니다.
Cloud Scheduler/cron 기준 첫 스케줄 예시는 평일 `15:35` KST, cron 표현으로는 `35 15 * * 1-5` 입니다.

### ChatGPT 앱 메타데이터 권장값

ChatGPT에서 custom app으로 연결할 때는 아래처럼 app-level metadata를 명시해 두는 편이 안정적입니다.

- Connector name: `KIS Portfolio`
- Description: `Use this app when you need Korean Investment & Securities (KIS) portfolio balances, total asset allocation, cached price history, exchange-rate history, or saved portfolio analytics for configured accounts. Prefer refresh-all-account-snapshots for the latest cross-account portfolio refresh and get-total-asset-overview for the combined domestic and overseas asset view. Do not use this app for internet news, general market research, or live order placement; order tools are disabled stubs.`

도구 설명이나 입력 스키마를 바꾼 뒤에는 ChatGPT Settings에서 connector `Refresh`를 눌러 frozen metadata snapshot을 갱신하세요.

### GitHub push 기반 Cloud Run 배포

이 저장소에는 `master` 브랜치 push 시 Cloud Run `auth` / `remote` 서비스를 순서대로 배포하는 GitHub Actions workflow가 포함되어 있습니다.

- workflow 파일: [.github/workflows/deploy-cloud-run.yml](./.github/workflows/deploy-cloud-run.yml)
- 기본 흐름: `push to master -> uv run pytest -> auth deploy -> remote deploy`
- 수동 실행: GitHub Actions에서 `workflow_dispatch`로 `all`, `auth`, `remote` 중 하나를 선택

필수 GitHub Environment/Repository secrets:

- `KIS_DEPLOY_ENV`
  - 배포용 `.env` 전체 내용을 그대로 담은 멀티라인 secret
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

## Claude Desktop 연결

이 저장소는 Claude Desktop 기준 자동 설정을 지원합니다.

```bash
bash scripts/setup.sh
```

예시 설정 파일은 [docs/examples/claude_desktop_config.example.json](./docs/examples/claude_desktop_config.example.json)에 있습니다.

## 대표 MCP Tool

### 포트폴리오 / 계좌

- `get-configured-accounts`
- `get-all-token-statuses`
- `get-account-balance`
- `refresh-all-account-snapshots`
- `get-total-asset-overview`

### 시세 / 이력

- `get-stock-price`
- `get-stock-ask`
- `get-stock-info`
- `get-stock-history`
- `get-overseas-stock-price`
- `get-overseas-stock-history`
- `get-exchange-rate-history`

### 손익 / 분석

- `get-period-trade-profit`
- `get-overseas-period-profit`
- `get-total-asset-history`
- `get-total-asset-daily-change`
- `get-total-asset-trend`
- `get-total-asset-allocation-history`
- `get-portfolio-history`
- `get-portfolio-daily-change`
- `get-portfolio-trend`
- `get-portfolio-anomalies`
- `get-bollinger-bands`

## 총자산 계산 방식

이 프로젝트의 canonical 총자산은 `get-total-asset-overview`를 기준으로 계산합니다.

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
├── db/           # DuckDB / MotherDuck schema + repository
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
adapters: local MCP, remote MCP, batch jobs, future web API
```

즉, MCP는 핵심 로직 위에 올라가는 인터페이스 중 하나입니다.

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

## 배포

- 로컬 stdio MCP: 가능
- Claude Desktop 연결: 가능
- 원격 MCP HTTP 엔드포인트: 가능
- Docker 베이스라인: 포함

배포 세부 내용은 [docs/deployment.md](./docs/deployment.md)를 참고하세요.

## 한계와 주의사항

- 투자 판단 책임은 사용자에게 있습니다.
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
