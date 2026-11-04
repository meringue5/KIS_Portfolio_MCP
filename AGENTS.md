# KIS Portfolio Service — Codex 컨텍스트

이 프로젝트는 [migusdn/KIS_MCP_Server](https://github.com/migusdn/KIS_MCP_Server)를 포크하여,
한국투자증권 Open API 기반 개인 포트폴리오 조회/저장/분석 서비스로 전환한 프로젝트입니다.
MCP는 primary adapter이며, core service는 MCP에 종속되지 않아야 합니다.

운영 의미 요약은 `docs/operating-model.md`, 현행 domain 규칙은 `docs/design/README.md`에서 찾는다.
구축 타임라인을 기본 context로 읽지 않고, 사례가 필요할 때만 `docs/history/README.md`의 압축 원문/고정 링크로 내려간다.
정확한 정책·승인·계약의 기존 소유권은 그대로 유지한다.

---

## 프로젝트 구조

```
KIS_Portfolio_MCP/
├── server.py          # 폐기된 로컬 V1 연결에 migration guidance를 반환하는 diagnostic
├── src/
│   └── kis_portfolio/
│       ├── adapters/  # MCP/remote/batch 등 외부 adapter
│       ├── services/  # 포트폴리오/account/market service
│       ├── clients/   # KIS API client helper
│       ├── common/    # 순수 값 변환 / JSON-safe helper
│       ├── security/  # 암호화 / OAuth crypto / redaction primitives
│       └── db/        # DuckDB/MotherDuck 연결, 스키마, 저장/조회 함수
├── tests/             # pytest 테스트 위치
├── docs/              # 세부 운영/설계 문서
│   └── security-and-secrets.md # 시크릿/source of truth/토큰 저장 정책
├── var/               # 로컬 토큰, local DB, 백업 파일 위치
├── .env.example       # 환경변수 템플릿 (실제 값은 .env 또는 claude_desktop_config.json)
├── AGENTS.md          # 이 파일 — Codex용 프로젝트 컨텍스트
├── ARCHITECTURE.md    # 코드 배치와 장기 구조 원칙
├── SPEC.md            # 요구사항 및 아키텍처 의사결정 기록
└── pyproject.toml     # uv 기반 의존성 관리
```

---

## 서버 실행 방법

정본 제품 연결은 `KIS Portfolio` OAuth Remote MCP다. `kis-portfolio-mcp`와 루트 `server.py`는 폐기된
로컬 V1 연결에 명시적 migration guidance를 반환하고 종료하며 MCP 서버를 시작하지 않는다.

---

## MCP 구성

Claude web/Desktop/mobile에는 같은 public HTTPS `/mcp` URL을 custom connector `KIS Portfolio`로 등록한다.
Codex에는 같은 URL을 DCR 방식으로 등록하고 owner browser consent를 거친 뒤 새 task에서 실제 tool 호출을 검증한다.
계좌 credential은 클라이언트에 주입하지 않으며 운영 batch/secret boundary에만 둔다. 연결 절차와 V1 tool
migration은 `docs/remote-mcp-v2-migration.md`가 소유한다.

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

### Project Operating System

이 저장소의 개발·운영 상위 체계는 **Project Operating System(Project OS, 프로젝트 운영체계)** 이다.
canonical policy는 `docs/governance/project-operating-system.md`, 요구·결정·작업·증거 연결은
`docs/traceability.md`가 담당한다. `Project Governance`는 Project OS의 결정·권한·변경통제 하위 영역이다.

정기 점검은 `docs/operations/steady-state-operations-runbook.md`, 장애는 `docs/troubleshooting.md`,
기능 수정은 `docs/traceability.md`의 해당 행, 우선순위·후보는 `TODO.md`에서 시작한다.
운영에서 반복 적용할 판단은 소유 계약을 갱신하고, 당시 증거는 사례 링크로 연결한다.

repository를 변경하거나 비사소한 버그·요구·incident를 분류하기 전에는 다음을 수행한다.

1. `.agent/skills/kis-project-os/SKILL.md`를 읽는다.
2. active Work Item과 `docs/traceability.md`를 확인한다.
3. 변경을 defect/clarification/change/architecture/incident/maintenance/governance로 분류한다.
4. 동시에 하나의 구현 Work Item만 `in_progress`로 둔다.
5. 작업 중 `bash scripts/check.sh quick`, 종료 전 `bash scripts/check.sh full`을 실행한다.
6. 사용자 노출 변경은 실제 승인 client/transport의 즉시 재현 가능한 positive·partial·error 시나리오를
   실행하고, 발견사항을 소유 Work Item에 연결한 뒤에만 완료한다. CI·배포·health smoke만으로 완료하지 않는다.

운영 증거를 모으는 항목은 `stabilizing`으로 표시한다. 인수 후 동일 outcome의 결함과 유지보수는
Project OS §6.4의 운영 교정 경로에 연결하고 닫힌 기준선을 보존한다. 활성 delivery의 milestone dependency는 DAG로 유지한다.
rollback과 보정은 `discovered_from`/`rollback_of`/`supersedes` 관계의 새 sub-item 또는 Work Item으로
append한다. 선행 milestone 안정화 중 후속 milestone은 `in_progress`로 전환해 registry의 reviewed
continuous isolated-overlap Work Item을 dependency 순서대로 하나씩 `verified`까지 계속 진행한다. production
migration·배포·source activation·public cutover는 선행 milestone `closed` 전까지 금지한다.

Issue/Work Item은 추적 레코드이며 결정 SSOT가 아니다. 승인된 제품 요구는 `docs/requirements/`, 장기
architecture decision은 `SPEC.md`, 데이터 계약은 `docs/data-catalog.md`가 소유한다. Skill, hook과 CI는
정책을 복제하지 않고 공통 하네스를 호출한다. 구현에 맞춰 계약을 조용히 완화하지 않는다.

마일스톤 기준선과 Work Item 불변 identity/dependency/sub-item 관계는
`governance/project/milestones.toml`이 소유하고 사람이 검토하는 기준선은 `docs/milestones/`에 둔다.
발급된 `WI-NNN`은 재사용·재번호화하지 않는다. 새 발견은 기존 outcome 안이면 `WI-NNN-SNN`, 독립
outcome이면 현재 최댓값 다음 WI로 append한다.

### 공통 운용 스킬
에이전트 공통 운용 절차는 `.agent/skills/` 아래에 둔다.
native skill discovery를 지원하지 않는 환경에서도 관련 작업 전에는 해당 `SKILL.md`를 읽고 따른다.

- `.agent/skills/kis-portfolio-ops/SKILL.md`: 포트폴리오 조회, 합산, 변화 분석 운용 절차
- `.agent/skills/kis-architecture-audit/SKILL.md`: SPEC/ARCHITECTURE/코드 구조 계약 정합성 점검
- `.agent/skills/kis-mcp-surface-audit/SKILL.md`: public MCP tool catalog와 응답 안전성 점검
- `.agent/skills/kis-api-capability-implementation/SKILL.md`: KIS Open API 신규 기능 추가 절차
- `.agent/skills/kis-warehouse-contract/SKILL.md`: MotherDuck/DuckDB schema, repository, backup 계약 점검
- `.agent/skills/kis-release-ops/SKILL.md`: CI/CD, Secret Manager, GitHub Actions, Cloud Run 릴리즈 절차
- `.agent/skills/kis-project-os/SKILL.md`: 변경 분류, Work Item, traceability와 공통 gate 절차
- `.agent/skills/kis-data-governance/SKILL.md`: source, 수집 장바구니, dataset, metric, pipeline과 데이터 수명주기 계약 절차

### Data Governance Harness

source, 수집 장바구니, dataset, metric, pipeline, quality, lineage, retention을 변경할 때는
`docs/governance/data-governance-harness.md`와 `.agent/skills/kis-data-governance/SKILL.md`를 먼저 읽는다.
계약 형식은 `governance/contract-schema.toml`, 개별 계약 SSOT는 `governance/catalog/`이다. 승인·활성 계약
없이는 production 수집, publish, metric, MCP 노출을 구현하지 않는다.

DB 작업에서는 이어서 `docs/data-catalog.md`를 읽는다. 이 문서가 객체 목적, grain, logical layer,
민감도, 백업 정책과 schema migration 계획의 canonical governance 문서다. `schema.py` 또는 live DB에만
객체를 추가하지 말고 `src/kis_portfolio/db/catalog.py`, DDL/migration, repository test, catalog 문서를
같은 변경에서 갱신한다.

### Secret / token 관리 문서
시크릿과 토큰의 canonical policy는 `docs/security-and-secrets.md`에 둔다.
`SPEC.md`는 설계 결정, `ARCHITECTURE.md`는 trust boundary, `docs/deployment.md`는 배포 절차만 담당한다.

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
API 키와 계좌정보는 Claude client config에 주입하지 않는다. 운영 batch/worker가 Secret Manager와 배포
환경을 통해 `KIS_APP_KEY_{ACCOUNT}`, `KIS_APP_SECRET_{ACCOUNT}`, `KIS_CANO_{ACCOUNT}`,
`KIS_ACNT_PRDT_CD_{ACCOUNT}` 형태의 계좌별 suffixed env를 받는다.
오케스트레이터는 내부적으로 짧은 scoped env context를 사용해 인증/토큰/잔고 로직을 재사용하며,
전체 계좌 refresh는 순차 실행한다.

### 주문 tool stub
과거 V1 내부 adapter에는 disabled 주문 stub 구현이 보존되지만 public catalog에는 등록하지 않는다.
V2에는 주문 scope와 주문 tool이 없다. 주문 기능은 audit/confirmation 설계 전까지 구현하지 않는다.

### KIS REST resilience
OAuth token 발급을 제외한 KIS 업무 REST 호출은 `kis_portfolio.clients.kis.request_kis`를 통과한다.
`clients/kis_resilience.py`가 process-local rate interval, shared adaptive cooldown, bounded queue/in-flight
bulkhead, policy deadline, idempotent retry와 endpoint circuit breaker를 담당한다.

- live order POST는 자동 재시도하지 않는다.
- `quote`, `account`, `history`, `batch` 정책을 호출 성격에 맞게 선택한다.
- live balance의 stale fallback은 호출자가 명시적으로 허용한 경우에만 반환한다.
- stale/partial 응답은 source, as-of, age와 upstream 상태를 표시한다.
- 설정과 운영 계약은 `docs/kis-api-rate-limits.md`, `docs/kis-api-resilience.md`가 canonical이다.

### Remote MCP 인증과 운영 증상

`kis-portfolio-remote`의 production OAuth, token 검증과 상태 저장은
`docs/security-and-secrets.md`와 `docs/deployment.md`를 따른다. 상태 점검 경로는 `/health`다.
운영 환경에서 `KIS_REMOTE_AUTH_DISABLED=true`를 사용하지 않는다.
토큰·연결·수집 이상은 `docs/troubleshooting.md`에서 찾아 대응한다.

---

## 관련 레포지토리

| 레포 | 용도 |
|------|------|
| `~/workspace/KIS_Portfolio_MCP` | **이 서버** (메인) |
| `~/workspace/koreainvestment-mcp` | API 문서 검색용 MCP (kis-api-search) |
| `~/workspace/stock_manager_llm` | KIS Open API 레퍼런스 코드 (참조용) |

---

## 데이터와 실행 진입점

- production 분석 저장소는 MotherDuck이며, 명시적인 local 모드는 DuckDB를 사용한다.
  객체·계층·drift는 `docs/data-catalog.md`, 데이터 흐름은 `docs/data-pipeline.md`,
  백업과 로컬 복원은 `docs/backup.md`를 따른다.
- MCP는 `kis-portfolio-remote`, 배치는 `kis-portfolio-batch`를 사용한다. 공개 tool의 기능과 구현은
  `docs/api-capability-map.md`와 `docs/traceability.md`, 배치 구성과 일정은 `docs/deployment.md`와 운영 런북을 확인한다.
- 공개 응답에서 토큰과 secret을 제외하고, 계좌 메타데이터의 계좌번호를 마스킹한다.

## 신규 환경 온보딩

새 맥이나 새 클론에서 저장소 의존성과 OAuth Remote 연결을 복원하는 절차.

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
- canonical `KIS_RESOURCE_SERVER_URL` 검사
- `uv sync` (Python 의존성 설치)
- 기존 Claude Desktop config의 정확한 로컬 `kis-portfolio` 항목만 백업 후 제거
- OAuth Remote custom connector 등록값 안내

### 이후
Claude 설정 > 커넥터에서 `KIS Portfolio`와 canonical `/mcp` URL 등록 → 새 대화에서 OAuth 승인 및
`get-portfolio-overview` 확인.

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

WI-071: `get-data-quality(dataset_id="dataset.cash-balance-reconciliation")` reads typed diagnostic Control
revisions. Initial production writer/schema permit deferred/NULL monetary columns only. The zero-source-call
companion pipeline runs after successful portfolio refresh when `KIS_CASH_RECONCILIATION_ENABLED=true`.
Never replace unknown source basis/posting with flags inferred from valuation residuals or collection watermarks.
