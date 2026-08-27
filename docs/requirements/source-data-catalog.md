# KIS Portfolio 소스 데이터 카탈로그

> 상태: 요구사항 분석용 초안
> 기준일: 2026-08-27
> 문서 범위: 원천 데이터 가용성·계약 조사
> 구현 상태: 미승인. 이 문서는 API 호출, DB 적재, schema 또는 배포 변경을 승인하지 않는다.

## 1. 목적과 책임

이 문서는 KIS Portfolio가 필요로 하는 논리 데이터를 어느 제공자의 어떤 API·파일·문서에서 얻을 수
있는지 endpoint 또는 dataset 단위로 관리한다.

- 이 문서: 원천 capability, endpoint, 조회 범위, 응답 grain, 운영 제약과 검증 상태
- `docs/data-catalog.md`: MotherDuck/DuckDB 객체의 목적, grain, key, 계층, 민감도와 백업 정책
- `docs/requirements/kis-portfolio-data-platform-requirements.md`: 사용자가 원하는 제품·분석 요구사항
- `docs/api-capability-map.md`: capability group 단위의 상위 수준 구현 방향

상위 capability가 존재하거나 코드에 endpoint 문자열이 있다는 사실만으로 데이터가 요구사항을 충족한다고
판정하지 않는다. 각 원천은 실제 계좌·시장 coverage, 과거 깊이, pagination, stable identity와 품질을
별도로 검증해야 한다.

## 2. 상태 정의

| 상태 | 의미 |
| --- | --- |
| `official-confirmed` | 기준일 현재 KIS 공식 예제 또는 공식 문서에서 계약을 확인함 |
| `implemented-unverified` | 현재 코드 경로가 있으나 공식 최신 계약 및 실제 응답 검증이 끝나지 않음 |
| `live-verified` | 승인된 read-only probe에서 실제 응답의 field·기간·pagination을 확인함 |
| `selected` | 요구사항에 사용할 원천으로 사용자가 승인함 |
| `gap` | 요구 grain이나 coverage를 충족하지 못하거나 확인 근거가 부족함 |

## 3. 1차 조사 범위: 주문·체결과 lot/thread

### SRC-KIS-DOM-ORDER-DAILY: 국내주식 주식일별주문체결조회

| 항목 | 조사 결과 |
| --- | --- |
| Provider | 한국투자증권 Open API |
| Capability | 국내주식 주문/계좌 |
| 공식 API | 주식일별주문체결조회 `[v1_국내주식-005]` |
| Endpoint | `/uapi/domestic-stock/v1/trading/inquire-daily-ccld` |
| 공식 현재 TR ID | 실전 최근 3개월 이내 `TTTC0081R`, 실전 3개월 이전 `CTSC9215R`; 모의 `VTTC0081R`, `VTSC9215R` |
| 주요 요청 축 | 계좌·상품코드, 시작/종료일, 매수/매도, 체결/미체결, 종목, 주문지점·주문번호, 거래소, 정렬 |
| Pagination | `CTX_AREA_FK100`, `CTX_AREA_NK100`, 응답 header의 `tr_cont` |
| 공식 호출 단위 | 실전 1회 최대 100건, 모의 1회 최대 15건; 이후 연속조회 |
| 현재 raw 저장 | Bronze `order_history`, 조회 호출 grain, append-only |
| 현재 canonical 저장 | Silver `domestic_orders`, 주문 grain upsert |
| 현재 canonical key | 계좌·상품코드·주문일·주문채번지점번호·주문번호 |
| 요구 연결 | 매수 lot 후보, 매도 연결, 매매일지, 포지션 reconciliation |
| 현재 상태 | `official-confirmed`, `live-verified`, `gap` |

공식 예제는 최근 3개월과 이전 구간을 명시적으로 분기하고, 3개월 이전 조회는 장 종료 후 짧은 기간으로
나눠 호출할 것을 권한다. 현재 서비스의 `inquery_order_list`는 legacy 최근구간 TR ID
`TTTC8001R`/`VTTC8001R`을 사용하고 이전구간 분기 및 연속조회를 수행하지 않는다.

2026-08-27 승인된 read-only probe에서 실전 최근구간 `TTTC0081R`과 이전구간 `CTSC9215R`을
실제 계좌에 호출했다. 민감한 payload는 출력하거나 저장하지 않고 상태, row 수, pagination과 field
이름만 확인했다.

| 계좌 유형 | 상품코드 | 최근구간 | 이전구간 | 판정 |
| --- | --- | --- | --- | --- |
| 위험자산 일임 | `01` | 성공, row 확인 | 성공, row 확인 | 두 구간 사용 가능 |
| ISA | `01` | 성공, row 확인 | 성공, 해당 시험 구간은 0 row | endpoint 동작 확인 |
| 일반 위탁 | `01` | 성공, row 확인 | 성공, row 확인 | 두 구간 사용 가능 |
| IRP | `29` | 실패 `APBK1744` | 성공, row 확인 | 최근구간 공통 endpoint 사용 불가; 전용 원천 조사 필요 |
| 연금저축 | `22` | 성공, row 확인 | 성공, 해당 시험 구간은 0 row | endpoint 동작 확인 |

IRP 최근구간 응답은 `퇴직연금계좌는 해당 서비스가 불가합니다.`라고 명시했다. 이전구간 endpoint가
row를 반환했다는 비대칭만으로 IRP 거래 원장 전체를 구성할 수 있다고 간주하지 않는다. 공식 예제 검색에서도
IRP 전용 주문·체결 이력 원천을 특정하지 못했으므로 이는 별도 source gap이다.

실제 `output1`은 `ord_dt`, `odno`, `ord_gno_brno`, `ord_tmd`, `pdno`, `sll_buy_dvsn_cd`,
`ord_qty`, `tot_ccld_qty`, `avg_prvs` 등 36개 field를 제공했다. 반면 개별 체결번호·체결시각·개별
체결수량을 나타내는 `ccld_no`, `ccld_tmd`, `ccld_qty`는 없었다. 즉 이 원천의 확인된 grain은
**개별 fill이 아니라 주문 단위 체결 집계**다. 수수료·세금 field도 주문 row에서 확인되지 않았다.

현재 canonical row에는 주문수량, 주문가격, 평균체결가, 총체결수량·금액과 잔량이 들어가지만 주문 안의
개별 체결 순번을 별도 grain으로 보존하지 않는다. 따라서 현재 데이터만으로는 다음을 보장하지 못한다.

- 최근 3개월 이전의 완전한 국내 거래 backfill
- 하루 100건을 초과한 실전계좌 주문의 완전성
- 한 주문이 여러 가격·시각에 나뉘어 체결된 경우의 fill별 lot
- IRP의 최근 주문·체결 이력 coverage

공식 근거:
[KIS 공식 국내주식 주식일별주문체결조회 예제](https://github.com/koreainvestment/open-trading-api/blob/main/examples_llm/domestic_stock/inquire_daily_ccld/inquire_daily_ccld.py)

### SRC-KIS-OVRS-ORDER-CCNL: 해외주식 주문체결내역

| 항목 | 조사 결과 |
| --- | --- |
| Provider | 한국투자증권 Open API |
| Capability | 해외주식 주문/계좌 |
| 공식 API | 해외주식 주문체결내역 `[v1_해외주식-007]` |
| Endpoint | `/uapi/overseas-stock/v1/trading/inquire-ccnl` |
| TR ID | 실전 `TTTS3035R`, 모의 `VTTS3035R` |
| 주요 요청 축 | 계좌·상품코드, 시작/종료일, 종목, 시장, 매수/매도, 체결/미체결, 정렬 |
| Pagination | `CTX_AREA_FK200`, `CTX_AREA_NK200`, 응답 header의 `tr_cont` |
| 공식 호출 단위 | 공식 예제 설명상 실전 1회 최대 20건, 모의 1회 최대 15건; 이후 연속조회 |
| 현재 raw 저장 | Bronze `overseas_order_history`, 조회 호출 grain, append-only |
| 현재 canonical 저장 | Silver `overseas_orders`, 주문 grain upsert |
| 현재 canonical key | 계좌·상품코드·주문일·거래소·주문채번지점번호·주문번호 |
| 요구 연결 | 해외 매수 lot 후보, 매도 연결, 매매일지, 포지션 reconciliation |
| 현재 상태 | `official-confirmed`, `live-verified`, `gap` |

2026-08-27 일반 위탁계좌에 대한 read-only probe에서 약 6개월 범위를 조회했고, 2개 page의 연속조회가
종료 조건까지 정상 동작했다. 실제 row에는 `ord_dt`, `odno`, `ord_gno_brno`, `ord_tmd`, `pdno`,
`sll_buy_dvsn_cd`, `ft_ccld_qty`, `ft_ccld_unpr3` 등 32개 field가 있었다. 개별 체결번호와
체결시각은 확인되지 않았다. 따라서 해외 주문체결내역도 **주문 단위 체결 집계**로 판정한다.

현재 서비스는 연속조회 helper를 사용하고 주문 단위 평균가격·체결수량을 canonical row로 만든다.
API가 제공하는 최장 과거 기간은 이번 probe만으로 확정하지 않는다.

공식 근거:
[KIS 공식 해외주식 주문체결내역 예제](https://github.com/koreainvestment/open-trading-api/blob/main/examples_user/overseas_stock/overseas_stock_functions.py)

### SRC-KIS-OVRS-PERIOD-TRANS: 해외주식 일별거래내역

| 항목 | 조사 결과 |
| --- | --- |
| Provider | 한국투자증권 Open API |
| Capability | 해외주식 주문/계좌 |
| 공식 API | 해외주식 일별거래내역 |
| Endpoint | `/uapi/overseas-stock/v1/trading/inquire-period-trans` |
| TR ID | 실전 `CTOS4001R`; 모의 지원 여부 확인 필요 |
| 주요 요청 축 | 계좌·상품코드, 등록 시작/종료일, 거래소, 종목, 매수/매도, 대출구분 |
| Pagination | `CTX_AREA_FK100`, `CTX_AREA_NK100`, 응답 header의 `tr_cont` |
| 현재 raw 저장 | Bronze `overseas_transaction_history`, 조회 호출 grain, append-only |
| 현재 canonical 저장 | Silver `overseas_transactions`, 정규화 raw-row grain upsert |
| 현재 canonical key | 계좌·상품코드·현재 구현이 생성한 `transaction_hash` |
| 확인 필드 | 거래일, 종목, 매수/매도, 수량, 가격, 거래금액, 원화·외화 수수료, 통화, 결제금액, 적용환율 |
| 요구 연결 | lot 원가·비용·환율, 실현손익, 배당·세금·현금흐름 분류 후보 |
| 현재 상태 | `official-confirmed`, `live-verified`, `gap` |

2026-08-27 일반 위탁계좌의 약 6개월 범위를 read-only probe한 결과 23개 거래 field와 4개 합계
field를 확인했다. `trad_dt`, `pdno`, `sll_buy_dvsn_cd`, `ccld_qty`, `ft_ccld_unpr2`,
`ovrs_stck_ccld_unpr`, `tr_amt`, `frcr_fee1`, `dmst_frcr_fee1`, `erlm_exrt`, `sttl_dt` 등이
있어 해외 lot의 비용·환율 보강에는 유용하다. 그러나 주문번호, 주문지점번호, 주문시각 또는 개별
체결번호는 없었다. 같은 날 같은 종목의 복수 주문을 특정 주문체결내역 row와 일의적으로 연결할 수 없다.

현재 natural key는 공식 거래 식별자가 아니라 선택 field의 hash에 의존한다. 또한 현재 normalizer가
기대하는 가격·수수료·환율 후보명과 실제 확인된 `ft_ccld_unpr2`, `frcr_fee1`, `erlm_exrt` 등이
일치하지 않아 일부 canonical 값이 0 또는 누락될 가능성이 있다. 이는 구현 결함 수정 승인이 아니라
후속 수집 계약과 구현 계획에서 다뤄야 할 확인사항이다.

공식 근거:
[KIS 공식 legacy 해외주식 예제](https://github.com/koreainvestment/open-trading-api/blob/main/legacy/Sample01/kis_ovrseastk.py)

## 4. lot/thread 구축 적합성 1차 판정

| 요구 grain | 현재 이용 가능한 정보 | 1차 판정 |
| --- | --- | --- |
| 증권사 평단가 position | 국내·연금·해외 잔고 API와 canonical snapshot | 현재 기본 트랙으로 사용 가능, 계좌별 reconciliation 필요 |
| 주문 단위 purchase lot | 국내·해외 주문번호, 주문시각, 평균체결가·총체결수량 | `selected`; v1 grain으로 승인 |
| 개별 fill 단위 execution | 확인된 국내·해외 응답에 fill 번호·시각·수량이 없음 | `gap`; 별도 원천 확보 전에는 생성 금지 |
| 해외 비용·환율 포함 lot | 일별거래내역에 비용·환율은 있으나 주문 identity가 없음 | 보강 원천으로 조건부 사용; 모호한 자동 join 금지 |
| 매도와 lot/thread 연결 | 원천은 매도를 제공하지만 어떤 매수 의도를 청산했는지는 제공하지 않음 | 사용자 지정 또는 명시적 내부 배분 규칙 필요 |
| 과거 현재보유 lot 재구성 | 국내 이전구간 API 후보, 해외 기간 API | 제공 깊이·계좌 coverage 미확정 |
| trade thread와 매매일지 | 증권사 원천에는 투자 의도가 없음 | 사용자·LLM 입력이 authoritative source |

### 4.1 v1 grain 결정 — 승인

- `purchase lot`의 최초 grain은 **총체결수량이 0보다 큰 매수 주문 1건**으로 한다.
- 내부 identity 후보는 계좌 alias·상품코드·주문일·주문채번지점번호·주문번호이며, 해외는 거래소를
  추가한다. 사용자용 `display_key`와 분리한다.
- 한 주문의 여러 fill은 원천이 제공하는 평균체결가와 총체결수량으로 한 lot에 표현한다. 이를 개별
  fill처럼 꾸며내지 않는다.
- 하나의 `trade thread`는 사용자의 투자 판단에 따라 하나 이상의 주문 단위 lot을 묶는다.
- 해외 일별거래내역의 비용·환율은 확실한 연결 규칙이 있는 경우에만 lot을 보강한다. 그렇지 않으면
  별도 거래 사건으로 보존하고 reconciliation 대상으로 남긴다.
- 향후 체결번호·체결시각·개별 체결수량을 제공하는 신뢰 가능한 원천이 확보되면 fill grain을 하위
  계층으로 추가할 수 있게 설계한다.

이 grain은 2026-08-27 사용자 승인으로 `selected` 상태가 되었다. 이는 논리 데이터 계약의 승인이지
물리 schema, 수집 코드, backfill 또는 배포의 구현 승인은 아니다.

## 5. 품질 및 identity 요구

- 원천 주문·체결 row를 Bronze에 append-only로 보존하고 수집 시각과 요청 범위를 기록한다.
- canonical identity는 표시 키와 분리한다.
- 사용자 표시 키는 `yyyy-mm-dd-hh-mm-ss-종목코드-매수` 형식을 지원하되 계좌·시장·원천 식별자를
  내부 identity에서 제거하지 않는다.
- 각 row의 source 상태를 `actual`, `manual`, `reconstructed`, `inferred_opening` 등으로 구분한다.
- pagination 종료, 요청 기간 coverage, row count와 raw-to-canonical 변환 수를 수집 실행별로 검증한다.
- lot 잔여수량 합계와 canonical position 수량을 정기적으로 reconciliation한다.
- 증권사의 공식 평단가·실현손익과 내부 lot 배분 손익을 같은 이름으로 제공하지 않는다.

## 6. 다음 검증 게이트

다음 단계는 구현이 아니라 승인된 read-only source probe와 응답 계약 확정이다.

1. IRP 최근 주문·체결 이력을 제공하는 전용 endpoint 또는 대체 원천을 조사한다.
2. 현재 보유종목의 최초 매수를 복원할 수 있는 과거 깊이를 계좌별로 측정한다.
3. 국내 100건 초과 및 해외 다중 page 조건에서 pagination 완전성 계약을 추가 검증한다.
4. 해외 주문과 일별거래내역을 안전하게 연결할 수 있는 조건과 모호성 처리 규칙을 정의한다.
5. 실제 응답 fixture가 필요하면 계좌번호·종목·금액을 제거한 field-name/shape만 보존한다.
6. 다음 장바구니인 가격·거래량·RSI 원천의 endpoint, 기간, 조정주가와 시장 coverage를 조사한다.

## 7. 조사 이력

| 날짜 | 상태 | 내용 |
| --- | --- | --- |
| 2026-08-27 | `selected` | v1 purchase lot을 총체결수량이 0보다 큰 매수 주문 1건 단위로 승인함. fill grain은 신뢰 가능한 원천 확보 후 확장함 |
| 2026-08-27 | read-only live 검증 | 국내 5개 계좌 유형의 최근·이전 구간, 해외 주문체결 pagination, 해외 일별거래내역 field shape를 민감값 없이 확인함. 개별 fill identity 부재와 IRP 최근구간 gap을 기록함 |
| 2026-08-27 | 1차 조사 | 국내·해외 주문체결 및 해외 일별거래내역을 lot/thread 원천 후보로 대조하고 현재 coverage gap을 기록함 |
