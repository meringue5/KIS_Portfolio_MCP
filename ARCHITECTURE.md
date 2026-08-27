# KIS Portfolio Service Architecture

이 문서는 프로젝트의 코드 배치와 장기 구조 원칙을 정리한다.

이 문서의 package tree와 DB 설명은 **현재 V1 구조**의 canonical 설명이다. 승인된 요구를 구현할
차세대 목표 구조와 전환 순서는 각각 `docs/design/kis-portfolio-v2-system-design.md`,
`docs/design/kis-portfolio-v2-delivery-plan.md`에 승인된 기준선으로 기록되어 있다. V2 architecture 승인은
개별 구현·provisioning·cutover 승인이 아니다. 관련 Work Item과 rehearsal이 완료되기 전에는 이 문서의
V1 runtime·schema·보안 계약을 대체하지 않는다.

제품 architecture의 변경·검증·배포·운영 feedback은 상위 **Project Operating System**의 통제를 받는다.
Project OS는 runtime component가 아니며 제품 code에 포함되지 않는다. canonical 운영 정책은
`docs/governance/project-operating-system.md`, trace는 `docs/traceability.md`가 소유한다. 제품 architecture
변경은 관련 ADR과 Work Item뿐 아니라 이를 검증하는 contract checker와 release evidence까지 함께
완료돼야 한다.

## 구조 원칙

루트 디렉터리는 프로젝트를 이해하고 운영하는 데 필요한 문서와 설정 진입점만 둔다.
실제 애플리케이션 코드는 `src/`, 테스트는 `tests/`, 운영 보조 스크립트는
`scripts/`, 런타임 산출물은 장기적으로 `var/` 또는 운영 환경의 안전한 데이터
디렉터리로 분리한다.

현재 기본 MCP Desktop 설정은 `kis-portfolio-mcp` console script를 실행한다.
루트 `server.py`는 수동 실행 호환용 thin shim으로 유지하며, 실제 구현은 `src/kis_portfolio/`
아래에 둔다.

```text
KIS_Portfolio_MCP/
├── README.md
├── SPEC.md
├── ARCHITECTURE.md
├── AGENTS.md
├── pyproject.toml
├── Dockerfile                 # 컨테이너 실행 베이스라인
├── server.py                  # 기존 MCP 설정 호환용 thin entrypoint
├── .agent/
│   └── skills/                # 에이전트 공통 운용 runbook
├── src/
│   └── kis_portfolio/
│       ├── __init__.py
│       ├── adapters/          # MCP, batch, auth adapter
│       ├── services/          # account, market, profit service
│       ├── clients/           # KIS API client helper
│       ├── analytics/         # DB 기반 분석 함수
│       ├── common/            # 순수 값 변환, JSON-safe helper
│       ├── security/          # 암호화, OAuth crypto, redaction primitive
│       └── db/                # DuckDB/MotherDuck 연결, 스키마, repository 함수
├── tests/                     # pytest 기반 테스트 위치
├── scripts/                   # 설치/점검/운영 스크립트
├── docs/                      # 세부 운영/설계 문서
└── var/                       # 로컬 토큰, local DB, 백업 파일 위치
```

## 현재 단계

현재 구조는 `baseline/pre-service-refactor` 이후의 서비스 전환 단계다.

- public MCP는 `src/kis_portfolio/adapters/mcp/server.py` 하나다.
- batch adapter는 `src/kis_portfolio/adapters/batch/` 아래에 둔다.
- OAuth auth server는 `src/kis_portfolio/adapters/auth/` 아래에 둔다.
- 기존 `app.py`는 새 MCP adapter를 re-export하는 compatibility shim이다.
- 기존 `db.py` 구현은 `src/kis_portfolio/db/` 패키지로 분리되어 있다.
- 루트 `server.py`는 `kis_portfolio.adapters.mcp.main()`을 호출한다.
- 루트 `db.py` 호환 wrapper는 제거했다. 내부 코드는 `kis_portfolio.db`를 직접 import한다.
- MotherDuck을 기본 운영 DB로 사용한다 (`KIS_DB_MODE=motherduck`).
- 로컬 DuckDB는 `KIS_DB_MODE=local`일 때만 사용하며 운영 트랜잭션 중심이 아니다.
- `KIS_DATA_DIR` 기본값은 프로젝트 루트 기준 `var`이다.
- 상대경로로 지정한 `KIS_DATA_DIR`, `KIS_TOKEN_DIR`, `KIS_LOCAL_DB_PATH`는 현재 작업 디렉터리가 아니라 프로젝트 루트 기준으로 해석한다.
- KIS API access token은 `kis_api_access_tokens` 테이블에 암호화 저장한다.
- legacy `var/tokens/token_{CANO}.json`은 1회 migration 입력값으로만 남기고, 정상 경로의 source of truth는 DB다.
- 주문 tool은 disabled stub이며 실제 KIS 주문 API를 호출하지 않는다.
- remote MCP는 `kis-portfolio-remote`가 제공한다.
- batch CLI는 `kis-portfolio-batch`가 제공한다.
- OAuth auth server는 `kis-portfolio-auth`가 제공한다.
- cross-cutting 보안 primitive는 `src/kis_portfolio/security/` 아래에 둔다.
- side effect 없는 공통 값 변환 helper는 `src/kis_portfolio/common/` 아래에 둔다.

## 장기 목표

MCP adapter는 tool 등록만 담당하고, 장기적으로 KIS 호출은 client/service로 계속 얇게 분리한다.

사용자-facing 제품표면은 OAuth Remote MCP 하나로 수렴한다. local stdio entrypoint는 remote parity와
운영 복구경로를 검증하는 동안 개발·test harness로 남을 수 있지만 사용자 제품 SSOT가 아니다. 현재
코드베이스의 shared core를 점진적으로 개선하며, 별도 REST microservice는 dashboard·mobile app 등 실제
consumer가 MCP와 다른 안정 계약을 요구할 때만 추가한다.

```text
src/kis_portfolio/
├── config.py
├── accounts.py
├── auth.py
├── adapters/
│   ├── auth/
│   ├── batch/
│   └── mcp/
│       └── server.py
├── clients/
│   └── kis.py
├── common/
│   └── values.py
├── services/
│   ├── account.py
│   └── kis_api.py
├── security/
│   ├── oauth_crypto.py
│   ├── redaction.py
│   └── token_encryption.py
├── db/
│   ├── catalog.py
│   ├── connection.py
│   ├── schema.py
│   └── repository.py
├── analytics/
│   ├── bollinger.py
│   └── portfolio.py
└── remote.py
```

이 구조의 핵심은 MCP를 유일한 본체로 두지 않는 것이다. KIS API client, DB repository,
analytics service를 내부 코어로 두고, MCP와 batch, 향후 HTTP/Web API는 같은 코어를 사용하는
인터페이스가 되어야 한다.

목표 패키지 경계:

- `adapters`: MCP, remote HTTP transport, OAuth auth server, batch CLI, future backend HTTP API 같은 외부 진입점
- `clients`: KIS 등 외부 API 호출을 위한 낮은 수준 HTTP client/helper
- `services`: 계좌, 포트폴리오, 마켓데이터, 주문조회, ETL orchestration의 비즈니스 유스케이스
- `analytics`: DB 기반 분석 쿼리와 war-room decision support 지표
- `db`: 연결, schema, repository, 기본 조회/쓰기 함수
- `security`: 암호화, OAuth crypto, redaction처럼 여러 레이어가 공유하는 보안 primitive
- `common`: JSON/date/numeric 변환처럼 side effect 없는 순수 유틸

`common`은 env, DB connection, HTTP client, KIS 도메인 판단 로직을 import하지 않는다. `security`는
보안 primitive만 제공하며 OAuth auth server 자체는 `adapters/auth`에 둔다.

## 비용과 실행 수명

운영 architecture의 월 실제 총비용 상한은 50,000원이다. 이 상한에는 Cloud Run, Scheduler, 저장·네트워크,
MotherDuck과 유료 데이터 provider를 포함한다.

- Remote MCP와 auth는 request-based billing, `min-instances=0`과 제한된 `max-instances`를 사용한다.
- 수집·정제·품질·signal은 예약 또는 on-demand batch job으로 실행하고 완료 즉시 종료한다.
- 상시 worker, 항상 켜진 ETL server와 dedicated warehouse compute는 기본 구성에 두지 않는다.
- MotherDuck Lite와 Cloud Run Jobs/Scheduler를 우선 사용하고 Flights·Business는 예산 내 효과를 입증해
  별도 승인받기 전까지 보류한다.
- 비용 경보는 지출 차단을 보장하지 않으므로 max instances, job timeout·retry, source call budget과
  관리된 비필수 작업 중지 경로를 함께 둔다.
- 검증된 KIS endpoint·resilience·OAuth protocol·순수 포트폴리오 계산은 재사용한다. 다만 다음 버전은
  monolithic MCP adapter, repository, runtime DDL과 operational/analytics state 결합을 V2 경계에 맞게
  재개발할 수 있다.

OAuth token 발급을 제외한 KIS 업무 REST 호출은 `clients.kis.request_kis` 단일 경로를 사용한다.
token 발급은 auth keyed lock과 전용 pacing/retry를 유지한다. `clients.kis_resilience`가 process-local
rate interval, shared cooldown, bounded queue/in-flight bulkhead, request deadline, idempotent retry와 endpoint
circuit breaker를 소유한다. services는 quote/account/history 정책을 선택하고 DB fallback의 업무 의미를
결정한다. adapter가 retry나 cache fallback을 자체 구현하지 않는다. live 주문 POST는 자동 재시도하지 않으며,
stale 데이터는 `status`, `source`, `as_of`와 age를 명시하지 않고 fresh 응답으로 반환할 수 없다.

## DB와 런타임 파일

MotherDuck이 운영 데이터베이스다. 로컬 DuckDB는 개발, 장애 대응, 주기적 백업 타겟으로만 사용한다.
`MOTHERDUCK_TOKEN`이 없을 때 조용히 로컬 파일로 fallback하지 않는다. 운영 서버에서 token이 빠졌다면
서버가 명확히 실패해야 데이터가 여러 DB로 흩어지는 사고를 막을 수 있다.

DB 객체와 schema의 관리 책임은 `docs/data-catalog.md`에 둔다. `src/kis_portfolio/db/catalog.py`는
동일 계약의 machine-readable allowlist이고, `schema.py`는 현재 물리 DDL이다. 현재 모든 객체가
`kis_portfolio.main`에 있지만 목표 namespace는 다음과 같이 분리한다.

```text
bronze   KIS raw observations and replayable snapshots
silver   normalized, deduplicated, canonical portfolio state
gold     reproducible analytics views and serving tables
control  migration ledger and reference/override data
security encrypted or hashed auth/token state
```

위 `security` schema는 현재 V1 목표 계약이다. 승인된 V2 목표는 OAuth/KIS token·lease·run request를
Seoul의 Firestore Standard database 하나로 옮기고 장기 credential과 encryption key를 Secret Manager에
두며, MotherDuck을 `bronze/silver/gold/control` 분석 plane으로 제한한다. Firestore collection allowlist와
trust-boundary별 key 격리를 적용하며, 별도 Work Item의 provisioning·migration·reconnect rehearsal과
cutover 승인 전에는 현재 runtime에 적용하지 않는다.

물리 이동은 runtime auto-DDL과 분리된 versioned migration runner, 단일 writer, backup/restore rehearsal,
row-count/aggregate reconciliation을 갖춘 뒤 수행한다. 그 전에도 logical layer 계약과 신규 객체 등록
규칙은 적용한다. live DB에만 존재하는 비관리 객체는 drift로 보고하며 자동 삭제하지 않는다.

기본 로컬 파일 배치는 다음과 같다.

```text
var/
├── tokens/                    # legacy migration source
│   └── token_{CANO}.json
├── local/
│   └── kis_portfolio.duckdb
└── backup/
```

MotherDuck 백업은 Parquet을 기본 포맷으로 둔다. `scripts/backup_motherduck.py`는 핵심 raw/cache/canonical 테이블을
`var/backup/parquet/YYYYMMDD_HHMMSS/` 아래로 export한다. 자세한 절차는 `docs/backup.md`를 참고한다.

스냅샷 raw table은 append-only로 유지한다. 분/일 단위 중복 제거와 대표값 선택은 raw write path에서
하지 않고 curated view 또는 향후 pipeline 단계에서 처리한다. 현재 `portfolio_daily_snapshots` view가
계좌별/일자별 마지막 스냅샷을 제공한다. 객체 계약과 schema 계획은 `docs/data-catalog.md`, 데이터 흐름은
`docs/data-pipeline.md`를 참고한다.

환경변수:

```text
KIS_DB_MODE=motherduck        # 기본값, 운영 중심
MOTHERDUCK_DATABASE=kis_portfolio
MOTHERDUCK_TOKEN=...
KIS_DATA_DIR=var              # 프로젝트 루트 기준 상대경로
KIS_TOKEN_ENCRYPTION_KEY=...
```

로컬 개발이나 장애 상황에서만 다음처럼 명시적으로 local 모드를 사용한다.

```text
KIS_DB_MODE=local
KIS_DATA_DIR=var
```

## 보안

시크릿과 토큰의 source of truth, DB 저장 가능 여부, 회전 절차는 `docs/security-and-secrets.md`를
canonical policy로 둔다.

아키텍처 관점의 경계는 다음과 같다.

- 장기 provider credential은 runtime env 또는 플랫폼 secret store에만 둔다.
- MotherDuck에는 운영 데이터, 암호화된 KIS token cache, OAuth digest state만 저장한다.
- auth server는 OAuth 발급과 owner login을 담당하고, remote MCP는 bearer token 검증 뒤 read-only tool을 실행한다.
- 로그와 MCP 계좌 메타데이터에는 전체 계좌번호를 노출하지 않는다. 운영 DB row와 백업은 계좌 id를
  포함할 수 있으므로 민감 데이터로 취급한다.
- raw token과 app secret은 로그, analytics table, MCP 응답에 포함하지 않는다.
- 주문 tool은 disabled stub으로 유지하고, 별도 audit/confirmation/권한 분리 설계 전에는 실제 주문 API를 호출하지 않는다.
