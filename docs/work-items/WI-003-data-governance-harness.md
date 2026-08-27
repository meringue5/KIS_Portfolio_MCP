---
id: WI-003
title: Define and enforce the Data Governance Harness
status: verified
type: governance
owner: owner
decision_refs: ADR-018, ADR-021, ADR-022, ADR-023
requirement_refs: DGOV-001..DGOV-010
architecture_impact: data control plane and engineering gates
data_impact: contract format only; no production schema or data mutation
security_impact: defines sensitivity and authorization gates; no credential change
cost_impact: repository-local checks only; no new paid service
---

# WI-003 — Define and enforce the Data Governance Harness

## Problem and evidence

Project OS와 Warehouse Contract는 변경 추적, object allowlist, DDL/catalog 일치, backup 포함 여부와 live
drift를 일부 통제한다. 그러나 source, collection basket, dataset, metric과 pipeline의 소유권·수명주기·
freshness·quality·lineage·retention 계약을 공통 형식으로 강제하는 하네스는 없다. `my_db`가 운영 DB처럼
보였던 사례는 물리 객체 존재와 관리 대상 선언이 분리될 때 발생하는 혼선을 보여줬다.

사용자는 2026-08-28에 Data Governance Harness를 정식 설계 산출물로 정의하고, 이후 원천 데이터
카탈로그와 수집 장바구니가 그 계약 형식을 반드시 따르도록 진행할 것을 승인했다.

## Classification and contract

- 초기 분류: `governance`
- 비교한 요구사항/ADR/catalog: ADR-018, ADR-021, ADR-022, DEC-036~DEC-040,
  `docs/data-catalog.md`, V2 Wave 3~4
- 계약 미달인지 계약 변경인지: 승인된 data governance 목표를 Project OS가 실행할 수 있는 전문 하네스로
  구체화하는 계약 변경
- 승인 필요 여부: 상위 방향과 필수 적용은 사용자 승인됨. production schema, source onboarding,
  collection schedule과 backfill은 별도 승인 대상

## Scope

- 포함: canonical Data Governance Harness 정책, ADR, DGOV traceability, source/dataset/collection/metric/
  pipeline manifest schema, 빈 canonical registries, repository-local Skill, deterministic checker, hook·CI
  공통 entrypoint 연결, negative contract test
- 제외: 실제 source 선정, 수집 장바구니 내용, provider 가입, production DDL/migration, pipeline 실행,
  MotherDuck 권한 변경, backfill, 배포

## Acceptance criteria

- [x] Project OS와 Data Governance Harness의 포함 관계, 문서 권한과 예외 절차가 canonical 문서에 고정된다.
- [x] source, dataset, collection basket, metric과 pipeline의 최소 계약 형식과 수명주기가 기계 판독 가능하다.
- [x] 미등록 참조, 중복 ID, 잘못된 상태·형식과 승인 근거 없는 active 계약을 checker가 거부한다.
- [x] `scripts/check.sh`의 staged/quick/full 모두 같은 data governance checker를 호출한다.
- [x] 관련 agent가 새 전용 Skill과 canonical 정책을 먼저 읽도록 AGENTS 계약이 갱신된다.
- [x] 기존 data catalog와 V2 delivery plan이 새 하네스를 선행 계약으로 참조한다.
- [x] 전체 Project OS·architecture·warehouse·MCP·pytest gate가 통과한다.
- [x] production 데이터·인프라·비용에는 변경이 없다.

## Change impact

- Architecture: Project OS 아래에 data-specific control system을 추가하며 product data architecture를
  대체하지 않는다.
- Data/schema/backup: manifest와 검사만 추가한다. live MotherDuck와 DDL은 변경하지 않는다.
- Security/privacy: source license, sensitivity, secret profile과 destructive change approval을 계약 필드로
  만든다.
- MCP/API compatibility: 없음. 미래 catalog/quality MCP의 입력 계약만 선행 정의한다.
- Deployment/rollback: repository 문서·checker를 revert하면 된다. runtime 배포 없음.
- Cost/SLO: 로컬·CI Python 검사 비용만 추가된다. 외부 SaaS나 상시 process 없음.

## Plan

1. ADR-023과 canonical Data Governance Harness 정책을 작성한다.
2. 기계 판독 contract schema와 빈 source/dataset/collection/metric/pipeline registry를 만든다.
3. 전용 Skill, deterministic checker와 negative test를 작성한다.
4. Project OS, data catalog, delivery plan, AGENTS, traceability와 공통 gate를 연결한다.
5. quick/full 검증 후 실제 증거와 남은 위험을 기록한다.

## Evidence

- `python3 .agent/skills/kis-data-governance/scripts/check_data_governance.py`: 통과,
  `registered_contracts=0` — Phase 1 source inventory 전의 의도된 빈 registry
- `uv run --with pyyaml python .../skill-creator/scripts/quick_validate.py
  .agent/skills/kis-data-governance`: `Skill is valid!`
- `uv run pytest tests/test_data_governance_contract.py tests/test_project_os_contract.py`: 5 passed; 승인된
  source→dataset→collection 양성 계약과 미승인·미등록 참조 음성 계약 포함
- `bash scripts/check.sh quick`: Project OS, DGH, architecture, warehouse, MCP surface 통과
- `bash scripts/check.sh full`: 193 passed, 1 기존 Authlib deprecation warning; 모든 contract gate 통과
- 운영 증거: production DB, service, Job, Scheduler와 secret 변경 없음

## Closeout

- 결과: ADR-023, DGOV-001..DGOV-010, canonical DGH 정책, TOML contract schema와 5개 registry,
  전용 Skill/checker/test를 공통 Project OS gate에 연결했다. 상태는 검증 완료, 사용자 인수 대기다.
- 남은 위험: 기존 V1 object/batch는 Phase 1 역등록 전까지 grandfather된다. runtime quality/publish gate와
  live `--fail-on-drift`는 V2 pipeline/migration Work Item에서 구현해야 한다.
- 후속 Work Item: WI-004 후보 — source inventory와 collection basket review package
