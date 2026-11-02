# 마일스톤과 구축 이력 안내

> 기준: 2026-11-02 V2 운영 인수 완료. 모든 delivery milestone은 closed입니다.
> [문서 홈](../README.md) · [기능 수정 지도](../traceability.md) · [운영 TODO](../../TODO.md)

평소 기능 수정에는 기능 추적표를 사용합니다. 이 문서는 구축 당시의 목적·순서·인수 근거를 찾는 입구입니다.
Work Item 상태·증거는 개별 [WI](../work-items/), identity/depends_on/sequence/sub-item은
[registry](../../governance/project/milestones.toml)가 정본입니다. 번호는 작업 우선순위가 아닙니다.

## 인수된 기준선

| 마일스톤 | 결과 / 원문 | 현재 상태 |
| --- | --- | --- |
| MS-001 | canonical 자산·거래·managed collection 기반; [registry](../../governance/project/milestones.toml), [시스템 설계](../design/kis-portfolio-v2-system-design.md) | closed |
| MS-002 | [분석·위험·신호·Telegram](MS-002-portfolio-analytics-alerting.md) | closed |
| MS-003 | [enrichment·Remote V2·운영 전환](MS-003-enrichment-remote-cutover.md) | closed |
| MS-004 | [V2 정본·이전 연결 퇴역](MS-004-v2-canonicalization-retirement.md) | closed |
| MS-GOV | Project OS; [정책](../governance/project-operating-system.md), [registry](../../governance/project/milestones.toml) | closed |
| MS-005 | [운영 피드백·사용성 보정](MS-005-production-feedback-corrections.md) | closed |
| MS-006 | [정기 수집·Telegram 복구](MS-006-scheduled-core-telegram-recovery.md) | closed |
| MS-007 | [부분 기능·source 실패 격리](MS-007-resilient-partial-portfolio.md) | closed |
| MS-008 | [실제 MCP 인수·기능 보정·V2 운영 인수](MS-008-real-use-mcp-acceptance.md) | closed |

WI-071은 관측 현금 이력이라는 제한된 범위로 인수했습니다. 완전 결제 대사·성과 자격은 미지원이며,
WI-072 관심종목 알림은 차기 검토 대상입니다. 상세 경계는 [MS-008 handoff](MS-008-real-use-mcp-acceptance.md#closeout-and-v2-operational-handoff--2026-11-02)와
[기능 추적표](../traceability.md)가 연결합니다. 이 표는 현재 운영 성공이나 모든 source 활성화를 보증하지 않습니다.

## 과거 관계와 설계 찾기

- [재편 직전 의존 그래프 전체 원문](../history/milestone-map-before-operations-2026-11-02.md): 당시 진행 상태·설명을 보존하고 상대 링크만 보정했습니다.
- [구축 당시 요구–구현–검증 추적표](../history/traceability-before-operations-2026-11-02.md).
- [시스템 설계](../design/kis-portfolio-v2-system-design.md), [delivery plan](../design/kis-portfolio-v2-delivery-plan.md), [SPEC](../../SPEC.md).
- 개별 milestone/WI의 revision/closeout은 당시 결정과 인수 기록입니다. 과거 `stabilizing`, `verified`, 미완료 표시를 현재 할 일로 해석하지 않습니다.

기존 의존 그래프를 새 상태로 매번 재작성하지 않습니다. 관계 확인은 registry와 해당 작업의 실제 producer·consumer·인수 조건을
함께 봅니다. `discovered_from`은 발견 경위이고, hard dependency나 완료 조건과 같지 않습니다.

## 운영 이후 변경

닫힌 milestone은 승인된 결과의 보존 기록입니다. 동일 outcome의 보정은 Project OS operations lane에 append하고,
새 기능은 owner 검토 뒤 별도 범위로 접수합니다. WI 번호·identity·과거 증거를 재사용/재번호화하지 않습니다.

2026-11-02 [WI-077](../work-items/WI-077-operational-documentation-navigation.md)은 WI-032의 문서 탐색을 정비하는
repository-only 운영 maintenance입니다. 새 기능이나 새 milestone을 만들거나 closed 상태를 되돌리지 않습니다.
