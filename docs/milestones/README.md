# Milestone and Work Item control

Milestone은 승인된 요구와 설계 delivery item을 실행 가능한 Work Item으로 묶는 기준선이다. 식별자와 관계의
machine-readable SSOT는 `governance/project/milestones.toml`, 상태·작업·증거의 SSOT는 개별
`docs/work-items/WI-*.md`, 전체 연결은 `docs/traceability.md`가 담당한다.

## 불변 규칙

- Work Item ID는 발급 뒤 삭제·재사용·재번호화하지 않는다.
- 번호는 정렬이나 우선순위가 아니다. 실행순서는 `sequence`와 `depends_on`으로 관리한다.
- 기존 outcome 안의 발견 작업은 `WI-NNN-SNN` sub-item으로 append한다.
- 독립 acceptance 또는 rollback이 필요하면 현재 최댓값 다음의 새 WI를 발급한다.
- 순서·의존관계 변경은 해당 milestone 문서의 revision log에 남긴다.
- 완료된 WI는 새 범위를 흡수하기 위해 다시 정의하지 않는다.

## 변경 단위

마일스톤을 변경할 때 registry, 해당 milestone 문서, Work Item, traceability와 Project OS 검사를 같은
change set에서 갱신한다. 아직 마일스톤에 편입하지 않은 장기 설계 항목은 V2 delivery ID로만 유지하고
Work Item 번호를 미리 점유하지 않는다.
