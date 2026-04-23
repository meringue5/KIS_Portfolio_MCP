# KIS Portfolio Service — Codex 컨텍스트

이 프로젝트는 [migusdn/KIS_MCP_Server](https://github.com/migusdn/KIS_MCP_Server)를 포크하여,
한국투자증권 Open API 기반 개인 포트폴리오 조회/저장/분석 서비스로 전환한 프로젝트입니다.
MCP는 primary adapter이며, core service는 MCP에 종속되지 않아야 합니다.

---

## 프로젝트 구조

```
KIS_Portfolio_MCP/
├── server.py          # 기존 MCP 설정 호환용 thin entrypoint
├── src/
│   └── kis_portfolio/
│       ├── adapters/  # MCP/remote/batch 등 외부 adapter
│       ├── services/  # 포트폴리오/account/market service
│       ├── clients/   # KIS API client helper
│       └── db/        # DuckDB/MotherDuck 연결, 스키마, 저장/조회 함수
├── tests/             # pytest 테스트 위치
├── docs/              # 세부 운영/설계 문서
├── var/               # 로컬 토큰, local DB, 백업 파일 위치
├── .env.example       # 환경변수 템플릿 (실제 값은 .env 또는 claude_desktop_config.json)
├── AGENTS.md          # 이 파일 — Codex용 프로젝트 컨텍스트
├── ARCHITECTURE.md    # 코드 배치와 장기 구조 원칙
├── SPEC.md            # 요구사항 및 아키텍처 의사결정 기록
└── pyproject.toml     # uv 기반 의존성 관리
```

---

## 서버 실행 방법

Codex Desktop에서 MCP로 자동 실행됨. 수동 테스트 시:

```bash
cd /path/to/KIS_Portfolio_MCP
uv run python server.py
```

Claude Desktop이 띄운 KIS MCP 프로세스를 내릴 때:

```bash
bash scripts/stop_mcp.sh
```

---

## MCP 구성 (claude_desktop_config.json)

기본 Claude Desktop 설정에는 단일 MCP 서버 `kis-portfolio`만 등록한다.
5개 계좌 설정은 `KIS_APP_KEY_{ACCOUNT}`, `KIS_APP_SECRET_{ACCOUNT}`, `KIS_CANO_{ACCOUNT}`,
`KIS_ACNT_PRDT_CD_{ACCOUNT}` 형태의 suffixed env로 `kis-portfolio`에 주입한다.

| 계좌 라벨 | ACNT_PRDT_CD | 계좌 종류 |
|----------|--------------|----------|
| ria      | 01           | 위험자산 일임 |
| isa      | 01           | ISA |
| brokerage| 01           | 일반 위탁 |
| irp      | 29           | IRP (퇴직연금) |
| pension  | 22           | 연금저축 |

`kis-api-search`는 기본 등록하지 않는다. 필요할 때만 별도 reference MCP로 수동 실행한다.

---

## 핵심 설계 규칙

### 공통 운용 스킬
에이전트 공통 운용 절차는 `.agent/skills/` 아래에 둔다.
native skill discovery를 지원하지 않는 환경에서도 관련 작업 전에는 해당 `SKILL.md`를 읽고 따른다.

- `.agent/skills/kis-portfolio-ops/SKILL.md`: 포트폴리오 조회, 합산, 변화 분석 운용 절차
- `.agent/skills/kis-architecture-audit/SKILL.md`: SPEC/ARCHITECTURE/코드 구조 계약 정합성 점검
- `.agent/skills/kis-mcp-surface-audit/SKILL.md`: public MCP tool catalog와 응답 안전성 점검
- `.agent/skills/kis-api-capability-implementation/SKILL.md`: KIS Open API 신규 기능 추가 절차
- `.agent/skills/kis-warehouse-contract/SKILL.md`: MotherDuck/DuckDB schema, repository, backup 계약 점검

### KIS access token DB cache
KIS access token은 `kis_api_access_tokens` 테이블에 **암호화 저장**한다.
cache key는 `sha256("{KIS_ACCOUNT_TYPE}:{KIS_CANO}:{KIS_APP_KEY}")` 규칙을 사용한다.

- 기본 source of truth: DB (`MotherDuck` 또는 local DuckDB)
- legacy migration 입력값: 프로젝트 루트 기준 `var/tokens/token_{CANO}.json`
- 토큰 만료 판단: `expires_at - 10분`
- refresh 직렬화: 프로세스 내 keyed async lock
- 필수 env: `KIS_TOKEN_ENCRYPTION_KEY`

### IRP vs 연금저축 API 분기
- **IRP (ACNT_PRDT_CD=29)**: 전용 pension API 사용
  - endpoint: `/uapi/domestic-stock/v1/trading/pension/inquire-balance`
  - TR_ID: `TTTC2208R`
- **연금저축 (ACNT_PRDT_CD=22)**: 표준 잔고 API 사용 (MTS 화면 구조로 확인)
  - endpoint: `/uapi/domestic-stock/v1/trading/inquire-balance`
  - TR_ID: `TTTC8434R`

```python
is_pension = acnt_prdt_cd == "29"  # IRP만 pension API, 22(연금저축)는 표준 API
```

### 환경변수 주입 방식
API 키와 계좌정보는 `claude_desktop_config.json`의 `env` 블록에서 주입.
`server.py`는 새 `kis_portfolio.adapters.mcp` shim이며, `.env` + `python-dotenv`로도 대체 가능하다.

`kis-portfolio`는 `KIS_APP_KEY_{ACCOUNT}`, `KIS_APP_SECRET_{ACCOUNT}`, `KIS_CANO_{ACCOUNT}`,
`KIS_ACNT_PRDT_CD_{ACCOUNT}` 형태의 계좌별 suffixed env 전체를 받는다.
오케스트레이터는 내부적으로 짧은 scoped env context를 사용해 인증/토큰/잔고 로직을 재사용하며,
전체 계좌 refresh는 순차 실행한다.

### 주문 tool stub
`submit-stock-order`, `submit-overseas-stock-order`는 disabled stub이다.
실제 KIS 주문 API를 호출하지 않는다. 주문 기능은 audit/confirmation 설계 전까지 구현하지 않는다.

### Remote MCP 인증
원격 Streamable HTTP MCP는 `kis-portfolio-remote` 엔트리포인트로 실행한다.
`/mcp` endpoint는 `Authorization: Bearer <KIS_REMOTE_AUTH_TOKEN>` 헤더를 요구한다.
`/health`만 인증 없이 노출한다. Cloud Run에서는 `/healthz` 같은 `z` suffix 경로가 예약 경로와 충돌할 수 있으므로 운영 health check는 `/health`를 사용한다. 운영 환경에서 `KIS_REMOTE_AUTH_DISABLED=true`를 사용하지 않는다.

---

## 트러블슈팅 기록

### token.json 충돌
- **증상**: RIA 토큰으로 ISA API 호출 → 인증 오류
- **원인**: 여러 인스턴스가 동일 토큰 파일을 공유
- **해결**: 초기에는 `token_{CANO}.json` 형식으로 분리했고, 현재는 재배포/cold start에서도 유지되도록 DB-backed encrypted cache로 전환

### koreainvestment-mcp Python 버전 오류
- **증상**: `uv run python server.py` 실행 시 pandas 빌드 실패
- **원인**: Python 3.14에서 pandas 미지원
- **해결**: `uv sync --python 3.13` 후 `--python 3.13` 플래그 명시

### 연금저축 appSecret 파싱 오류
- **증상**: 토큰 발급 실패
- **원인**: KIS 발급 appSecret 끝에 `]` 문자 포함 (잘못된 base64)
- **해결**: `]` 문자 제거

### IRP/연금저축 "계좌 없음"
- **증상**: `inquery-balance` 호출 시 계좌 조회 실패
- **원인**: ACNT_PRDT_CD가 01이 아닌 계좌는 별도 처리 필요
- **해결**: 환경변수 `KIS_ACNT_PRDT_CD` 추가 및 API 분기 로직 구현

---

## 관련 레포지토리

| 레포 | 용도 |
|------|------|
| `~/workspace/KIS_Portfolio_MCP` | **이 서버** (메인) |
| `~/workspace/koreainvestment-mcp` | API 문서 검색용 MCP (kis-api-search) |
| `~/workspace/stock_manager_llm` | KIS Open API 레퍼런스 코드 (참조용) |

---

## 데이터베이스 (MotherDuck / DuckDB)

`src/kis_portfolio/db/` 패키지가 DB 레이어를 담당. MCP tool 등록은
`src/kis_portfolio/adapters/mcp/server.py`가 담당하고, 핵심 로직은 `services/` 아래에 둔다.

**연결 전략 (명시적 모드):**
```python
# 기본: MotherDuck. token이 없으면 로컬 fallback하지 않고 실패.
KIS_DB_MODE=motherduck
MOTHERDUCK_DATABASE=kis_portfolio
MOTHERDUCK_TOKEN=... → md:kis_portfolio

# 개발/장애 대응/백업용 local 모드
KIS_DB_MODE=local → var/local/kis_portfolio.duckdb
```

상대경로 `KIS_DATA_DIR=var`는 현재 작업 디렉터리가 아니라 프로젝트 루트 기준으로 해석.

**테이블 요약:**

| 테이블 | 저장 방식 | 트리거 |
|--------|----------|--------|
| `price_history` | INSERT OR IGNORE | `get-stock-history`, `get-overseas-stock-history` 호출 시 |
| `exchange_rate_history` | INSERT OR IGNORE | `get-exchange-rate-history` 호출 시 |
| `portfolio_snapshots` | append-only INSERT | `get-account-balance`, `refresh-all-account-snapshots` 호출 시 |
| `overseas_asset_snapshots` | append-only INSERT | `get-total-asset-overview(save_snapshot=True)` 호출 시 |
| `asset_overview_snapshots` | append-only INSERT | `get-total-asset-overview(save_snapshot=True)` 호출 시 |
| `asset_holding_snapshots` | append-only INSERT | `get-total-asset-overview(save_snapshot=True)` 호출 시 |
| `order_history` | append-only INSERT | `kis-portfolio-batch collect-domestic-order-history --date today` 실행 시 |
| `instrument_master` | upsert | `scripts/sync_instrument_master.py` 실행 시 |
| `instrument_classification_overrides` | upsert | 로컬 override 등록 시 |
| `trade_profit_history` | append-only INSERT | `get-period-trade-profit`, `get-overseas-period-profit` 호출 시 |

**DB 전용 조회 툴 (API 호출 없음):**
- `get-portfolio-history` — 계좌 잔고 스냅샷 이력
- `get-token-status` — 현재 MCP 인스턴스의 접근토큰 캐시 상태 조회 (토큰 값 제외)
- `get-latest-portfolio-summary` — 국내/연금 feeder 최신 합산 요약
- `get-total-asset-overview` — canonical 총자산 요약, 해외 예수금 포함, `해외우회투자` 분류/차트 데이터
- `get-total-asset-history`, `get-total-asset-daily-change`
- `get-total-asset-trend`, `get-total-asset-allocation-history`
- `get-portfolio-daily-change` — 국내/연금 feeder 일별 대표 스냅샷 기준 평가금액 변화
- `get-price-from-db` — 캐시된 주가 이력
- `get-exchange-rate-from-db` — 캐시된 환율 이력

**백업:**
- 운영 DB는 MotherDuck
- Parquet 백업 스크립트: `uv run python scripts/backup_motherduck.py`
- 기본 백업 위치: `var/backup/parquet/YYYYMMDD_HHMMSS/`

**정제/분석 방향:**
- `portfolio_snapshots`는 raw append-only로 유지
- `overseas_asset_snapshots`는 해외계좌 raw/aggregate feeder로 유지
- `asset_overview_snapshots`는 canonical 총자산 aggregate 저장소로 사용
- `asset_holding_snapshots`는 canonical snapshot 기준 정규화 보유 row를 저장
- 분/일 단위 중복 제거는 저장 시점이 아니라 curated view/pipeline에서 처리
- 현재 일별 대표값 view: `portfolio_daily_snapshots`
- 현재 canonical 일별 대표값 view: `asset_overview_daily_snapshots`
- 국내 상장 해외 ETF/REIT 분류는 `override > KIS master group code > 이름 heuristic > unknown`
- 상세 문서: `docs/data-pipeline.md`

## KIS Portfolio MCP

실행 명령은 `kis-portfolio-mcp`.

## KIS Portfolio Batch

실행 명령은 `kis-portfolio-batch`.

현재 배치 command:
- `collect-domestic-order-history --date today`

노출 tool:
- `get-configured-accounts`
- `get-all-token-statuses`
- `get-account-balance`
- `refresh-all-account-snapshots`
- `get-stock-price`, `get-stock-ask`, `get-stock-info`, `get-stock-history`
- `get-overseas-stock-price`, `get-overseas-stock-history`
- `get-overseas-balance`, `get-overseas-deposit`
- `get-period-trade-profit`, `get-overseas-period-profit`
- `get-order-list`, `get-order-detail`
- `submit-stock-order`, `submit-overseas-stock-order` (disabled stub)
- `get-latest-portfolio-summary`
- `get-total-asset-overview`
- `get-total-asset-history`, `get-total-asset-daily-change`
- `get-total-asset-trend`, `get-total-asset-allocation-history`
- `get-portfolio-daily-change`
- `get-portfolio-anomalies`, `get-portfolio-trend`, `get-bollinger-bands`

기존 fork의 `inquery-*` tool alias는 기본 MCP 표면에 등록하지 않는다.
토큰 원문과 secret은 응답에 포함하지 않는다. 계좌번호는 계좌 메타데이터에서는 항상 마스킹한다.

## 신규 환경 온보딩

새 맥이나 새 클론 후 Codex Desktop MCP를 복원하는 절차.

### 전제조건
- `.env` 파일: 구글드라이브 등에 안전하게 보관한 사본 복사
- GitHub CLI (`gh`) 설치 및 `gh auth login` 완료
- `uv` 설치: `curl -LsSf https://astral.sh/uv/install.sh | sh`

### 복원 절차

```bash
# 1. 레포 클론
git clone https://github.com/meringue5/KIS_Portfolio_MCP.git ~/workspace/KIS_Portfolio_MCP
cd ~/workspace/KIS_Portfolio_MCP

# 2. .env 파일 복사 (구글드라이브 등에서)
cp /path/to/backup/.env .

# 3. 셋업 스크립트 실행 (1회로 끝)
bash scripts/setup.sh
```

`setup.sh`가 자동으로 처리하는 것:
- `.env` 유효성 검사 (빠진 변수 즉시 오류)
- `uv sync` (Python 의존성 설치)
- `~/Library/Application Support/Claude/claude_desktop_config.json` 생성
- 기존 설정 백업 (`claude_desktop_config.json.bak`)

### 이후
Claude Desktop 재시작 → `kis-portfolio` 단일 MCP 서버 스폰 확인

### 환경변수 레퍼런스
`.env.example` 참고. 계좌별 변수명 패턴:
```
KIS_APP_KEY_{ACCOUNT}=
KIS_APP_SECRET_{ACCOUNT}=
KIS_CANO_{ACCOUNT}=
KIS_ACNT_PRDT_CD_{ACCOUNT}=
```
`{ACCOUNT}` = `RIA`, `ISA`, `IRP`, `PENSION`, `BROKERAGE`

---

## 작업 큐

자주 바뀌는 예정 작업은 `TODO.md`에서 관리한다. 결정된 설계 원칙은 `SPEC.md`에만 남긴다.
