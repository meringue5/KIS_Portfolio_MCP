---
id: WI-000
title: Bootstrap the KIS Portfolio Project Operating System
status: verified
type: governance
owner: owner
decision_refs: ADR-022
requirement_refs: GOV-001..GOV-008
architecture_impact: yes
data_impact: none
security_impact: none
cost_impact: none
---

# WI-000 — Bootstrap the KIS Portfolio Project Operating System

## Problem and evidence

제품·데이터·배포 아키텍처와 검증 Skill은 존재하지만 feedback intake, 변경 분류, Work Item lifecycle,
traceability, 공통 로컬/CI 하네스가 하나의 운영 계약으로 연결돼 있지 않다. `TODO.md`에는 이미 운영 중인
항목도 미완료로 남아 있어 작업 상태 SSOT로 사용하기 어렵다.

## Classification and contract

- 초기 분류: `governance`
- 사용자 결정: 정식 명칭을 Project Operating System으로 선택하고 Package F를 제품 V2 구현보다 먼저
  설계·구현해 현재 세션부터 사용한다.
- 관련 결정: ADR-022, V2 delivery trace 계약
- 승인 필요 여부: 이름·도입은 승인됨. 제품 architecture 또는 infrastructure 변경은 이 작업 범위 밖이다.

## Scope

- 포함: Project OS canonical 문서, traceability, Work Item·Issue·PR template, Project OS Skill, 공통
  `check.sh`, tracked Git hooks, CI 연결과 현재 작업 dogfood
- 제외: GitHub Issue 실제 생성, production 배포, DB 변경, Firestore 활성화, V2 제품 코드 구현

## Acceptance criteria

- [x] Project OS와 Project Governance 용어 관계가 canonical 문서와 ADR에 고정된다.
- [x] feedback을 defect/clarification/change/architecture/incident/maintenance/governance로 분류할 수 있다.
- [x] 요구·결정·작업·구현·증거의 SSOT와 lifecycle이 명시된다.
- [x] Skill, local hooks와 CI가 같은 `scripts/check.sh`를 사용한다.
- [x] 동시에 하나의 `in_progress` Work Item만 허용하는 checker가 통과한다.
- [x] 기존 architecture/warehouse/MCP contract와 전체 pytest가 통과한다.
- [x] 이 Work Item 자체가 traceability와 evidence 형식을 사용한다.

## Change impact

- Architecture: 제품 상위 Engineering Control System과 mandatory repository workflow 추가
- Data/schema/backup: 없음
- Security/privacy: Issue/Work Item에 secret·raw token·전체 계좌번호 기록 금지 규칙 추가
- MCP/API compatibility: 없음
- Deployment/rollback: CI entrypoint 변경만 포함; production deployment 없음
- Cost/SLO: 외부 서비스·상시 실행 추가 없음

## Plan

1. Project OS 정책과 ADR을 기록한다.
2. Work Item/traceability/Issue/PR template을 추가한다.
3. Project OS Skill과 결정적 checker를 만든다.
4. 공통 check harness와 local hook·CI를 연결한다.
5. staged/quick/full mode를 실행해 dogfood하고 결과를 기록한다.

## Evidence

- `python3 .agent/skills/kis-project-os/scripts/check_project_os.py`: 통과,
  `tracked_work_items=1 active_work_items=1` 상태에서 bootstrap 확인
- Skill validator: `Skill is valid!`
- GitHub Issue Form 5개 YAML parse: 통과
- `uv run pytest tests/test_project_os_contract.py`: 2 passed; 현재 repository 양성 계약과 중복
  `in_progress` 음성 계약 확인
- `bash scripts/check.sh quick`: Project OS, architecture, warehouse, MCP surface, shell/JSON 통과
- `bash scripts/check.sh full`: 190 passed, architecture/warehouse/MCP/Project OS contract 통과
- `git config --local --get core.hooksPath`: `.githooks`
- 첫 기준선 commit 뒤 clean-checkout full gate가 실패함: 음성 테스트가 WI-000의 `verified` 상태까지 복사해
  두 개의 `in_progress` fixture를 만들지 못한 test coupling을 발견함. WI-000을 재개해 fixture를 독립화함.
- fixture가 source Work Item의 실제 상태와 무관하게 두 active item을 만들도록 수정한 뒤 targeted 2 tests와
  full gate 190 tests가 다시 통과함.
- 운영 증거: production 변경 없음

## Closeout

- 결과: Project OS 정책·Skill·Work Item·traceability·Issue/PR template·single check harness·tracked hook·CI를
  연결하고 현재 세션에서 Skill을 로드해 WI-000에 dogfood했다. post-commit 결함도 같은 feedback loop로
  재개·수정·재검증했다.
- 남은 위험: 실제 GitHub Issue 기반 workflow와 release 작업에서 추가 dogfood 필요
- 후속 Work Item: V2 Architecture delta review
