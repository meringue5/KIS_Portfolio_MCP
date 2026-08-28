# MS-004 — V2 canonicalization and V1 retirement

> 상태: proposed; project delivery의 final milestone
> 선행 milestone: MS-003
> machine registry: `governance/project/milestones.toml`

## Outcome

V2 cutover 뒤 V1 runtime·data consumer·문서 잔존물을 검증 가능한 방식으로 퇴역시키고, 보존할 역사와 현재
운영 정본을 구분하여 V2 문서·계약·runbook 하나를 프로젝트의 canonical baseline으로 만든다.

## Baseline

| Sequence | Work Item | Design refs | Depends on | 상태 / 결과 |
| ---: | --- | --- | --- | --- |
| 1 | WI-032 V2 canonical documentation and V1 retirement | V2-W0807 | MS-003 completion gate | proposed |

V2-W0801~0806의 runtime/data/resource retirement와 audit 작업은 MS-003 종료 시점에 실제 잔존물과 rollback
단위를 조사한 뒤 새 Work Item으로 발급한다. WI-032는 문서 정본화 outcome만 소유하며 live resource 삭제를
자동으로 포함하지 않는다.

## Acceptance gate

- V2-W0801~0806의 retirement/audit evidence와 MS-003 cutover evidence가 닫혀 있다.
- architecture, requirements/decisions, MCP, data, security, deployment, recovery, cost와 onboarding의 현재
  문서가 V2 정본 하나를 가리킨다.
- V1 문서는 역사 보존, superseded redirect 또는 승인된 삭제 대상으로 전수 분류된다.
- 새 clone, Remote MCP/iPhone 연결과 운영 runbook을 문서대로 재현한다.
- destructive resource/data deletion은 별도 승인과 복구 증거 없이는 수행하지 않는다.

## Revision log

| Version | Date | Change | Identity impact |
| --- | --- | --- | --- |
| 2026-08-28.1 | 2026-08-28 | final MS-004와 WI-032 문서 정본화 작업을 최초 기준선화 | 기존 WI 변경 없음; WI-032 신규 발급 |
