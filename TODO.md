# 운영 TODO

> 기준: 2026-11-02 V2 운영 인수 이후. [문서 홈](docs/README.md) · [기능 추적표](docs/traceability.md) · [트러블슈팅](docs/troubleshooting.md)
> 상세 작업 상태는 개별 WI/Issue가 정본입니다. 이 목록은 현재 업무의 요약이며, 아이디어는 승인된 할 일이 아닙니다.

## 현재 진행

현재 이 목록에 등록된 진행 작업은 없습니다. 최근 문서 정리는
[WI-077](docs/work-items/WI-077-operational-documentation-navigation.md)로 종료했습니다.

새로 확인·등록된 운영 장애는 이 목록에 없습니다. 운영 정상 여부의 실시간 판정은
[run/quality 점검](docs/operations/steady-state-operations-runbook.md)이 담당합니다.

## 반복 운영 업무

일정·권한·완료 기준은 [기존 런북](docs/operations/steady-state-operations-runbook.md)이 정본입니다.
이 표는 새 자동화나 매번 닫아야 할 구축 WI를 만들지 않습니다.

| 때 | 확인할 것 | 지침 |
| --- | --- | --- |
| 실행·일별 | 실패/누락 슬롯, freshness/quality, 전송 결과, 최신 사용 가능 백업 | [일상 점검](docs/operations/steady-state-operations-runbook.md#daily-triage) |
| 월별 | 사용량·실제/예상 비용·runtime drift·source/권리 예외 | [비용·용량](docs/operations/steady-state-operations-runbook.md#monthly-capacity-and-cost-review) |
| 분기 | 새 private backup 복원·권한·source/API/보존 조건 | [복원](docs/operations/steady-state-operations-runbook.md#quarterly-restore-rehearsal), [보안](docs/security-and-secrets.md) |
| 릴리즈 | 변경 영향·테스트·backups/restore·정확한 이미지·rollback·실제 client | [배포](docs/deployment.md), [Project OS](docs/governance/project-operating-system.md) |

## 차기 버전 검토 후보

| 후보 | 현재 판정 | 검토 원문 |
| --- | --- | --- |
| WI-072 관심종목 관찰·알림 | owner가 운영 전환 후로 유보. 기존 별도 세션의 격리 산출물/원천 blocker 보존; 완료·운영 활성으로 취급하지 않음 | [V2 인수 경계](docs/milestones/MS-008-real-use-mcp-acceptance.md#closeout-and-v2-operational-handoff--2026-11-02) |
| ETF 구성종목 수집·look-through | 초기 V2 제외. source 권리·비용·coverage와 새 승인 필요; WI-026/027 번호 재사용 안 함 | [WI-052](docs/work-items/WI-052-defer-etf-from-initial-v2.md), [요구 DEC-049](docs/requirements/kis-portfolio-data-platform-requirements.md) |
| 완전한 결제 현금 대사·외부 입출금/자금이동 원인·성과 자격 | WI-071 인수 범위 밖. 현재 관측 이력의 결손·미확인 원인을 조용히 승격하지 않음; 구현 일정/활성 승인 없음 | [WI-071](docs/work-items/WI-071-owner-cash-flow-history-management.md), [현금 관측 제한](docs/operations/wi-071-observed-cash-history-2026-10-30.md) |
| 이전 TODO의 나머지 제안 | 미검토 후보 — 현재 할 일 아님. 이미 구현됐거나 폐기된 전제를 포함할 수 있어 실제 계약/코드를 대조한 뒤에만 접수 | [원문 스냅샷](docs/history/todo-before-operations-2026-11-02.md) |

후보는 중요도·승인·착수 순서를 뜻하지 않습니다. 새 요구가 확정되면 [Project OS](docs/governance/project-operating-system.md)
절차로 상세 WI/Issue를 만들고, 그때 이 문서의 현재 진행에 올립니다.

## 완료된 구축과 이전 메모

V2 구축은 [MS-008/V2 운영 인수](docs/milestones/MS-008-real-use-mcp-acceptance.md)로 종료했습니다.
WI-060/061/062/063 등 이미 닫힌 항목을 미완료 업무로 반복하지 않습니다.
재편 직전 TODO 123줄은 [본문·상태를 보존해](docs/history/todo-before-operations-2026-11-02.md) 보존합니다.
그 안의 미완료 체크·과거 API명·가격·경로·구축 가설은 현재 승인이나 실행 지시가 아닙니다.
