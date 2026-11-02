# 인수된 V2 범위와 운영 변경 원칙

> 기준: owner가 인수한 V2의 의미. 당시 실행 순서·revision log는 [압축 원문](../history/README.md)에만 보존합니다.
> [운영 모델](../operating-model.md) · [현재 할 일/후보](../../TODO.md)

## 무엇을 인수했는가

| 범위 | 유지할 의미 |
| --- | --- |
| 관측·저장·조회 | OAuth Remote 하나, managed collection, 근거/시점/품질을 가진 자산·가격·거래·계좌 범위 |
| 부분 결과 | 전체 합계의 엄격한 완전성을 유지하면서 독립적인 현재 구성/국내 현황/진단은 제공 |
| 분석·보정 | 원장·lot/thread·PIT metric·검토 queue와 source-proven revision; 입력 부족 시 explicit 제한 |
| 운영 확인 | run/stage/quality/lineage·backup/restore·rollback·비용 점검과 실제 승인 client 인수 |
| 알림 | 보유종목 통합 현황·eligible 상세, 별도의 총자산 보고서; 각각 독립 배송/수신 증거 |
| 현금 | 마지막 관측 금액·basis/시각·날짜별 변화·제한된 거래 문맥·unknown 원인 |
| 과거 참고 | 가정·분류가 표시된 total-level opt-in, canonical/성과와 분리 |

완전 결제 현금 대사·외부 입출금 원장·RP/자금이동 원인 추정·성과 자격을 현금 관측으로 인수한 것은 아닙니다.
관심종목 알림은 차기 검토, ETF 구성종목 look-through는 초기 범위 밖, 주문은 비목표입니다.
코드/계약이 있어도 특정 source·계좌·기간의 가용성은 별도 확인합니다. 이는 미완료 구축 목록이 아니라 인수된 한계입니다.

## 완료 기준과 이후의 처리

구축은 실행한 자동 검증, 필요한 운영/복구 증거, 실제 client의 정상·부분·오류 처리와 owner 인수로 닫습니다.
기능의 한계를 숨기지 않은 인수는 향후 모든 데이터를 제공한다는 약속이 아닙니다. 새 발견을 과거 pass로
덮거나 milestone을 되열지 않습니다. 운영 결함은 기존 outcome의 corrective work, 새 기능은 별도 검토입니다.

| 보존된 기준선 identity | 인수한 결과 |
| --- | --- |
| MS-001 | canonical 자산/거래와 managed collection 기반 |
| MS-002 | 분석·risk·signal·Telegram 경로 |
| MS-003 | enrichment 계약·stateless Remote·운영 전환 |
| MS-004 | V2 정본·이전 연결/자원 퇴역·문서 정본 |
| MS-GOV | Project OS와 변경·권한·검증 체계 |
| MS-005 | 실제 운영 피드백의 사용성/품질 교정 |
| MS-006 | 정기 자산 수집·보고·영구 보유 신호 복구 |
| MS-007 | source 실패 격리와 정확한 부분 기능 |
| MS-008 | 실제 MCP 인수·발견 사항 교정·V2 운영 handoff |

이 delivery 기준선들은 closed입니다. identity·depends_on·sequence·하위 항목은
[registry](../../governance/project/milestones.toml), 개별 작업 상태·인수 증거는 [WI](../work-items/)가 정본입니다.
운영 maintenance가 추가돼도 delivery 인수를 취소하지 않습니다.

## 운영에서 유지할 책임

기존 service owner는 [런북](../operations/steady-state-operations-runbook.md)의 run/quality·배송·백업·비용·복원을
유지하고, [배포/rollback](../deployment.md)과 [보안](../security-and-secrets.md)을 따릅니다.
이 문서가 새 monitor·schedule·source·비용·전송을 승인하지 않습니다.

정확한 당시 판단이 필요할 때만 [MS-008 owner handoff](../history/README.md#인수와-구축-경과) 또는 개별 WI로 내려갑니다.
