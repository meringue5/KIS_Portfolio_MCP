# KIS Portfolio Traceability

이 문서는 요구·결정·작업·구현·검증·인수 사이의 연결을 관리한다. 상세 정책은
`docs/governance/project-operating-system.md`가 소유하며, 이 표는 그 정책을 복제하지 않는다.

## Active and Recent Work

| Requirement / feedback | Decision | Work Item | Implementation artifacts | Verification / evidence | Status |
| --- | --- | --- | --- | --- | --- |
| GOV-001..GOV-008: Project OS 도입 | ADR-022 | WI-000 | governance docs, templates, Skill, `scripts/check.sh`, hooks, CI | full gate 190 passed, Skill/YAML validation, duplicate-WIP negative test | verified |
| DEC-001..DEC-041: KIS Portfolio data platform | ADR-021 proposed | V2-W0001..V2-W0806 | `docs/design/kis-portfolio-v2-*.md` | Wave별 acceptance/rollback gate | design_review |

## Governance Requirements

| ID | Requirement | Acceptance owner |
| --- | --- | --- |
| GOV-001 | 정식 명칭은 Project Operating System, 약칭 Project OS로 고정한다. | owner |
| GOV-002 | Project Governance는 Project OS의 결정·권한·변경통제 하위 영역이다. | owner |
| GOV-003 | 티켓은 추적 레코드이고 승인된 요구·ADR·catalog가 결정 SSOT다. | owner |
| GOV-004 | 모든 비사소한 변경은 분류·계약비교·영향·인수·증거를 가진다. | owner / maintainer |
| GOV-005 | Skill, hook과 CI는 동일한 결정적 검사 entrypoint를 사용한다. | maintainer / CI |
| GOV-006 | 동시에 하나의 구현 Work Item만 `in_progress`로 둔다. | maintainer |
| GOV-007 | 계약 변경은 사용자 승인 뒤 반영하고, 구현에 맞춘 silent widening을 금지한다. | owner |
| GOV-008 | Project OS 자체 변경도 Work Item과 dogfood 검증을 거친다. | owner / maintainer |

## Update Rules

- Work Item을 시작·검증·종료할 때 해당 row의 artifact, evidence와 상태를 같은 변경에서 갱신한다.
- 상세 로그나 긴 테스트 출력은 Work Item/CI artifact에 두고 이 표에는 링크나 명령 이름만 둔다.
- closed row는 삭제하지 않는다. 오래된 항목은 별도 archive table/file로 이동할 수 있다.
- 요구나 결정이 superseded되면 새 ID와 대체 관계를 기록하고 과거 연결을 덮어쓰지 않는다.
