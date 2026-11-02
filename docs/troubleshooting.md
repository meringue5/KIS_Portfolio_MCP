# 트러블슈팅 — 증상에서 찾기

> 기준: 2026-11-02 인수된 V2. [문서 홈](README.md) · [기능 추적표](traceability.md) · [현재 할 일](../TODO.md)
> 사건 원문은 당시 진단/실행의 이력입니다. 아래 절차와 현재 정본을 먼저 확인합니다.

사건을 매번 외우지 않고 [운영 모델](operating-model.md)의 근거·시간·값 구분으로 먼저 판정합니다.
아래 원문 링크는 특정 원인/복구 사례가 필요할 때만 읽습니다.

## 공통 첫 확인

1. 어떤 기능·client·관측 시각·계좌 alias/시장 범위의 문제인지 좁힙니다. 총자산 보고서, 신호 통합 현황,
   종목별 상세 알림, 차기 관심종목 알림을 구분합니다.
2. 기존 조회에서 `request_id`, `run_id`, logical date/slot, quality/freshness/missing coverage를 확인합니다.
   `get-pipeline-run`의 실패 이력과 현재 요청의 결과를 구분합니다.
3. 아래 행의 정본·관련 WI를 확인합니다. 문서만으로 현재 장애 원인을 확정하거나 과거 해결 명령을 재실행하지 않습니다.
4. run ID·시점·배포 identity·품질 코드를 보존하고 운영 결함으로 추적합니다. 원본/실패 이력은 지우지 않습니다.
   credential·계좌번호·금액·메시지 본문·private URI는 공개 문서나 로그에 옮기지 않습니다.

## 증상별 첫 확인과 해결 경계

| 증상 / 검색어 | 먼저 확인 | 해결·복구 경계 | 정본 / 사례(선택) |
| --- | --- | --- | --- |
| MCP 연결 실패·인증 만료·일지 쓰기 권한 없음 | OAuth Remote `KIS Portfolio` 연결인지, 읽기는 되는지, 쓰기 scope 동의와 오류 구분 | 동의 누락은 정본 온보딩 절차로 처리. 구 로컬 연결로 우회하거나 계좌 키를 client config에 넣지 않음 | [연결·scope](remote-mcp-v2-migration.md), [보안](security-and-secrets.md), [WI-073](work-items/WI-073-journal-oauth-recovery.md) |
| KIS 토큰 만료·EGW00123·유량 제한·EGW00215 | source 응답과 수집 run 실패 시점, 계좌별 credential/refresh 경로, backoff 상태 | 기존 token/resilience 경로를 사용. 반복 수동 발급·병렬 전체 계좌 조회로 회복을 시험하지 않음 | [REST 복원력](kis-api-resilience.md), [유량](kis-api-rate-limits.md), [토큰 정책](security-and-secrets.md) |
| 총자산 이미지가 안 오거나 현재 구성/전일 비교가 빠짐 | 정확한 날짜·10:00/16:00 슬롯의 core/quality/배송 outcome; 현재 완전성인지 전일 같은 슬롯 결손인지 구분 | [무전송 readiness 검사](operations/steady-state-operations-runbook.md#daily-triage)부터 확인. 전일 결손은 비교만 제한; 해외/FX 결손을 0으로 합치지 않음. 원인 확인 전 과거 전송 replay 안 함 | [WI-059](work-items/WI-059-scheduled-core-telegram-recovery.md), [WI-060](work-items/WI-060-resilient-partial-portfolio.md), [WI-075](work-items/WI-075-total-asset-overseas-coverage-recovery.md) |
| 보유종목 신호가 안 오거나 중복됨 | 총자산 보고서와 분리. 세 시각 현황/eligible transition 상세를 분리하고 rule 활성·만료·후보 quality·terminal delivery 확인 | 변화가 없다는 이유만으로 상세 메시지를 생성하지 않음. 현황 수신이 상세 수신 증거는 아님. 관심종목 기능은 현재 운영 대상 밖 | [WI-070](work-items/WI-070-permanent-held-position-telegram-signals.md), [WI-076](work-items/WI-076-three-slot-held-signal-status.md), [전송 계약](../governance/catalog/pipelines.toml) |
| 현금은 보이는데 대사는 deferred / 금액 변화의 원인을 모름 | 조회 dataset을 구분: 관측은 `dataset.cash-observation-history`, 대사 진단은 `dataset.cash-balance-reconciliation`; basis·시점·age·missing/zero 확인 | 현재 인수는 관측 금액·날짜별 변화·제한된 거래 문맥·원인 미확인까지. RP/입출금/결제 원인이나 수익률 자격을 차액에서 추정하지 않음 | [현금 동작·제한](operations/wi-071-observed-cash-history-2026-10-30.md), [WI-071](work-items/WI-071-owner-cash-flow-history-management.md) |
| 과거 총자산 급락·회복률이 이상하거나 NULL | 요청 기간이 불완전 legacy인지, canonical/opt-in reference인지, missing coverage인지 확인 | 결손 총액을 0으로 채우거나 참고값으로 수익률을 계산하지 않음. 허용된 참고 조회는 noncanonical/가정을 유지 | [WI-066](work-items/WI-066-legacy-total-asset-history-quality-recovery.md), [WI-068](work-items/WI-068-retained-legacy-history-recovery.md) |
| 거래 없음·누락·삼성/SOR 이력 차이 | 정확한 계좌·시장·기간의 producer/coverage/lineage/publish; 전체 구간 증명과 SOR venue 선택 확인 | 빈 행/최신 watermark만으로 거래 없음을 결론 내리지 않음. 보정·bounded recovery는 승인된 경로와 해당 WI에서 처리 | [WI-063](work-items/WI-063-incremental-trade-event-collection.md), [WI-074](work-items/WI-074-domestic-sor-recovery.md) |
| 같은 거래가 여러 번 보임 | source identity/alias와 실제 주문을 대조; 현재 projection·lot/thread 참조 확인 | `DISTINCT`나 Bronze 삭제로 숨기지 않음. 서로 다른 정상 주문을 합치지 말고 source-proven 보정 절차 사용 | [WI-064](work-items/WI-064-trade-event-business-key-deduplication.md), [identity 검사](../tests/test_trade_identity_projection.py) |
| pipeline partial인데 휴일임 / 슬롯은 있는데 quality failed | `window_status`와 개별 run status·quality 구분; calendar·예정 시각·실패 이력 확인 | closed-market quiet window와 누락 슬롯을 구분. 슬롯 관측이 run 성공을 뜻하지 않으며 과거 실패를 pass로 덮지 않음 | [WI-067](work-items/WI-067-calendar-aware-pipeline-run-status.md), [WI-065](work-items/WI-065-claude-asset-change-mcp-recovery.md) |
| fundamental·macro·ETF·전망에 no_governed_rows / unavailable | 요청 식별자·기간과 source/collection/dataset의 실제 승인·활성·coverage 확인 | tool/코드/approved 계약 존재와 현재 데이터 제공을 구분. source를 버그 수정 명목으로 활성화하지 않음; ETF look-through는 초기 V2 제외 | [기능 경계](api-capability-map.md), [데이터 카탈로그](data-catalog.md), [WI-052](work-items/WI-052-defer-etf-from-initial-v2.md) |
| 배포 후 연결·구조·품질이 다름 | exact SHA/digest·Remote 안정 경로/호환 경로·Job 설정·schema prefix·보호된 릴리즈 결과 확인 | 현재 [배포/rollback](deployment.md) 절차로 복구. 원문에 남은 V1 rollback은 현행 경로가 아님 | [WI-065](work-items/WI-065-claude-asset-change-mcp-recovery.md), [배포](deployment.md), [WI-071 전환](operations/wi-071-production-transition.md) |
| 백업·복원·객체 drift·비용 이상 | 최신 사용 가능 backup/manifest, 객체 계약과 exception, 실제/예상 비용 확인 | fresh local restore와 aggregate 검사부터. production 대상 복원·미등록 객체 채택/삭제·유료 source 확대는 별도 변경 절차 | [운영 런북](operations/steady-state-operations-runbook.md), [백업](backup.md), [카탈로그](data-catalog.md), [비용 가드](operations/production-cost-release-guardrails.md) |

## 아직 해결 기록이 없는 문제

기능 추적표에서 소유 코드를 찾고, 실제 요청·오류·영향 범위를 좁혀 원인을 확인합니다.
새 발견은 [운영 변경 절차](governance/project-operating-system.md)의 operations lane에 기록합니다.
닫힌 milestone을 되열거나 현재 인수 범위를 자동으로 넓히지 않습니다.

해결한 뒤에는 해당 WI/Issue에 재현·원인·수정·검증·rollback을 남기고, 이 표에는 다음에 같은 증상을
찾을 수 있는 짧은 설명과 원문 링크만 추가합니다. 일반 구현 설명과 긴 조사 로그는 복제하지 않습니다.
