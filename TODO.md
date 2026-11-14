# 운영 TODO

> 기준: 2026-11-03 V2 운영 인수 이후. [문서 홈](docs/README.md) · [기능 추적표](docs/traceability.md) · [트러블슈팅](docs/troubleshooting.md)
> 상세 작업 상태는 개별 WI/Issue가 정본입니다. 이 목록은 현재 업무의 요약이며, 아이디어는 승인된 할 일이 아닙니다.

## 현재 진행

현재 이 목록에 등록된 진행 작업은 없습니다. 운영 지식의 의미 중심 압축은
[WI-077](docs/work-items/WI-077-operational-documentation-navigation.md)의 S02로 종료했습니다.

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
| 관심종목 관찰·알림 (기존 WI-072 초안) | 차기 제품 범위 후보. 실제 그룹 조회 실패와 MTS 동등성 미확인으로 보류; 격리 구현은 운영·V2 인수 범위 밖 | [V2 인수 경계](docs/milestones/v2-acceptance.md), 아래 WI-072 보존 메모 |
| ETF 구성종목 수집·look-through | 초기 V2 제외. source 권리·비용·coverage와 새 승인 필요; WI-026/027 번호 재사용 안 함 | [WI-052](docs/work-items/WI-052-defer-etf-from-initial-v2.md), [요구 DEC-049](docs/requirements/kis-portfolio-data-platform-requirements.md) |
| 완전한 결제 현금 대사·외부 입출금/자금이동 원인·성과 자격 | WI-071 인수 범위 밖. 현재 관측 이력의 결손·미확인 원인을 조용히 승격하지 않음; 구현 일정/활성 승인 없음 | [WI-071](docs/work-items/WI-071-owner-cash-flow-history-management.md), [현금 관측 제한](docs/operations/wi-071-observed-cash-history-2026-10-30.md) |

후보는 중요도·승인·착수 순서를 뜻하지 않습니다. 새 요구가 확정되면 [Project OS](docs/governance/project-operating-system.md)
절차로 상세 WI/Issue를 만들고, 그때 이 문서의 현재 진행에 올립니다.

### WI-072 보존 메모 — 2026-11-14

- 로컬 `codex/wi072-watchlist-isolation` 브랜치의 `cf81cc0`에 KIS 그룹 조회 adapter, 격리 관찰 core,
  proposed 데이터 계약, 테스트와 마스킹된 조사 증거를 보존했습니다. 이 브랜치는 미병합·미배포이며
  현행 `master`의 Work Item registry나 운영 계약에 WI-072를 소급 등록하지 않습니다.
- 당시 실제 그룹 목록 요청은 HTTP 200이었으나 `rt_cd=1`이고 `output2`가 없었습니다. 빈 관심종목 목록이나
  MTS와의 동등성이 증명된 결과로 취급하지 않습니다. 재검토 시 원천 접근·선택 그룹 membership을 확인하거나
  출처를 명시한 수동 동기화 대안을 owner가 별도로 인수해야 합니다.
- 착수 결정 전 [Project OS §6.4](docs/governance/project-operating-system.md#64-stabilization-exit-and-steady-state-operations)에 따라
  닫힌 MS-008 기준선을 보존하면서 새 제품 범위의 요구·인수 경계와 milestone 배치를 검토합니다. 원천 및
  membership SSOT, 신호·중복 전송 조정의 DEC/ADR, Data Governance 계약, 비용과 실제 client/transport 검증을
  승인한 뒤 필요한 산출물만 분리 브랜치에서 가져옵니다. 이 후보 기록은 구현·source 활성·알림 전송 승인이 아닙니다.

## 이전 TODO의 개별 미검토 후보

Owner 검토에 따라 각 아이디어를 아래에 따로 표시합니다. **모두 미검토 후보이며 현재 진행 작업이 아닙니다.**
이미 구현된 부분·중복·폐기된 전제가 있을 수 있으므로 필요성과 잔여 범위를 대조한 뒤에만 WI/Issue로 접수합니다.
행의 순서는 원문을 찾기 위한 것이며 우선순위나 구현 승인이 아닙니다.

| 후보 | 먼저 검토할 내용 | 원문 / 현재 대조 기준 |
| --- | --- | --- |
| 종목 분류 override 운영 루틴·입력 UX | 기존 override 경로로 충분한지, owner 입력 방식에 실제 공백이 있는지 | [옛 실사용 메모](https://github.com/meringue5/KIS_Portfolio_MCP/blob/a8fdfa599ba1e4876ded726d23d577a4640eff9d/docs/history/todo-before-operations-2026-11-02.md#high-priority), [카탈로그](docs/data-catalog.md) |
| 종목마스터 동기화 주기·실패 fallback | 현재 source/collection 계약과 실행 주기·실패 정책의 잔여 요구 | [옛 실사용 메모](https://github.com/meringue5/KIS_Portfolio_MCP/blob/a8fdfa599ba1e4876ded726d23d577a4640eff9d/docs/history/todo-before-operations-2026-11-02.md#high-priority), [수집 계약](governance/catalog/collections.toml) |
| 종목마스터 재시도·중단 후 재개 | 기존 upsert/수집 복원력으로 충족되는 범위와 추가 필요성 | [옛 실사용 메모](https://github.com/meringue5/KIS_Portfolio_MCP/blob/a8fdfa599ba1e4876ded726d23d577a4640eff9d/docs/history/todo-before-operations-2026-11-02.md#high-priority), [REST 복원력](docs/kis-api-resilience.md) |
| KIS 토큰 발급 감사 메타데이터 | 발급 사유·시점 등의 감사 필요성과 현재 Firestore 보안 경계; 원문/암호문 중복 저장 금지 | [옛 토큰 감사 제안](https://github.com/meringue5/KIS_Portfolio_MCP/blob/a8fdfa599ba1e4876ded726d23d577a4640eff9d/docs/history/todo-before-operations-2026-11-02.md#high-priority), [현재 보안 정책](docs/security-and-secrets.md) |
| 과거 branch·live DB 통합 메모의 잔여 범위 | `portfolio-pipeline-reliability`/legacy 객체 메모를 현행 V2 관리 객체·보존 drift와 대조; 옛 통합 명령 재실행 아님 | [옛 통합 메모](https://github.com/meringue5/KIS_Portfolio_MCP/blob/a8fdfa599ba1e4876ded726d23d577a4640eff9d/docs/history/todo-before-operations-2026-11-02.md#data-governance), [현재 카탈로그](docs/data-catalog.md) |
| 명시적 조회 전용 운영 모드 | 현재 읽기/쓰기 OAuth scope 분리 외에 별도 모드가 필요한지 | [옛 Remote 메모](https://github.com/meringue5/KIS_Portfolio_MCP/blob/a8fdfa599ba1e4876ded726d23d577a4640eff9d/docs/history/todo-before-operations-2026-11-02.md#remote-mcp), [현재 연결·권한](docs/remote-mcp-v2-migration.md) |
| 포트폴리오 합산의 서비스 경계 재검토 | 현재 aggregate/service 구조로 기존 제안이 이미 충족됐는지 | [옛 리팩터 제안](https://github.com/meringue5/KIS_Portfolio_MCP/blob/a8fdfa599ba1e4876ded726d23d577a4640eff9d/docs/history/todo-before-operations-2026-11-02.md#refactor), [현재 구조](ARCHITECTURE.md) |
| KIS client/service 패키지 설계 재검토 | 기존 capability map과 실제 모듈 배치 사이의 개선 필요성; 이미 수행된 분리는 중복 착수하지 않음 | [옛 패키지 제안](https://github.com/meringue5/KIS_Portfolio_MCP/blob/a8fdfa599ba1e4876ded726d23d577a4640eff9d/docs/history/todo-before-operations-2026-11-02.md#refactor), [기능 경계](docs/api-capability-map.md) |
| KIS client의 국내·해외·연금·환율별 모듈 분리 | 현재 공통 요청·정책 경계를 보존하면서 분리할 실익이 있는지 | [옛 모듈 분리 제안](https://github.com/meringue5/KIS_Portfolio_MCP/blob/a8fdfa599ba1e4876ded726d23d577a4640eff9d/docs/history/todo-before-operations-2026-11-02.md#refactor), [현재 구조](ARCHITECTURE.md) |
| token refresh와 감사 로깅의 책임 분리 | 기존 인증/상태 저장 경계로 충족되는지, 감사 메타데이터 후보와 겹치는지 | [옛 경계 제안](https://github.com/meringue5/KIS_Portfolio_MCP/blob/a8fdfa599ba1e4876ded726d23d577a4640eff9d/docs/history/todo-before-operations-2026-11-02.md#refactor), [보안 정책](docs/security-and-secrets.md) |
| ETF PDF·외부 자료 기반 해외노출 enrichment | 상단 ETF 구성종목/look-through 후보와 함께 범위·권리·비용·미지원 경계를 대조 | [옛 enrichment 제안](https://github.com/meringue5/KIS_Portfolio_MCP/blob/a8fdfa599ba1e4876ded726d23d577a4640eff9d/docs/history/todo-before-operations-2026-11-02.md#refactor), [초기 V2 제외 결정](docs/work-items/WI-052-defer-etf-from-initial-v2.md) |
| Cloudflare Access/WAF 등 추가 접근 계층 | 옛 배포 가설의 필요성이 현재 OAuth Remote 구조에도 남는지; 새 인프라/비용/접근 변경 승인 없음 | [옛 배포 가설](https://github.com/meringue5/KIS_Portfolio_MCP/blob/a8fdfa599ba1e4876ded726d23d577a4640eff9d/docs/history/todo-before-operations-2026-11-02.md#remote-mcp), [현재 배포](docs/deployment.md) |

## 기존 기준선으로 대체된 구축 메모

아래 항목은 옛 TODO에 미완료 체크가 있어도 신규 후보나 현재 할 일로 자동 승격하지 않습니다.
검토 목적이 생기면 원문과 현재 정본을 대조합니다.

| 옛 항목 | 현재 찾을 곳 / 취급 |
| --- | --- |
| WI-060 및 WI-061/062/063 미완료 표시 | [마일스톤 종료·운영 인수](docs/milestones/v2-acceptance.md); 해당 WI의 완료 이력 유지 |
| `main` 단일 schema 전환·runtime auto-DDL 분리 | [V2 물리 구조·관리 migration 경계](ARCHITECTURE.md); legacy 보존 객체/drift는 [카탈로그](docs/data-catalog.md)로 별도 확인 |
| bearer 인증의 OAuth 승격 | [현재 OAuth 연결·scope](docs/remote-mcp-v2-migration.md); 신규 인증 전환 할 일 아님 |
| Docker build·배포 타깃 선정·GCP 가입/Secret 준비 | [현재 Cloud Run 릴리즈](docs/deployment.md); 옛 공급자 비교·가격·가입 체크를 재실행하지 않음. 추가 Cloudflare 계층은 위 별도 미검토 후보 |
| `app.py`의 core/MCP adapter 분리 | [현재 코드 경계](ARCHITECTURE.md); 과거 파일명 기준 공정을 되열지 않음 |

## 완료된 구축과 이전 메모

V2 구축은 [V2 운영 인수](docs/milestones/v2-acceptance.md)로 종료했습니다.
WI-060/061/062/063 등 이미 닫힌 항목을 미완료 업무로 반복하지 않습니다.
재편 직전 TODO 123줄은 [본문·상태를 보존해](https://github.com/meringue5/KIS_Portfolio_MCP/blob/a8fdfa599ba1e4876ded726d23d577a4640eff9d/docs/history/todo-before-operations-2026-11-02.md) 보존합니다.
그 안의 미완료 체크·과거 API명·가격·경로·구축 가설은 현재 승인이나 실행 지시가 아닙니다.

옛 제안의 원문 링크는 고정 commit을 가리킵니다. [동일 원문을 담은 로컬 압축본](docs/history/README.md)도 보존합니다.
