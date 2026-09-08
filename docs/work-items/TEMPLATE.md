---
id: WI-NNN
title: Replace with a concise outcome
status: proposed
type: change
owner: owner
decision_refs: none
requirement_refs: none
milestone_ref: none
delivery_refs: none
parent_work_item: none
depends_on: none
discovered_from: none
supersedes: none
rollback_of: none
execution_scope: pending_gate
production_effects: unknown
architecture_impact: unknown
data_impact: unknown
security_impact: unknown
cost_impact: unknown
# stabilizing일 때 아래 세 필드를 실제 값으로 채운다.
stabilization_window: none
stabilization_exit_refs: none
rollback_plan: none
---

# WI-NNN — Replace with a concise outcome

## Problem and evidence

관찰한 사실, 재현 방법과 출처를 기록한다. secret, raw token, 전체 계좌번호는 넣지 않는다.

## Classification and contract

- 초기 분류:
- 비교한 요구사항/ADR/catalog:
- 계약 미달인지 계약 변경인지:
- 승인 필요 여부:

## Scope

- 포함:
- 제외:

## Acceptance criteria

- [ ] 사용자 관점 결과
- [ ] 자동 검증
- [ ] 필요한 운영·복원·비용 증거

## Change impact

- Architecture:
- Data/schema/backup:
- Security/privacy:
- MCP/API compatibility:
- Deployment/rollback:
- Cost/SLO:

## Plan

1. 첫 단계

## Sub-items

- `none`. 기존 outcome 안에서 발견된 작업은 `WI-NNN-SNN`으로 append한다. 독립 outcome이면 새 Work Item을
  발급하며 기존 index를 이동하지 않는다.

## Stabilization plan

- 관찰 기간/표본:
- 관찰할 신호·품질·전송·비용:
- rollback trigger와 마지막 안전 상태:
- 종료 증거와 owner acceptance:

운영 증거가 필요 없는 작업은 `not applicable`로 표시한다. 운영 중 발견된 결함은 기존 증거를 지우거나
상태를 되감지 않고 새 sub-item/Work Item을 append해 `discovered_from`, `rollback_of`, `supersedes`로 연결한다.

## Evidence

- 명령/테스트:
- 운영 증거:

## Closeout

- 결과:
- 남은 위험:
- 후속 Work Item:
