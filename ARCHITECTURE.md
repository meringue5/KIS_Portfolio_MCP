# KIS MCP Server Architecture

이 문서는 프로젝트의 코드 배치와 장기 구조 원칙을 정리한다.

## 구조 원칙

루트 디렉터리는 프로젝트를 이해하고 운영하는 데 필요한 문서와 설정 진입점만 둔다.
실제 애플리케이션 코드는 `src/`, 테스트는 `tests/`, 운영 보조 스크립트는
`scripts/`, 런타임 산출물은 장기적으로 `var/` 또는 운영 환경의 안전한 데이터
디렉터리로 분리한다.

현재 MCP Desktop 설정은 레포 루트의 `server.py`를 직접 실행하므로, 루트의
`server.py`와 `db.py`는 당분간 호환 shim으로 유지한다. 실제 구현은
`src/kis_mcp_server/` 아래에 둔다.

```text
KIS_MCP_Server/
├── README.md
├── SPEC.md
├── ARCHITECTURE.md
├── AGENTS.md
├── pyproject.toml
├── server.py                  # 기존 MCP 설정 호환용 thin entrypoint
├── db.py                      # 기존 import db 호환용 wrapper
├── src/
│   └── kis_mcp_server/
│       ├── __init__.py
│       ├── app.py             # MCP app, tool 등록, 현재 main 구현
│       └── db.py              # DuckDB/MotherDuck 연결, 스키마, repository 함수
├── tests/                     # pytest 기반 테스트 위치
├── scripts/                   # 설치/점검/운영 스크립트
├── docs/                      # 세부 운영/설계 문서
└── var/                       # 로컬 토큰, local DB, 백업 파일 위치
```

## 현재 단계

이번 구조 정리는 1단계 마이그레이션이다.

- 기존 `server.py` 구현을 `src/kis_mcp_server/app.py`로 이동했다.
- 기존 `db.py` 구현을 `src/kis_mcp_server/db.py`로 이동했다.
- 루트 `server.py`는 `kis_mcp_server.app.main()`을 호출한다.
- 루트 `db.py`는 `kis_mcp_server.db`를 re-export한다.
- MotherDuck을 기본 운영 DB로 사용한다 (`KIS_DB_MODE=motherduck`).
- 로컬 DuckDB는 `KIS_DB_MODE=local`일 때만 사용하며 운영 트랜잭션 중심이 아니다.
- `KIS_DATA_DIR` 기본값은 프로젝트 루트 기준 `var`이다.
- 상대경로로 지정한 `KIS_DATA_DIR`, `KIS_TOKEN_DIR`, `KIS_LOCAL_DB_PATH`는 현재 작업 디렉터리가 아니라 프로젝트 루트 기준으로 해석한다.

## 장기 목표

현재 `app.py`는 아직 많은 책임을 가진다. 이후 단계에서 다음 모듈로 나누는 것을 목표로 한다.

```text
src/kis_mcp_server/
├── config.py
├── accounts.py
├── auth.py
├── kis_client/
│   ├── base.py
│   ├── domestic.py
│   ├── overseas.py
│   ├── pension.py
│   └── exchange.py
├── db/
│   ├── connection.py
│   ├── schema.py
│   └── repository.py
├── analytics/
│   ├── bollinger.py
│   └── portfolio.py
├── tools/
│   ├── account_tools.py
│   ├── market_tools.py
│   ├── order_tools.py
│   ├── db_tools.py
│   └── analytics_tools.py
└── web/
    └── app.py
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
