# MS-002 — Portfolio analytics, risk signals and Telegram delivery

> 상태: in progress
> 기준선: 2026-08-28.4
> machine registry: `governance/project/milestones.toml`

## Outcome

현재 보유 국내·미국 종목을 대상으로 수집된 point-in-time 데이터를 이용해 포트폴리오 성과, 추세,
lot/thread 위험과 ETF 간접 노출을 계산하고, 3년 replay와 2주 shadow를 거친 `주의` 이상 신호만 승인된
Telegram destination으로 전달한다.

## Baseline

Work Item 번호는 불변 identity이며 실행 순서는 아래 dependency를 따른다. 새 발견은 기존 번호를 밀지 않고
sub-item 또는 현재 최댓값 다음 Work Item으로 append한다.

| Sequence | Work Item | Design refs | Depends on | 상태 / 결과 |
| ---: | --- | --- | --- | --- |
| 1 | WI-013 metric foundation | V2-W0501 | WI-009, WI-012 | closed |
| 2 | WI-014 data-readiness review | review gate | WI-013 | closed |
| 3 | WI-015 dual-basis price history | V2-W0404 | WI-014 | closed |
| 4 | WI-016 broker history correction | V2-W0304, V2-W0403 | WI-014, WI-015 | closed |
| 5 | WI-017 held-instrument ETF routing | V2-W0405, V2-W0505 prerequisite | WI-014, WI-016 | closed; ID와 outcome 고정 |
| 6 | WI-019 trend/volatility metrics | V2-W0503 | WI-013, WI-015 | closed |
| 7 | WI-020 cash-event contract | V2-W0304 | WI-013, WI-016 | closed |
| 8 | WI-021 three-year trade/cash history | V2-W0403 | WI-016, WI-020 | closed; 131 partitions, private recovery and reconciliation passed |
| 9 | WI-036 corporate-action ledger | V2-W0307 | WI-015 | closed; repository-local PIT ledger and fail-closed coverage gate |
| 10 | WI-022 position/lot/sell reconstruction | V2-W0304, V2-W0305 | WI-010, WI-021, WI-036 | closed; 57 review exceptions, idempotency and private restore passed |
| 11 | WI-023 return/contribution/drawdown | V2-W0502 | WI-009, WI-015, WI-020..022 | closed; formula/replay/restore pass, production publish remains fail-closed on upstream quality |
| 12 | WI-024 typed thread risk plan | V2-W0305, V2-W0306 | WI-010, WI-022 | closed; owner-only revision/review/restore pass, production migration not applied |
| 13 | WI-025 lot/thread risk metrics | V2-W0504 | WI-015, WI-019, WI-022, WI-024 | closed; 8 PIT metrics, 6 focused/full 374 pass, production fail-closed |
| 14 | WI-026 ETF constituent forward collection | V2-W0405 | WI-012, WI-017 | blocked; explicit rights or licensed full-composition API required |
| 15 | WI-027 nested ETF look-through | V2-W0505 | WI-009, WI-017, WI-026 | blocked by WI-026 |
| 16 | WI-033 total-asset valuation-change contribution | V2-W0510 | WI-009, WI-013 | ready; return attribution과 분리 |
| 17 | WI-028 alert state/delivery ledger | V2-W0507 | WI-019, WI-023, WI-025, WI-027, WI-033 | proposed |
| 18 | WI-029 replay/shadow calibration | V2-W0509 | WI-028 | proposed |
| 19 | WI-030 outbound Telegram delivery | V2-W0508 | WI-029 | proposed; external-send approval gate |

`WI-018`은 이 baseline을 만드는 Project OS 거버넌스 작업이므로 MS-002의 제품 실행순서에는 포함하지 않는다.
기존에 텔레그램으로 논의했던 미완료 작업은 삭제되지 않았고, 완료된 `WI-017`을 보존하기 위해
`WI-030`으로 새 기준선화했다.

## Sub-item rule applied

`WI-026`의 provider별 권리 검토와 activation은 동일한 ETF forward-collection outcome 안에서
`WI-026-S01` TIME, `S02` KoAct, `S03` RISE, `S04` PLUS로 관리한다. 특정 provider가 독립 infrastructure,
별도 비용 또는 다른 rollback을 요구하면 그때 새 Work Item으로 승격하고 기존 sub-item은 발견 이력으로
남긴다.

## Acceptance gate

- W0502~W0505 metric이 point-in-time 및 quality contract를 통과한다.
- 3년 replay 결과와 자산유형별 threshold 근거가 있다.
- 2주 DB-only shadow에서 중복, 누락, 민감정보와 최대 오탐 사례를 검토한다.
- Telegram은 owner가 rule version, destination과 finance-free test message를 승인한 뒤에만 활성화한다.
- 10:00, 14:30, 16:00 KST 평가와 미국장 오전 마감 요약이 동일한 alert state machine을 사용한다.
- 전체 계좌번호, 총자산 절대액, credential과 raw source content가 payload/log에 없다.

## Known work outside this baseline

MS-003과 MS-004의 승인 설계는 `WI-035`, `WI-037`~`WI-051`, `WI-032`에 불변 ID로 배정됐다.
상세 순서와 acceptance gate는 각 milestone 문서와 machine registry가 소유한다.

## Revision log

| Version | Date | Change | Identity impact |
| --- | --- | --- | --- |
| 2026-08-28.3 | 2026-08-28 | 미배정 corporate-action identity를 WI-036으로 분리하고 후속 lot reconstruction 의존성에 연결 | 기존 ID 불변; WI-036 append, 후속 sequence만 이동 |
| 2026-08-28.2 | 2026-08-28 | 원화 평가액 변화 기여도를 WI-033으로 분리하고 alert 선행조건에 추가 | 기존 ID 불변; WI-028~030 sequence만 16~18로 변경 |
| 2026-08-28.1 | 2026-08-28 | WI-013~017 완료 이력을 고정하고 남은 작업을 WI-019~030으로 기준선화 | 기존 WI 변경 없음; Telegram은 WI-030으로 배정 |
