# KIS Portfolio Service Architecture

이 문서는 프로젝트의 코드 배치와 장기 구조 원칙을 정리한다.

## 구조 원칙

루트 디렉터리는 프로젝트를 이해하고 운영하는 데 필요한 문서와 설정 진입점만 둔다.
실제 애플리케이션 코드는 `src/`, 테스트는 `tests/`, 운영 보조 스크립트는
`scripts/`, 런타임 산출물은 장기적으로 `var/` 또는 운영 환경의 안전한 데이터
디렉터리로 분리한다.

현재 기본 MCP Desktop 설정은 `kis-portfolio-mcp` console script를 실행한다.
루트 `server.py`는 수동 실행 호환용 thin shim으로 유지하며, 실제 구현은 `src/kis_portfolio/`
아래에 둔다.

```text
KIS_MCP_Server/
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
│       ├── adapters/mcp/      # 단일 public MCP adapter
│       ├── services/          # account, market, profit service
│       ├── clients/           # KIS API client helper
│       ├── analytics/         # DB 기반 분석 함수
│       └── db/                # DuckDB/MotherDuck 연결, 스키마, repository 함수
├── tests/                     # pytest 기반 테스트 위치
├── scripts/                   # 설치/점검/운영 스크립트
├── docs/                      # 세부 운영/설계 문서
└── var/                       # 로컬 토큰, local DB, 백업 파일 위치
```

## 현재 단계

현재 구조는 `baseline/pre-service-refactor` 이후의 서비스 전환 단계다.

- public MCP는 `src/kis_portfolio/adapters/mcp/server.py` 하나다.
- 기존 `app.py`는 새 MCP adapter를 re-export하는 compatibility shim이다.
- 기존 `db.py` 구현은 `src/kis_portfolio/db/` 패키지로 분리되어 있다.
- 루트 `server.py`는 `kis_portfolio.adapters.mcp.main()`을 호출한다.
- 루트 `db.py` 호환 wrapper는 제거했다. 내부 코드는 `kis_portfolio.db`를 직접 import한다.
- MotherDuck을 기본 운영 DB로 사용한다 (`KIS_DB_MODE=motherduck`).
- 로컬 DuckDB는 `KIS_DB_MODE=local`일 때만 사용하며 운영 트랜잭션 중심이 아니다.
- `KIS_DATA_DIR` 기본값은 프로젝트 루트 기준 `var`이다.
- 상대경로로 지정한 `KIS_DATA_DIR`, `KIS_TOKEN_DIR`, `KIS_LOCAL_DB_PATH`는 현재 작업 디렉터리가 아니라 프로젝트 루트 기준으로 해석한다.
- 주문 tool은 disabled stub이며 실제 KIS 주문 API를 호출하지 않는다.
- remote MCP는 `kis-portfolio-remote`가 제공한다.

## 장기 목표

MCP adapter는 tool 등록만 담당하고, 장기적으로 KIS 호출은 client/service로 계속 얇게 분리한다.

```text
src/kis_portfolio/
├── config.py
├── accounts.py
├── auth.py
├── clients/
│   └── kis.py
├── services/
│   ├── account.py
│   └── kis_api.py
├── db/
│   ├── connection.py
│   ├── schema.py
│   └── repository.py
├── analytics/
│   ├── bollinger.py
│   └── portfolio.py
├── adapters/
│   └── mcp/
│       └── server.py
└── remote.py
```

이 구조의 핵심은 MCP를 유일한 본체로 두지 않는 것이다. KIS API client, DB repository,
analytics service를 내부 코어로 두고, MCP와 향후 HTTP/Web API는 같은 코어를 사용하는
인터페이스가 되어야 한다.

## DB와 런타임 파일

MotherDuck이 운영 데이터베이스다. 로컬 DuckDB는 개발, 장애 대응, 주기적 백업 타겟으로만 사용한다.
`MOTHERDUCK_TOKEN`이 없을 때 조용히 로컬 파일로 fallback하지 않는다. 운영 서버에서 token이 빠졌다면
서버가 명확히 실패해야 데이터가 여러 DB로 흩어지는 사고를 막을 수 있다.

기본 로컬 파일 배치는 다음과 같다.

```text
var/
├── tokens/
│   └── token_{CANO}.json
├── local/
│   └── kis_portfolio.duckdb
└── backup/
```

MotherDuck 백업은 Parquet을 기본 포맷으로 둔다. `scripts/backup_motherduck.py`는 네 개의 핵심 테이블을
`var/backup/parquet/YYYYMMDD_HHMMSS/` 아래로 export한다. 자세한 절차는 `docs/backup.md`를 참고한다.

스냅샷 raw table은 append-only로 유지한다. 분/일 단위 중복 제거와 대표값 선택은 raw write path에서
하지 않고 curated view 또는 향후 pipeline 단계에서 처리한다. 현재 `portfolio_daily_snapshots` view가
계좌별/일자별 마지막 스냅샷을 제공한다. 자세한 방향은 `docs/data-pipeline.md`를 참고한다.

환경변수:

```text
KIS_DB_MODE=motherduck        # 기본값, 운영 중심
MOTHERDUCK_DATABASE=kis_portfolio
MOTHERDUCK_TOKEN=...
KIS_DATA_DIR=var              # 프로젝트 루트 기준 상대경로
```

로컬 개발이나 장애 상황에서만 다음처럼 명시적으로 local 모드를 사용한다.

```text
KIS_DB_MODE=local
KIS_DATA_DIR=var
```

## 보안

웹 호스팅을 도입할 때는 조회 기능과 주문 기능의 권한 경계를 분리하고, 로그에 token, app secret,
계좌번호 전체가 남지 않도록 별도 보안 정책을 문서화해야 한다.
