---
id: WI-056
title: Introduce stabilization lifecycle and controlled milestone overlap gates
status: closed
type: governance
owner: maintainer
decision_refs: ADR-022
requirement_refs: GOV-004, GOV-005, GOV-006, GOV-008..012
milestone_ref: MS-GOV
delivery_refs: none
parent_work_item: none
depends_on: WI-053
discovered_from: WI-030, WI-055
supersedes: none
rollback_of: none
architecture_impact: Project OS lifecycle and cross-milestone execution gates only
data_impact: no data contract, schema, migration or production row mutation
security_impact: no credential, permission or trust-boundary change
cost_impact: repository-local governance and tests only
---

# WI-056 — Introduce stabilization lifecycle and controlled milestone overlap gates

## Problem and evidence

MS-002는 구현·배포가 끝난 기능을 실제 사용하며 시간축 증거와 owner acceptance를 모으고 있지만 기존 상태
모델은 이를 `in_progress` 또는 `verified`로만 표현한다. 이 때문에 다음 milestone의 안전한 격리 구현과
production activation을 같은 gate로 묶으며, rollback 뒤 보정·재검증·재안정화되는 실제 운영 loop도
dependency DAG에 잘못 섞일 위험이 있다.

## Classification and contract

- 분류: `governance`.
- 사용자가 `stabilizing` 상태, 이중 milestone gate, WI-056 분리와 7단계 개정안을 승인했다.
- 구조적 `depends_on`은 계속 DAG로 유지하고, rollback/recovery는 append-only feedback 관계와 새 보정
  Work Item으로 표현한다.

## Scope

- 포함: Work Item/milestone `stabilizing`, 진입·종료 기준, implementation/production gate, checker와 테스트,
  템플릿·Skill·그래프, MS-002/MS-003 재기준선화와 dogfood.
- 포함: rollback 시 이력을 되감지 않는 feedback/recovery loop와 관계 검증.
- 제외: MS-003 제품 구현, DB migration, source activation, 배포, infrastructure와 외부 메시지.

## Acceptance criteria

- [x] `verified`, `stabilizing`, `closed`의 의미와 owner acceptance 경계가 명료하다.
- [x] 선행 milestone이 안정화 중이면 승인된 isolated work만 가능하고 production effect는 닫힐 때까지 차단된다.
- [x] dependency DAG와 rollback/recovery feedback loop가 분리되어 machine check된다.
- [x] 템플릿, Skill, milestone graph와 MS-002/MS-003 상태가 같은 계약을 따른다.
- [x] quick/full gate와 negative contract tests가 통과한다.

## Change impact

- Architecture: 제품 architecture는 불변; Project OS control architecture를 확장한다.
- Data/schema/backup: 없음.
- Security/privacy: 없음.
- MCP/API compatibility: 없음.
- Deployment/rollback: 배포하지 않는다. 정책 변경 자체는 이 커밋 revert로 복원 가능하다.
- Cost/SLO: 실행비용 없음; CI 검사 시간이 소폭 증가한다.

## Plan

1. lifecycle과 안정화 진입·종료 기준을 정책에 추가한다.
2. milestone implementation gate와 production gate를 분리한다.
3. checker가 조기 production effect와 잘못된 feedback 관계를 막게 한다.
4. 템플릿에 안정화 기간·관찰·rollback·exit evidence를 추가한다.
5. Skill과 Mermaid를 갱신한다.
6. MS-002를 stabilizing, MS-003을 ready로 재기준선화한다.
7. 이 Work Item과 현재 milestone에 dogfood하고 full gate를 실행한다.

## Sub-items

- `none`.

## Stabilization plan

- Not applicable. WI-056 is a repository-only governance change with no runtime, data, infrastructure or external
  effect, so it moves from verified evidence directly to closed.

## Evidence

- `uv run pytest -q tests/test_project_os_contract.py`: 18 passed.
- `bash scripts/check.sh quick`: passed with 57 tracked Work Items and one active implementation WIP.
- `bash scripts/check.sh full`: 475 passed; all Project OS, data governance, architecture, warehouse and MCP gates
  passed with one third-party Authlib deprecation warning.
- Negative evidence covers missing stabilization exit contract, premature implementation gate, non-allowlisted overlap,
  production effect during overlap, unknown feedback target and structural dependency cycle.
- Positive dogfood covers MS-002 `stabilizing`, MS-003 `ready`, WI-035/WI-040 isolated overlap and a feedback edge that
  closes an operational recovery loop without entering dependency topological sorting.
- 운영 증거: repository-local governance 변경이며 production mutation 없음.

## Closeout

- 결과: closed. 승인된 7단계 lifecycle/gate 개정과 recovery-loop 계약을 Project OS에 적용했다.
- 남은 위험: repository metadata를 거짓으로 분류한 외부 수동 작업까지 기술적으로 막지는 못한다. 실제
  production mutation은 기존 release/data/authorization gate와 함께 적용해야 한다.
- 후속 Work Item: 없음. 이후 발견되는 rollback은 해당 제품 Work Item 또는 독립 corrective Work Item으로
  append한다.
