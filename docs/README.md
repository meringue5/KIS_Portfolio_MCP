# KIS Portfolio 문서 홈

> 기준: 2026-11-02 V2 운영 인수 완료 — [MS-008 종료](milestones/MS-008-real-use-mcp-acceptance.md)
> 이 파일은 탐색의 입구입니다. 승인·계약·상태는 아래 소유 문서가 정본입니다.

## 지금 하려는 일부터 찾기

| 하려는 일 | 먼저 볼 문서 | 다음 단계 |
| --- | --- | --- |
| 기능을 이해하거나 수정하기 | [요구사항–기능 추적표](traceability.md) | 업무명 → 요구 → 구현 → 테스트 → 인수·제한 |
| 현재 할 일과 차기 후보 확인 | [운영 TODO](../TODO.md) | 현재 작업과 미검토 후보를 구분 |
| 오류·누락·알림 문제 해결 | [트러블슈팅](troubleshooting.md) | 증상 → 첫 확인 → 복구 경계 → 사건 원문 |
| 매일·매월·분기 운영 점검 | [운영 런북](operations/steady-state-operations-runbook.md) | 품질·전송·백업·비용·복원 점검 |
| 과거 결정·구축 경로 조사 | [구축 이력 안내](#구축-이력) | 당시 문서와 현재 정본을 구분 |

처음부터 모든 WI를 읽을 필요는 없습니다. 수정하려는 기능의 추적표 행에서 시작하고, 관련 테스트와
원문만 확인합니다. 링크는 일반 Markdown 형식이며 별도 앱·DB·생성기가 필요하지 않습니다.

## 정본 문서의 역할

| 확인할 내용 | 정본 |
| --- | --- |
| 승인된 제품 요구·DEC | [요구사항](requirements/kis-portfolio-data-platform-requirements.md), [요구 패키지](requirements/) |
| 장기 설계 결정·현재 코드 경계 | [SPEC](../SPEC.md), [ARCHITECTURE](../ARCHITECTURE.md) |
| 공개 기능·API 도입 판단 | [기능 경계](api-capability-map.md), [Remote 연결 안내](remote-mcp-v2-migration.md) |
| 데이터 grain·key·민감도·pipeline | [데이터 카탈로그](data-catalog.md), [파이프라인](data-pipeline.md), [계약 레지스트리](../governance/catalog/) |
| 시크릿·토큰·접근 경계 | [보안 정책](security-and-secrets.md) |
| 배포·rollback·backup | [배포](deployment.md), [백업·복원](backup.md), [비용·릴리즈 가드](operations/production-cost-release-guardrails.md) |
| 작업 상태·작업 관계·운영 변경 절차 | 개별 [WI](work-items/), [마일스톤 레지스트리](../governance/project/milestones.toml), [Project OS](governance/project-operating-system.md) |

추적표는 정본으로 가는 지도입니다. TODO는 승인 기록이나 상세 작업 상태의 복제본이 아닙니다.
원문과 충돌하면 조용히 요구를 바꾸지 말고, 해당 기능의 WI/Issue에 충돌과 근거를 기록합니다.

## 인수된 운영 기준선

- 사용자 연결은 OAuth Remote MCP `KIS Portfolio`의 안정 HTTPS `/mcp`입니다. 공개 도구는 18개이며 주문 도구는 없습니다.
- Firestore가 OAuth/KIS-token/lease/run-request 운영 상태를, MotherDuck가 분석 데이터·진단 이력을 소유합니다.
- 현재 관측·과거 이력·참고값·부분 결과를 구분합니다. 코드나 데이터가 존재한다는 이유로 완전성·성과 계산을 보장하지 않습니다.
- WI-071은 관측 현금의 금액·기준·시각·날짜별 변화·거래 참고 정보·원인 미확인 표시로 인수했습니다.
  완전한 결제 현금 대사·입출금 원장·RP/자금이동 원인 추정·성과 자격은 별도 미지원 범위입니다.
- WI-072 관심종목 알림과 ETF 구성종목 look-through는 현재 인수 범위 밖입니다. [차기 후보](../TODO.md#차기-버전-검토-후보)를 참조합니다.
- `kis-portfolio-mcp`와 루트 `server.py`는 폐기 연결 진단입니다. 운영 복구는 검증된 V2 이미지·설정으로 합니다.

## 구축 이력

| 찾을 내용 | 원문 / 안내 |
| --- | --- |
| V2 운영 인수와 마일스톤별 목적 | [마일스톤 안내](milestones/README.md), [MS-008 handoff](milestones/MS-008-real-use-mcp-acceptance.md) |
| 번호별 작업·검증·사용자 인수 | [Work Items](work-items/), [날짜별 운영 증거](operations/) |
| 설계 대안과 채택 시점 | [설계 문서](design/), [SPEC](../SPEC.md) |
| 재편 직전 전체 요구·구축 추적표 | [원문 스냅샷](history/traceability-before-operations-2026-11-02.md) |
| 재편 직전 TODO·의존 그래프 | [TODO 원문](history/todo-before-operations-2026-11-02.md), [의존 그래프 원문](history/milestone-map-before-operations-2026-11-02.md) |

스냅샷은 당시 본문·표·상태를 보존하고 상대 링크의 위치만 보정했습니다. 안에 있는 미완료 체크·당시 상태·명령·가격·경로는 **그 시점의 기록**이며
현재 실행 지침이 아닙니다. 기존 WI·설계·검증 원문은 제자리에서 유지합니다.
V1 문서 분류는 기존 [disposition](../governance/project/v1-document-disposition.toml)과 검사 절차를 따릅니다.
