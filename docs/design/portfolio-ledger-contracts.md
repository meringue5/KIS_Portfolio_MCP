# 원장·거래 구간·포지션 재구성 규칙

> 기존 승인 계약의 현행 의미를 통합합니다. source 수집·보정·migration 권한을 새로 주지 않습니다.
> [운영 모델](../operating-model.md) · [물리 객체](../data-catalog.md) · [구현·테스트 지도](../traceability.md)

## 무엇이 사실이고 무엇이 파생인가

Bronze source 관측, canonical 거래 identity/revision, 현재 broker position, episode/lot/allocation은 다른 객체입니다.
보유수량은 cutoff 시점의 기준일 뿐 과거 매수나 원가를 증명하지 않습니다. 원문은 append-only로 보존하고,
source-proven alias/보정 revision과 current/as-of projection으로 중복·정정을 처리합니다.

| 축 | 상태 | 해석 |
| --- | --- | --- |
| 근거 출처 | `actual`, `manual`, `inferred_opening` | 사실을 어떻게 알았는가 |
| 재구성 결과 | `reconstructed`, `inferred_opening`, `provisional`, `not_assessed`, `reconciliation_exception` | 이 구간의 수량을 대사한 projection으로 쓸 수 있는가 |

실제 체결이 있어도 전체 구간 재구성은 provisional일 수 있습니다. inferred opening은 실제 매수로 바뀌지 않습니다.

## 수집 구간과 완전성

- partition은 source operation·account alias·상품 code·real/virtual profile·시장/거래소·route·시작/끝을 포함합니다.
  credential은 identity나 공개 계획에 넣지 않습니다. 문법 변경은 plan version을 바꾸며 기존 checkpoint를 재해석하지 않습니다.
- bounded 과거 계획은 요청일/as-of 이내, 최대 3 calendar years입니다. 기본 60일, hard maximum 90일 shard가
  중복/빈 날짜 없이 전체 요청을 덮습니다. 국내 old/recent route 경계는 as-of−90일에서 나누고 shard가 경계를 넘지 않습니다.
- IRP recent route나 국내 일반 cash source처럼 선택된 source가 없는 구간은 named gap입니다. 다른 계좌/시장,
  잔고 역산, order와 별도 transaction stream으로 gap을 채우지 않습니다. 실제 callable scope는 versioned planner와 source 계약을 확인합니다.
- watermark는 resume hint입니다. 정확한 source·계좌·시장·기간의 성공 terminal run, pagination·source-row reconciliation,
  quality, lineage와 publish가 함께 증명한 구간만 union하고, 모든 필수 operation의 교집합으로 요청 구간을 판정합니다.
- complete coverage 아래 빈 결과와 source failure/missing partition의 빈 결과는 다릅니다. 상한 날짜나 행 존재만으로 pass를 만들지 않습니다.

## 호출 예산과 실행 효과

기존 bounded backfill의 기본 page 정책은 domestic order 3, overseas order 3, overseas transaction 2이며
60일 partition 기준입니다. global physical-call 기본 상한은 400, helper hard cap은 source당 10 pages입니다.
이는 안전 상한이며 완전성 보증이나 현재 데이터량 예측이 아닙니다. 승인된 버전/설정은 원래 수치와 함께 검토합니다.

1. plan hash와 별도로 budget hash를 고정하고, callable partition 전체의 worst-case 예약이 global 상한을 넘으면 호출 전 실패합니다.
2. 각 물리 HTTP 요청 직전에 partition page와 global call을 원자적으로 예약합니다. 실패한 network 시도도 소비합니다.
3. unknown partition·known gap·page/global 고갈은 source callable 전에 거절합니다. 내부 pagination 전체를 한 call로 세지 않습니다.
4. source가 다음 page를 가리키는데 상한에 닿으면 incomplete입니다. capped 행을 완전 구간으로 publish하지 않습니다.
5. managed execution은 logical key·lease·stage evidence를 보존합니다. destructive replay·대량 backfill·운영 변경은 기존 승인 경로를 따릅니다.

## 재구성과 sell allocation

episode는 한 계좌·canonical instrument의 연속 비영(非零) 보유 구간입니다. 수량이 0이 되면 닫히고 재매수는
새 episode입니다. account/instrument/episode를 넘어 lot이나 sell slice를 배분하지 않습니다.
승계는 governed corporate-action identity effect로만 연결하며 이름/심볼 유사성으로 이어 붙이지 않습니다.

입력은 timezone-aware이고 명시한 window·계좌·instrument lineage 안에 있으며 quality pass인 revision입니다.
action 한 revision의 quantity/price/successor effect는 각 최대 하나이고 effective/knowledge time과 입력 instrument가 일치해야 합니다.
정렬은 `(effective time, execution sequence, stable identity)`입니다. 같은 시각의 trade/action 충돌, 복수 action revision,
반대 체결 side의 모호한 순서를 임의로 결정하지 않습니다.

현재 수량에서 매수는 빼고 매도는 더하며 quantity factor를 정확한 rational로 역적용해 시작 잔량을 구합니다.
음수 잔량·깨진 successor chain·비 decimal 수량·소수점 10자리 초과는 exception입니다. action coverage pass와
source gap 없음 아래 양수 잔량만 `inferred_opening`이며 체결 참조·과거 가격·원가를 만들지 않습니다.
그 상태를 같은 순서로 forward replay하고, 수량 부족이면 전체 plan을 막습니다.

매도 selector의 우선순위는 **명시 lot → 명시 thread → 같은 episode 전체 FIFO**입니다. FIFO는 `(opened_at, lot_id)`입니다.
명시한 selector의 대상이 없거나 수량이 모자라면 범위를 넓히거나 가상 매수/음수 lot을 만들지 않습니다. 미지정 FIFO는 owner 검토 대상입니다.

## 판정과 저장

| 조건 | 결과 / 저장 경계 |
| --- | --- |
| 음수 잔량·실패한 action coverage·모호한 순서·재생 수량 불일치 | `reconciliation_exception`, Silver 후보 fact 없음 |
| action coverage 미평가 | `not_assessed`, 파생 fact 없음 |
| named source gap | `provisional`, 파생 fact 없음 |
| pass coverage·gap 없음·양수 시작 잔량 | `inferred_opening`, 출처 표지와 가격/원가 unknown 보존 |
| exact quantity reconciliation | `reconstructed` |

뒤 두 상태만 blocker 없이 reconciled projection에 사용할 수 있습니다. episode별 출처/상태와 plan 전체의 inferred-opening 필요 여부를 구분합니다.

- `replay_hash`는 canonical 입력·coverage·gap, `projection_hash`는 모든 후보 fact를 묶습니다. 저장 전에 projection hash와
  비밀 없는 partition/request scope·현재수량을 재계산해 plan 변조를 거절합니다.
- identity는 한번만 insert/verify합니다. 동일 plan은 no-op, 다른 input은 knowledge time이 증가할 때만 새 revision입니다.
- episode/lot state, whole sell-allocation header+모든 slices, exception resolve와 current-view 대사를 한 transaction으로 처리합니다.
  mismatch/constraint 실패는 전체 rollback이며 partial episode/lot/allocation을 남기지 않습니다.
- 양수 현재 position에는 open episode가 정확히 하나, 0에는 없습니다. episode 수량=lot 잔량 합, lot 잔량은 0 이상/effective 수량 이하입니다.
- 각 sell의 requested=allocated+unallocated, unallocated=0, slice 합=allocated이며 slice는 같은 episode 안입니다.
  successor가 있어도 sell instrument는 당시 체결의 instrument입니다.
- blocked plan은 Control exception의 open revision만 남깁니다. 같은 blocker는 no-op이며, 후속 성공이 passing replay를 가리키는
  resolved revision을 추가합니다. 이전 실패를 삭제하지 않습니다.

## 변경과 검증의 출발점

[구간 증명](../../src/kis_portfolio/services/trade_coverage.py), [source 계획](../../src/kis_portfolio/services/trade_cash_backfill.py),
[재생](../../src/kis_portfolio/services/position_replay.py), [저장](../../src/kis_portfolio/adapters/outbound/position_reconstruction_warehouse.py).
독립 oracle은 [coverage](../../tests/test_trade_coverage_intervals.py), [계획](../../tests/test_trade_cash_backfill_planner.py),
[재생](../../tests/test_position_replay.py), [저장/복원](../../tests/test_position_reconstruction_warehouse.py)에서 확인합니다.

개별 계좌·날짜의 dry-run/execute·복구 결과와 최초 단계의 계획은 [압축 구축 기록](../history/README.md)에 있습니다.
그 당시 call count나 단계별 미활성 상태를 현재 계약/가용성으로 복제하지 않습니다.
