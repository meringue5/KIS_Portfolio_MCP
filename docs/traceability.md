# 요구사항–기능 추적표

> 기준: 인수된 V2; 의미 통합 검토 2026-11-03. 새 요구나 가용성 보증이 아닙니다.
> 먼저 [운영 모델](operating-model.md)과 [현행 설계 규칙](design/README.md)을 읽고, 아래는 필요한 기능 행만 찾습니다.
> [문서 홈](README.md) · [현재 할 일](../TODO.md) · [트러블슈팅](troubleshooting.md)

## 읽는 방법

업무명으로 행을 찾은 뒤 요구 → 구현 → 테스트 → 인수 기록 순서로 확인합니다. 기능 상태는 **인수 범위**를
뜻하며, 현재 데이터의 신선도·완전성·실행 성공은 `get-data-quality`와 `get-pipeline-run`으로 별도 확인합니다.
테스트 파일 연결은 테스트 실행 성공이나 실제 사용자 인수를 대신하지 않습니다.

공통 진입점: [공개 MCP 등록](../src/kis_portfolio/adapters/mcp/v2.py),
[조회 요청·응답 계약](../src/kis_portfolio/services/remote_read_surface.py),
[저장 데이터 조회 어댑터](../src/kis_portfolio/adapters/outbound/remote_v2_warehouse.py).
DEC 번호는 [승인 요구사항](requirements/kis-portfolio-data-platform-requirements.md)의 해당 항목을 찾는 키입니다.
DEC-063 표기는 보유 신호와 현금 전환에 각각 사용된 원문이 있으므로, 아래에 문서 제목/해당 WI도 함께 적습니다.
이번 정리는 번호나 승인 내용을 변경하지 않습니다.

## 기능별 수정 지도

| 기능 / 제공 범위 | 요구·계약 | 사용자 경로 | 구현 출발점 | 관련 테스트 | 한계 / 사례(필요시) |
| --- | --- | --- | --- | --- | --- |
| 총자산·계좌 구성·평가액 변화 — 운영; 부분 기능 독립 제공 | DEC-048/055/057; [요구](requirements/kis-portfolio-data-platform-requirements.md) | `get-portfolio-overview` | [조회 어댑터](../src/kis_portfolio/adapters/outbound/remote_v2_warehouse.py), [평가 변화](../src/kis_portfolio/modules/monitoring/valuation_change.py) | [Remote 조회](../tests/test_remote_v2_warehouse.py), [평가 변화](../tests/test_v2_valuation_change.py) | [WI-060](work-items/WI-060-resilient-partial-portfolio.md); 불완전 합계를 총자산으로 표시하지 않음 |
| 포지션·매수 lot·투자 thread — 운영; 근거 있는 재구성 | DEC-009/010/014/017; [거래 요구](requirements/review-package-a-transaction-ledger.md) | `get-position-analysis`, `get-trade-thread` | [재구성](../src/kis_portfolio/services/position_reconstruction_runtime.py), [조회 어댑터](../src/kis_portfolio/adapters/outbound/remote_v2_warehouse.py) | [재구성](../tests/test_position_reconstruction_runtime.py), [Remote](../tests/test_remote_v2_warehouse.py) | [WI-022](work-items/WI-022-position-lot-sell-reconstruction.md), [WI-025](work-items/WI-025-lot-thread-risk-metrics.md) |
| 성과·자산 이력·과거 참고값 — 조건부; 결손과 noncanonical 구분 | DEC-023/030/062; [요구](requirements/kis-portfolio-data-platform-requirements.md) | `get-performance-history` | [성과](../src/kis_portfolio/modules/monitoring/portfolio_performance.py), [참고 이력](../src/kis_portfolio/services/legacy_total_reference.py) | [성과](../tests/test_v2_portfolio_performance.py), [legacy](../tests/test_legacy_total_reference.py) | [WI-066](work-items/WI-066-legacy-total-asset-history-quality-recovery.md), [WI-068](work-items/WI-068-retained-legacy-history-recovery.md); 총액 관측은 현금흐름 조정 수익률이 아님 |
| 시세·가격·환율 이력 — 저장 근거/가격 basis 조건부 | DEC-015/016; [시세 요구](requirements/review-package-b-price-trend-etf.md) | `get-market-snapshot`, `get-market-history` | [가격 이력](../src/kis_portfolio/services/price_history.py), [조회 어댑터](../src/kis_portfolio/adapters/outbound/remote_v2_warehouse.py) | [가격 pipeline](../tests/test_price_history_pipeline.py), [Remote](../tests/test_remote_v2_warehouse.py) | [WI-015](work-items/WI-015-v2-price-history.md), [WI-058](work-items/WI-058-remote-mcp-identifier-and-coverage-correction.md); raw/adjusted·기간·품질 확인 |
| 거래 원장·증분 수집·중복/SOR 복구 — 운영; 정확한 구간 증명 필요 | DEC-009/012/060; [거래 요구](requirements/review-package-a-transaction-ledger.md) | `get-trade-ledger`; 독립 거래 배치 | [구간 증명](../src/kis_portfolio/services/trade_coverage.py), [수집](../src/kis_portfolio/services/trade_incremental.py) | [구간](../tests/test_trade_coverage_intervals.py), [중복 identity](../tests/test_trade_identity_projection.py), [수집](../tests/test_trade_incremental.py) | [WI-063](work-items/WI-063-incremental-trade-event-collection.md), [WI-064](work-items/WI-064-trade-event-business-key-deduplication.md), [WI-074](work-items/WI-074-domestic-sor-recovery.md) |
| 현금 관측·날짜별 증감 — 인수 완료; 원인은 미확인으로 유지 | DEC-063 현금 전환/addendum; [동작·제한](operations/wi-071-observed-cash-history-2026-10-30.md) | `get-data-quality`: `dataset.cash-observation-history`; 대사 진단은 별도 `dataset.cash-balance-reconciliation` | [현금 관측](../src/kis_portfolio/adapters/outbound/cash_observation_history.py), [대사 진단](../src/kis_portfolio/services/cash_reconciliation_runtime.py) | [관측](../tests/test_cash_observation_history.py), [진단](../tests/test_cash_reconciliation_production.py) | [WI-071](work-items/WI-071-owner-cash-flow-history-management.md); 관측/결제 시각·missing/zero 구분, 완전 대사·입출금/RP 추론·성과 사용 미지원 |
| 배당 요약 — entitlement/receipt/coverage별 조건부 | DEC-020~025; [배당 요구](requirements/review-package-c-fundamentals-dividend-macro.md) | `get-dividend-summary` | [배당 원장](../src/kis_portfolio/services/dividend_ledger.py), [배당 어댑터](../src/kis_portfolio/adapters/outbound/dividend_warehouse.py) | [배당 원장](../tests/test_v2_dividend_ledger.py), [Remote](../tests/test_remote_v2_warehouse.py) | [WI-038](work-items/WI-038-dividend-event-ledger.md); 선언·권리·수령/추정·결손 구분 |
| 실적·전망·매크로 — 공개 경로 존재; 승인 source/데이터별 가용성 조건부 | DEC-020~025/043; [전망 요구](requirements/review-package-c-fundamentals-dividend-macro.md) | `get-fundamental-outlook`; 매크로는 관련 노출 projection | [조회 어댑터](../src/kis_portfolio/adapters/outbound/remote_v2_warehouse.py), [source 계약](../governance/catalog/sources.toml) | [Remote](../tests/test_remote_v2_warehouse.py), [조회 계약](../tests/test_remote_v2_read_surface.py) | [WI-037](work-items/WI-037-filing-actual-fundamental-pipeline.md), [WI-039](work-items/WI-039-macro-profile-pipeline.md), [WI-041](work-items/WI-041-consensus-forward-outlook.md); 코드/approved 계약 존재는 source 활성·관측 성공 증거가 아님 |
| 경제적 노출·직접 분류 — 조건부; ETF 구성종목 look-through 제외 | DEC-018/048/049; [노출 경계](api-capability-map.md) | `get-exposure-analysis` | [노출 분류](../src/kis_portfolio/modules/exposure/instruments.py), [조회 어댑터](../src/kis_portfolio/adapters/outbound/remote_v2_warehouse.py) | [Remote](../tests/test_remote_v2_warehouse.py) | [WI-017](work-items/WI-017-held-instrument-etf-routing.md), [WI-052](work-items/WI-052-defer-etf-from-initial-v2.md); 미지원 look-through를 0으로 채우지 않음 |
| 보유종목 신호·세 시각 현황·상세 알림 — 운영; 관심종목은 차기 후보 | DEC-006/051/052/053/061 및 DEC-063 보유 신호; [감시 요구](requirements/review-package-d-monitoring-conversation.md) | `get-signal-status`; Telegram 10:00/14:30/16:00 현황, eligible transition 상세 | [신호 현황](../src/kis_portfolio/services/signal_slot_report.py), [전송](../src/kis_portfolio/services/telegram_delivery.py) | [신호 replay](../tests/test_v2_signal_replay.py), [전송](../tests/test_telegram_delivery.py) | [WI-070](work-items/WI-070-permanent-held-position-telegram-signals.md), [WI-076](work-items/WI-076-three-slot-held-signal-status.md); 통합 현황과 상세 수신 증거는 별개 |
| 총자산 이미지 보고서 — 운영; 현재 구성과 전일 비교를 구분 | DEC-054/055/057; [요구](requirements/kis-portfolio-data-platform-requirements.md) | Telegram 10:00/16:00 | [리포트](../src/kis_portfolio/services/total_asset_digest.py) | [리포트](../tests/test_total_asset_digest.py) | [WI-059](work-items/WI-059-scheduled-core-telegram-recovery.md), [WI-060](work-items/WI-060-resilient-partial-portfolio.md), [WI-075](work-items/WI-075-total-asset-overseas-coverage-recovery.md); 비교 불가와 현재 총액 불가를 구분 |
| 데이터 카탈로그·품질·실행 이력 — 운영 진단; 실패 이력 보존 | DEC-031/032/038/059; [운영 요구](requirements/review-package-e-data-platform-operations.md) | `get-data-catalog`, `get-data-quality`, `get-pipeline-run` | [조회 어댑터](../src/kis_portfolio/adapters/outbound/remote_v2_warehouse.py), [read-model 계약](../governance/catalog/read-models.toml) | [pipeline](../tests/test_remote_v2_pipeline.py), [Remote](../tests/test_remote_v2_warehouse.py) | [WI-040](work-items/WI-040-catalog-quality-read-model.md), [WI-065](work-items/WI-065-claude-asset-change-mcp-recovery.md), [WI-067](work-items/WI-067-calendar-aware-pipeline-run-status.md); 슬롯 관측과 run 성공은 별개 |
| 수집 요청·일지·thread 보정 — 운영; 고정 명령·권한 필요 | DEC-004/031/032; [대화 요구](requirements/review-package-d-monitoring-conversation.md) | `run-managed-pipeline`, `upsert-trade-journal`, `revise-trade-thread`, `get-journal-review-queue` | [명령](../src/kis_portfolio/services/remote_commands.py), [MCP](../src/kis_portfolio/adapters/mcp/v2.py) | [명령](../tests/test_remote_v2_commands.py), [보정](../tests/test_remote_v2_revisions.py) | [WI-043](work-items/WI-043-remote-mcp-managed-commands.md), [WI-073](work-items/WI-073-journal-oauth-recovery.md); 수집·일지 쓰기는 조회와 다른 scope |

운영 공통 경로: [OAuth/연결](remote-mcp-v2-migration.md), [보안](security-and-secrets.md),
[배포·rollback](deployment.md), [백업](backup.md), [운영 런북](operations/steady-state-operations-runbook.md).
관련 구현은 [Remote](../src/kis_portfolio/remote.py), [배치](../src/kis_portfolio/adapters/batch/cli.py),
검증은 [OAuth](../tests/test_auth_oauth.py), [릴리즈](../tests/test_deploy_cloud_run.py),
[운영 점검](../tests/test_steady_state_operations.py)에서 시작합니다.

## Active and Recent Work

| 현재 작업 | 소유 기록 | 승인 범위 | 상태 |
| --- | --- | --- | --- |
| 운영 문서 탐색 정리 | [WI-077](work-items/WI-077-operational-documentation-navigation.md) | 문서 홈·추적표·TODO·증상 안내; 원문 보존, 도구 추가 없음 | closed; repository-only maintenance, 2026-11-02 |

현재 할 일은 [TODO](../TODO.md), 상세 상태는 개별 WI/Issue가 소유합니다. 완료된 구축 작업을 이 표에
계속 쌓지 않습니다. 최근 완료된 문서 정리만 위에 연결하며, 신규 작업은 해당 WI/Issue에 연결합니다.

## Planned Milestone Work

V2 구축은 [V2 인수 의미](milestones/v2-acceptance.md)까지 인수·종료했습니다.
현재 단계와 후속 후보는 [인수·운영 변경 원칙](milestones/v2-acceptance.md)와 [TODO](../TODO.md)에서 찾습니다.
과거 delivery mapping은 [압축된 구축 추적표](history/README.md)에 보존합니다.

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
| GOV-009 | 구현 검증 뒤 시간축 운영 증거가 필요한 작업과 milestone은 `stabilizing`으로 관리한다. | owner / maintainer |
| GOV-010 | 선행 milestone 안정화 중 후속 milestone은 `in_progress`로 열고 reviewed Work Item을 dependency 순서와 단일 WIP 아래 isolated 검증까지 연속 진행하며, production effect는 선행 `closed`까지 막는다. | maintainer / CI |
| GOV-011 | 구조적 dependency는 DAG로 유지하며 rollback/recovery는 append-only feedback 관계와 새 corrective work로 기록한다. | owner / maintainer |
| GOV-012 | `closed`는 stabilization exit evidence와 필요한 owner acceptance가 충족된 뒤에만 허용한다. | owner |
| GOV-013 | 신규 사용자 노출 Work Item은 실제 승인 client/transport의 즉시 재현 가능한 positive·partial·error 사용 증거와 발견사항 소유권 없이는 `closed`가 될 수 없다. | owner / maintainer |

## Data Governance Requirements

| ID | Requirement | Acceptance owner |
| --- | --- | --- |
| DGOV-001 | Data Governance Harness는 Project OS 아래에서 data architecture를 집행하는 전문 control system이다. | owner |
| DGOV-002 | 정책은 canonical 문서, 계약 형식은 machine schema, 인스턴스는 registry, 검사는 단일 checker가 소유한다. | owner / maintainer |
| DGOV-003 | source, dataset, collection basket, metric과 pipeline은 구현 전에 versioned contract를 가진다. | data owner |
| DGOV-004 | 승인·활성 계약만 production 수집·publish·분석의 근거가 될 수 있다. | owner / pipeline runner |
| DGOV-005 | grain, key, time semantics, freshness, quality, lineage, sensitivity, retention과 cost 책임을 누락할 수 없다. | data owner |
| DGOV-006 | 미등록 객체·참조, schema drift와 승인 없는 breaking change는 hook·CI·release gate에서 실패한다. | maintainer / CI |
| DGOV-007 | runtime은 run, stage, watermark, quality result와 lineage evidence를 남기고 품질 미달을 성공으로 숨기지 않는다. | pipeline owner |
| DGOV-008 | Gold, metric, signal과 Telegram은 선언된 quality publish gate를 통과한 입력만 공식 결과로 사용한다. | analytics owner |
| DGOV-009 | 예외는 사유·범위·만료·승인자를 가진 Work Item으로만 허용하며 silent bypass를 금지한다. | owner |
| DGOV-010 | 원천 데이터 카탈로그와 수집 장바구니는 이 하네스의 source·collection·dataset 계약 형식을 따른다. | owner / data architect |

## Update Rules

기능 수정 시 해당 행의 요구·구현·테스트·인수·제한 링크를 함께 검토합니다. 새 결정과 상태의 정본을
이 표에 복제하지 않습니다. 상세 작업이 끝나면 TODO를 정리하고 기능 행의 관련 이력 링크를 갱신합니다.
기존 WI/design/evidence는 보존하며 당시 상태를 현재로 해석하지 않습니다. 공개 문서에는 새 운영 원문,
금액·계좌 식별자·credential·private URI를 복사하지 않습니다.

## 구축 기록과 인수

- [재편 직전 전체 추적표](https://github.com/meringue5/KIS_Portfolio_MCP/blob/a8fdfa599ba1e4876ded726d23d577a4640eff9d/docs/history/traceability-before-operations-2026-11-02.md): 모든 기존 행·결정·증거 원문 보존.
- [V2 인수 의미](milestones/v2-acceptance.md): WI-071의 제한된 인수 범위와 WI-072 차기 유보.
- [WI-077 문서 정리](work-items/WI-077-operational-documentation-navigation.md): 탐색 점검과 원문 보존 검증.

## 번호별 기록 찾기

기존 Project OS 검사는 이 문서에서 모든 발급 WI를 찾을 수 있어야 합니다. 아래는 상태 복제 없이 원문만
연결하는 보조 목차입니다. 평소에는 위 기능 표에서 시작하고, 특정 번호를 조사할 때만 이 목차를 사용합니다.

- [WI-000 — Bootstrap the KIS Portfolio Project Operating System](work-items/WI-000-project-operating-system.md)
- [WI-001 — Review and approve the KIS Portfolio V2 architecture delta](work-items/WI-001-v2-architecture-delta-review.md)
- [WI-002 — Establish the current operating cost baseline](work-items/WI-002-cost-baseline.md)
- [WI-003 — Define and enforce the Data Governance Harness](work-items/WI-003-data-governance-harness.md)
- [WI-004 — Select the governed source inventory and collection basket](work-items/WI-004-source-inventory-collection-basket.md)
- [WI-005 — Build the locally verifiable V2 foundation through Wave 4](work-items/WI-005-v2-local-foundation-wave-1-4.md)
- [WI-006 — Define the executable V1 to V2 mapping contract](work-items/WI-006-v1-v2-mapping-contract.md)
- [WI-007 — Rehearse V1 to V2 migration and produce reconciliation evidence](work-items/WI-007-v1-v2-reconciliation-dry-run.md)
- [WI-008 — Backfill only reconciled V1 history into live V2 tables](work-items/WI-008-bounded-v2-historical-backfill.md)
- [WI-009 — Build and reconcile the canonical account position cash and daily asset ledger](work-items/WI-009-canonical-portfolio-ledger.md)
- [WI-010 — Build the canonical trade purchase-lot and trade-thread ledger](work-items/WI-010-canonical-trade-lot-thread-ledger.md)
- [WI-011 — Move operational state behind Firestore ports and remove runtime DDL](work-items/WI-011-firestore-operational-state-cutover.md)
- [WI-012 — Run the first production V2 managed collection pipeline](work-items/WI-012-v2-managed-collection-pipeline.md)
- [WI-013 — Establish the V2 point-in-time metric foundation](work-items/WI-013-v2-metric-foundation.md)
- [WI-014 — Re-sequence Milestone 2 from production data readiness](work-items/WI-014-milestone-2-data-readiness.md)
- [WI-015 — Build the V2 dual-basis revision-aware price ledger](work-items/WI-015-v2-price-history.md)
- [WI-016 — Correct broker history semantics and append reversible trade corrections](work-items/WI-016-broker-history-correction.md)
- [WI-017 — Classify held instruments and establish rights-gated ETF routing](work-items/WI-017-held-instrument-etf-routing.md)
- [WI-018 — Establish immutable milestone and Work Item control](work-items/WI-018-milestone-work-item-control.md)
- [WI-019 — Implement replay-safe trend and volatility metrics](work-items/WI-019-trend-volatility-metrics.md)
- [WI-020 — Establish canonical cash events and classification revisions](work-items/WI-020-canonical-cash-events.md)
- [WI-021 — Collect bounded three-year trade and cash history](work-items/WI-021-three-year-trade-cash-history.md)
- [WI-022 — Reconstruct positions lots and sell allocations](work-items/WI-022-position-lot-sell-reconstruction.md)
- [WI-023 — Implement portfolio return contribution and drawdown](work-items/WI-023-portfolio-return-contribution-drawdown.md)
- [WI-024 — Add typed thread risk plans and review state](work-items/WI-024-thread-risk-plan-review-state.md)
- [WI-025 — Implement lot and thread path and risk metrics](work-items/WI-025-lot-thread-risk-metrics.md)
- [WI-026 — Activate rights-approved ETF constituent collection](work-items/WI-026-etf-constituent-forward-collection.md)
- [WI-027 — Implement nested ETF look-through and impact](work-items/WI-027-nested-etf-look-through.md)
- [WI-028 — Implement alert state and delivery ledger](work-items/WI-028-alert-state-delivery-ledger.md)
- [WI-029 — Calibrate signals with replay and shadow evaluation](work-items/WI-029-signal-replay-shadow-calibration.md)
- [WI-030 — Enable approved outbound Telegram delivery](work-items/WI-030-outbound-telegram-delivery.md)
- [WI-031 — Baseline Milestones 3 and 4 and register newly approved work](work-items/WI-031-milestone-three-four-baseline-intake.md)
- [WI-032 — Consolidate V1 documentation and establish V2 as the canonical baseline](work-items/WI-032-v2-canonical-documentation-and-v1-retirement.md)
- [WI-033 — Implement instrument-level total-asset valuation-change contribution](work-items/WI-033-total-asset-valuation-change-contribution.md)
- [WI-034 — Identify and baseline all remaining V2 delivery work](work-items/WI-034-remaining-delivery-work-identification.md)
- [WI-035 — Complete production inventory cost and release cleanup guardrails](work-items/WI-035-production-operations-cost-release-guardrails.md)
- [WI-036 — Establish corporate-action identity and adjustment lineage](work-items/WI-036-corporate-action-ledger.md)
- [WI-037 — Build filing actual and fundamental fact pipeline](work-items/WI-037-filing-actual-fundamental-pipeline.md)
- [WI-038 — Build declared entitled and received dividend ledger](work-items/WI-038-dividend-event-ledger.md)
- [WI-039 — Build the governed macro profile pipeline](work-items/WI-039-macro-profile-pipeline.md)
- [WI-040 — Publish the DB-only catalog and quality read model](work-items/WI-040-catalog-quality-read-model.md)
- [WI-041 — Implement point-in-time consensus and forward outlook analysis](work-items/WI-041-consensus-forward-outlook.md)
- [WI-042 — Implement the stateless Remote MCP V2 read surface](work-items/WI-042-remote-mcp-v2-read-surface.md)
- [WI-043 — Add governed collection and journal commands to Remote MCP V2](work-items/WI-043-remote-mcp-managed-commands.md)
- [WI-044 — Verify Remote MCP V2 clients and publish the migration guide](work-items/WI-044-remote-mcp-client-compatibility.md)
- [WI-045 — Complete V1 V2 dual-run recovery and cost readiness](work-items/WI-045-v1-v2-dual-run-readiness.md)
- [WI-046 — Cut production connectors and schedules over to Remote MCP V2](work-items/WI-046-remote-mcp-v2-production-cutover.md)
- [WI-047 — Retire local setup and the V1 public MCP surface](work-items/WI-047-v1-public-surface-retirement.md)
- [WI-048 — Transition remaining V1 main consumers to archive or compatibility views](work-items/WI-048-v1-main-consumer-transition.md)
- [WI-049 — Approve and execute bounded V1 runtime resource cleanup](work-items/WI-049-v1-runtime-resource-cleanup.md)
- [WI-050 — Finalize steady-state recovery cost and source review runbooks](work-items/WI-050-steady-state-operations-runbooks.md)
- [WI-051 — Remove obsolete shims and complete the final V2 architecture audit](work-items/WI-051-final-v2-architecture-audit.md)
- [WI-052 — Defer ETF constituent collection and look-through from initial V2 acceptance](work-items/WI-052-defer-etf-from-initial-v2.md)
- [WI-053 — Publish the human-readable Work Item dependency map](work-items/WI-053-work-item-dependency-visualization.md)
- [WI-054 — Audit and correct MS-002 production readiness before user acceptance](work-items/WI-054-ms002-production-readiness-correction.md)
- [WI-055 — Deliver a scheduled privacy-safe total-asset Telegram digest](work-items/WI-055-scheduled-total-asset-digest.md)
- [WI-056 — Introduce stabilization lifecycle and controlled milestone overlap gates](work-items/WI-056-stabilization-lifecycle-overlap-gates.md)
- [WI-057 — Make milestone overlap continuous and phase-aware](work-items/WI-057-continuous-milestone-overlap.md)
- [WI-058 — Correct Remote MCP identifiers and empty-coverage semantics after real Claude use](work-items/WI-058-remote-mcp-identifier-and-coverage-correction.md)
- [WI-059 — Restore 10:00 quality and scheduled Telegram delivery after the V2 core deployment](work-items/WI-059-scheduled-core-telegram-recovery.md)
- [WI-060 — Isolate portfolio capability failures and provide accurate partial results](work-items/WI-060-resilient-partial-portfolio.md)
- [WI-061 — Require real-use acceptance for user-visible completion](work-items/WI-061-real-use-acceptance-gate.md)
- [WI-062 — Remediate capability gaps found by direct Remote MCP use](work-items/WI-062-remote-mcp-real-use-remediation.md)
- [WI-063 — Restore governed incremental trade-event collection and coverage evidence](work-items/WI-063-incremental-trade-event-collection.md)
- [WI-064 — Eliminate duplicate current trade events without erasing source history](work-items/WI-064-trade-event-business-key-deduplication.md)
- [WI-065 — Restore the Claude recent-asset-change MCP workflow on the current Remote revision](work-items/WI-065-claude-asset-change-mcp-recovery.md)
- [WI-066 — Quarantine incomplete legacy total-asset history and restore truthful longitudinal analysis](work-items/WI-066-legacy-total-asset-history-quality-recovery.md)
- [WI-067 — Distinguish closed-market quiet windows from missing scheduled portfolio runs](work-items/WI-067-calendar-aware-pipeline-run-status.md)
- [WI-068 — Recover retained legacy portfolio history for bounded longitudinal use](work-items/WI-068-retained-legacy-history-recovery.md)
- [WI-069 — Align Project OS recovery lanes with stabilization and steady-state operations](work-items/WI-069-stabilization-recovery-operations-lanes.md)
- [WI-070 — Restore permanent held-position Telegram signal delivery](work-items/WI-070-permanent-held-position-telegram-signals.md)
- [WI-071 — Reconcile cash balances with trade settlement and surface unexplained movements](work-items/WI-071-owner-cash-flow-history-management.md)
- [WI-073 — Restore production journal OAuth consent and scope challenges](work-items/WI-073-journal-oauth-recovery.md)
- [WI-074 — Recover omitted domestic SOR executions and preserve complete trade collection](work-items/WI-074-domestic-sor-recovery.md)
- [WI-075 — Prevent incomplete overseas coverage from being reported as total assets](work-items/WI-075-total-asset-overseas-coverage-recovery.md)
- [WI-076 — Deliver held-position signal status at all three governed slots](work-items/WI-076-three-slot-held-signal-status.md)
- [WI-077 — Make accepted V2 documents navigable by feature, current task and symptom](work-items/WI-077-operational-documentation-navigation.md)


2026-11-02 owner review follow-up: WI-077-S01 displays each historical TODO candidate separately, preserving
unreviewed status and distinguishing completed/superseded construction premises. [Candidate list](../TODO.md#이전-todo의-개별-미검토-후보).


2026-11-03 WI-077-S02: owner requested semantic operating knowledge rather than reordered construction episodes.
Current semantic contracts and a byte-verified, fresh-restored compressed source archive are complete; product approval and runtime
boundaries remain unchanged.

현행 의미 규칙은 [운영 모델](operating-model.md)과 통합 계약에 있습니다. 위 WI·고정 commit 링크는 사례가 필요할 때만 읽습니다.

WI-077-S03 applies the operating knowledge structure to [Project OS](governance/project-operating-system.md)
and its Skill. See [work and evidence](work-items/WI-077-operational-documentation-navigation.md#wi-077-s03--steady-state-project-os-alignment).
