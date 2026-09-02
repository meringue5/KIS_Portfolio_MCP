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
| IRP | `29` | 실패 `APBK1744` | 성공, row 확인 | 최근구간 공통 endpoint 사용 불가; 지연 수집과 fallback 필요 |
| 연금저축 | `22` | 성공, row 확인 | 성공, 해당 시험 구간은 0 row | endpoint 동작 확인 |

IRP 최근구간 응답은 `퇴직연금계좌는 해당 서비스가 불가합니다.`라고 명시했다. 이전구간 endpoint는
3년 probe의 짧은 조회 구간에서 오류 없이 과거 row를 반환했다. 따라서 오래된 IRP 주문은 지연 수집할
수 있지만, 최근 약 3개월을 같은 원천으로 즉시 복원할 수는 없다.

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

### SRC-KIS-IRP-DAILY-CCLD: 퇴직연금 미체결내역

| 항목 | 조사 결과 |
| --- | --- |
| Provider | 한국투자증권 Open API |
| Capability | 국내주식 주문/계좌·퇴직연금 |
| 공식 API | 퇴직연금 미체결내역 `[v1_국내주식-033]` |
| Endpoint | `/uapi/domestic-stock/v1/trading/pension/inquire-daily-ccld` |
| TR ID | 실전 `TTTC2201R` |
| 주요 요청 축 | 계좌·상품코드, 사용자구분, 매수/매도, 전체·체결·미체결, 조회구분 |
| 날짜 범위 | 날짜 파라미터 없음 |
| Pagination | `CTX_AREA_FK100`, `CTX_AREA_NK100`, 응답 header의 `tr_cont` |
| 요구 연결 | IRP 당일 주문 상태의 보조 관측 후보 |
| 현재 상태 | `official-confirmed`, `live-verified`, `gap` |

공식 명칭은 미체결내역이지만 `CCLD_NCCS_DVSN`은 전체·체결·미체결을 선택할 수 있다. 날짜를 받지
않으므로 과거 backfill 원천으로 선정하지 않는다. 2026-08-27 read-only probe에서는 전체와 체결 조회
모두 0 row였고 빈 page에서도 continuation header가 반복되었다. 구현 시에는 빈 page, 동일 context와
최대 page를 모두 종료 조건으로 사용해야 한다.

현재 보유상태는 별도 퇴직연금 체결기준잔고 `TTTC2202R` 또는 잔고조회 `TTTC2208R`에서 확인할 수
있지만, 잔고는 개별 매수 사실을 복원하지 않는다. 따라서 IRP의 최근구간은 잔고 기반 provisional 상태,
사용자 보완 및 3개월 이후 이전구간 endpoint의 지연 reconciliation을 조합해야 한다.

공식 근거:
[KIS 공식 퇴직연금 미체결내역 예제](https://github.com/koreainvestment/open-trading-api/blob/main/examples_llm/domestic_stock/pension_inquire_daily_ccld/pension_inquire_daily_ccld.py),
[KIS 공식 퇴직연금 체결기준잔고 예제](https://github.com/koreainvestment/open-trading-api/blob/main/examples_llm/domestic_stock/pension_inquire_present_balance/pension_inquire_present_balance.py)

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
3년 read-only probe는 60일 구간으로 분할했을 때 오류 없이 완료됐다. 180일 구간은 연속조회 중
`SYDB0050` 데이터 변경 오류가 발생했으므로 초도 적재도 짧은 shard, bounded retry와 watermark를
사용해야 한다. API가 제공하는 절대 최장 보존기간은 이번 결과만으로 확정하지 않는다.

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

3년 probe에서는 해외 주문 43건과 일별거래 39건이 관측됐다. 일별거래 39건 모두 수수료와 적용환율이
있었다. 계좌·거래일·종목·매수매도·수량만으로 대조하면 35건은 주문 후보가 하나였고 4건은 일치 후보가
없었다. 이번 표본에 복수 후보는 없었지만 공식 order identity가 없으므로 35건도 원천상 확정 join이
아니라 가역적인 `derived_candidate` 관계로만 취급해야 한다.

공식 근거:
[KIS 공식 legacy 해외주식 예제](https://github.com/koreainvestment/open-trading-api/blob/main/legacy/Sample01/kis_ovrseastk.py)

## 4. lot/thread 구축 적합성 1차 판정

| 요구 grain | 현재 이용 가능한 정보 | 1차 판정 |
| --- | --- | --- |
| 증권사 평단가 position | 국내·연금·해외 잔고 API와 canonical snapshot | 현재 기본 트랙으로 사용 가능, 계좌별 reconciliation 필요 |
| 주문 단위 purchase lot | 국내·해외 주문번호, 주문시각, 평균체결가·총체결수량 | `selected`; v1 grain으로 승인 |
| 개별 fill 단위 execution | 확인된 국내·해외 응답에 fill 번호·시각·수량이 없음 | `gap`; 별도 원천 확보 전에는 생성 금지 |
| 해외 비용·환율 포함 lot | 일별거래내역에 비용·환율은 있으나 주문 identity가 없음 | `selected`; 유일 후보만 가역적 `derived_candidate` link |
| 매도와 lot/thread 연결 | 원천은 매도를 제공하지만 어떤 매수 의도를 청산했는지는 제공하지 않음 | `selected`; explicit 우선, 미지정은 FIFO `inferred` |
| 과거 현재보유 lot 재구성 | 3년 probe와 현재 잔고 reconciliation | `selected`; 3년 backfill 후 잔여분만 opening/exception |
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

### 4.2 3년 backfill 복원성 probe

2026-08-27에 2023-08-28부터 2026-08-27까지 읽기 전용으로 조사했다. 원천 payload, 종목, 수량,
가격과 금액은 저장하거나 문서화하지 않았다. 아래의 수량 일치는 corporate action과 계좌이체를 아직
반영하지 않은 **복원 후보 판정**이지 회계적 확정이 아니다.

| 범위 | 현재 보유종목 수 | 3년 내 매수 근거 | 잔고 수량 일치 후보 | 판정 |
| --- | ---: | ---: | ---: | --- |
| 비IRP 국내 4개 계좌 합계 | 15 | 15 | 15 | 3년 주문 backfill로 초기 재구성 가능성이 높음 |
| IRP | 7 | 6 | 0 | 최근 약 3개월 공백 때문에 전 종목 reconciliation 필요 |
| 미국주식 | 4 | 3 | 0 | 실제 주문 lot은 보존하되 전 종목에 잔여 opening/reconciliation 필요 |

비IRP 국내의 일치는 신뢰도를 높이지만 corporate action, 외부 입고와 과거 정정이 없었다는 검증 전에는
`reconstructed`를 넘어 `actual` position history로 승격하지 않는다. IRP와 해외는 관측된 실제 주문을
버리지 않고, 현재 잔고와의 차이만 `inferred_opening` 또는 `reconciliation_exception`으로 분리한다.

## 5. 품질 및 identity 요구

- 원천 주문·체결 row를 Bronze에 append-only로 보존하고 수집 시각과 요청 범위를 기록한다.
- canonical identity는 표시 키와 분리한다.
- 사용자 표시 키는 `yyyy-mm-dd-hh-mm-ss-종목코드-매수` 형식을 지원하되 계좌·시장·원천 식별자를
  내부 identity에서 제거하지 않는다.
- 각 row의 source 상태를 `actual`, `manual`, `reconstructed`, `inferred_opening` 등으로 구분한다.
- pagination 종료, 요청 기간 coverage, row count와 raw-to-canonical 변환 수를 수집 실행별로 검증한다.
- lot 잔여수량 합계와 canonical position 수량을 정기적으로 reconciliation한다.
- 증권사의 공식 평단가·실현손익과 내부 lot 배분 손익을 같은 이름으로 제공하지 않는다.

## 6. 2차 조사 범위: 가격·추세·ETF 노출

### SRC-KIS-DOM-DAILY-BAR: 국내주식 기간별 일봉

| 항목 | 조사 결과 |
| --- | --- |
| Provider | 한국투자증권 Open API |
| Endpoint / TR ID | `/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice` / `FHKST03010100` |
| 요청 축 | 시장, 종목, 시작·종료일, 일·주·월·년, 수정·원주가 |
| 반환 grain | 종목·거래일·price basis |
| 주요 필드 | OHLC, 거래량, 거래대금, 변경 여부, 분할비율, 재평가사유 |
| 호출 단위 | 최대 100행; 날짜 shard 필요, continuation header 없음 |
| 조정 계약 | `FID_ORG_ADJ_PRC=0` 수정주가, `1` 원주가 |
| 현재 저장 | Silver cache `price_history`; raw Bronze 없음 |
| 현재 gap | 수정주가를 `adjusted=FALSE`로 저장할 수 있고 dual basis PK가 없음 |
| 상태 | `official-confirmed`, `live-verified`, `selected`, 현재 구현은 `gap` |

3년 범위를 한 번 호출한 probe는 최신 100행만 반환했다. 따라서 승인된 3년 backfill은 날짜 범위를
100거래일보다 짧은 shard로 분할하고 시작·종료 coverage를 검증해야 한다.

공식 근거:
[KIS 공식 국내주식기간별시세 예제](https://github.com/koreainvestment/open-trading-api/blob/main/examples_llm/domestic_stock/inquire_daily_itemchartprice/inquire_daily_itemchartprice.py)

### SRC-KIS-US-DAILY-BAR: 해외주식 기간별 일봉

| 항목 | 조사 결과 |
| --- | --- |
| Provider | 한국투자증권 Open API |
| Endpoint / TR ID | `/uapi/overseas-price/v1/quotations/dailyprice` / `HHDFS76240000` |
| 요청 축 | 거래소, 종목, 기준일, 일·주·월, 수정주가 반영 여부 |
| 반환 grain | 거래소·종목·거래일·price basis |
| 주요 필드 | OHLC, 거래량, 거래대금, 호가·잔량 |
| 호출 단위 | 100행; 실제 `tr_cont=F`, 공식 예제 연속조회 사용 |
| 조정 계약 | `MODP=0` 미반영, `1` 반영 |
| 현재 저장 | Silver cache `price_history`; raw Bronze 없음 |
| 현재 gap | 현재 서비스는 첫 page만 저장하고 dual basis를 표현하지 못함 |
| 상태 | `official-confirmed`, `live-verified`, `selected`, 현재 구현은 `gap` |

분할 구간 probe에서 수정 옵션에 따라 100행의 가격이 모두 달랐지만 거래량은 동일했다. 거래량은
vendor raw observation으로 보존하고 corporate action 보정 전에는 분할 전후 상대비교 품질을 낮춰야 한다.

공식 근거:
[KIS 공식 해외주식 기간별시세 예제](https://github.com/koreainvestment/open-trading-api/blob/main/examples_llm/overseas_stock/dailyprice/dailyprice.py)

### SRC-KIS-CORPORATE-ACTION: 국내 예탁원 일정·해외 기간별 권리

| 항목 | 조사 결과 |
| --- | --- |
| Provider | 한국투자증권 Open API |
| 국내 Endpoint / TR ID | `/uapi/domestic-stock/v1/ksdinfo/merger-split` / `HHKDB669104C0`; `/uapi/domestic-stock/v1/ksdinfo/rev-split` / `HHKDB669105C0` |
| 해외 Endpoint / TR ID | `/uapi/overseas-price/v1/quotations/period-rights` / `CTRGT011R` |
| 요청 축 | 국내 종목·기간·시장; 해외 권리유형·현지기준일 기간·상품번호·상품유형 |
| 반환 grain | source endpoint의 종목·권리유형·기준/적용일·sequence row |
| 국내 주요 필드 | 기준일, 합병/분할 양측 회사코드, 합병사유·비율, 변경 전/후 액면가, 거래정지·상장일 |
| 해외 주요 필드 | 권리유형코드, 상품/표준상품번호, 현지기준일, 주식·현금 배정비율, 확정여부 |
| revision 계약 | stable source id가 없으므로 endpoint·market·source instrument·action code·effective dates·source sequence를 deterministic source record identity로 만들고 content 변경을 새 knowledge revision으로 보존 |
| 품질 한계 | 해외 `주식배정비율`과 국내 자유형식 `합병비율`은 단위 의미를 검증하기 전 pre/post units로 추정하지 않음; 예정·미확정·대상 instrument 미해결은 계산 차단 |
| 상태 | `official-confirmed`, `selected`; WI-036은 offline fixture·ledger·recovery만 구현하고 production sampling/schedule은 별도 gate |

분할·병합 여부만 관측됐다는 사실과 가격·수량에 적용할 수 있는 확정 비율을 분리한다. 국내 액면교체의
양의 변경 전/후 액면가는 방향이 명시되므로 reciprocal price/quantity effect를 만들 수 있다. 그 밖의
자유형식 비율과 예정 권리는 raw provenance를 남기되 `unknown` 또는 `provisional`로 보존하여 lot과
성과 계산이 그 조건을 사실처럼 사용하지 못하게 한다.

공식 근거:
[KIS 공식 국내 합병·분할일정 예제](https://github.com/koreainvestment/open-trading-api/blob/main/examples_llm/domestic_stock/ksdinfo_merger_split/ksdinfo_merger_split.py),
[KIS 공식 국내 액면교체일정 예제](https://github.com/koreainvestment/open-trading-api/blob/main/examples_llm/domestic_stock/ksdinfo_rev_split/ksdinfo_rev_split.py),
[KIS 공식 해외 기간별권리조회 예제](https://github.com/koreainvestment/open-trading-api/blob/main/examples_llm/overseas_stock/period_rights/period_rights.py)

### SRC-KIS-ETF-COMPONENT: ETF 구성종목시세

| 항목 | 조사 결과 |
| --- | --- |
| Provider | 한국투자증권 Open API |
| Endpoint / TR ID | `/uapi/etfetn/v1/quotations/inquire-component-stock-price` / `FHKST121600C0` |
| 요청 축 | 국내 ETF 종목코드 |
| 반환 grain | ETF·현재 조회시점·반환 구성상품 |
| 주요 필드 | 구성상품 코드·명칭·현재가·평가금액·비중·시가총액 |
| 날짜·과거축 | 없음; 현재 관측 |
| 현재 보유 probe | 14/14 성공, 선언 642행 중 286행 반환, 8종은 30행, continuation 없음 |
| 요구 연결 | 당일 상위 구성종목 확인, KRX/운용사 PDF cross-check |
| 한계 | 전체 구성과 역사적 snapshot을 보장하지 않음 |
| 상태 | `official-confirmed`, `live-verified`, 보조 원천으로 `selected`, 완전성은 `gap` |

모든 시험 ETF에서 output1의 선언 구성종목 수가 output2 반환 수보다 컸다. 따라서 완전한 ETF
look-through의 canonical source로 선정하지 않는다.

공식 근거:
[KIS 공식 ETF 구성종목시세 예제](https://github.com/koreainvestment/open-trading-api/blob/main/examples_user/etfetn/etfetn_functions.py)

### SRC-KRX-ETF-PDF: KRX 납입자산구성내역

| 항목 | 조사 결과 |
| --- | --- |
| Provider | 한국거래소 및 ETF 집합투자업자 |
| 공식 dataset | ETF PDF (Portfolio Deposit File) |
| 노출 위치 | KRX Data Marketplace `증권상품 > ETF > PDF`, 운용사 상품 페이지 |
| 공시 주기 | 거래일마다 공시 |
| 반환 grain 후보 | ETF·기준일·구성자산 |
| 요구 필드 | 구성자산 식별자·명칭·수량·평가금액·비중, 기준일, source URL·hash |
| 요구 연결 | canonical ETF 구성 snapshot과 direct/recursive look-through |
| 현재 상태 | 미래 canonical 후보로 `selected`, `official-confirmed`; 자동수집·과거 coverage·이용조건은 `gap`, DEC-049로 initial V2 제외 |

KRX는 PDF가 거래소와 운용사 홈페이지에 매일 공시된다고 설명한다. 현재 보유 운용사 페이지에서도
구성종목과 Excel 다운로드가 확인된다. 구현 전에는 KRX dataset의 안정적인 자동 접근 방식, 이용조건,
과거 날짜 조회와 운용사별 fallback을 별도 probe한다.

공식 근거:
[KRX ETF 설명](https://m.krx.co.kr/contents/06/0609/060901/JHPETP060901M01.jsp),
[KRX Data Marketplace](https://data.krx.co.kr/contents/MDC/MAIN/main/index.cmd)

### 계산 데이터 계약 후보

RSI, 이동평균, rolling high와 ETF look-through는 외부 원천 dataset이 아니라 위 원천에서 재생성하는
Gold 지표다. B-1~B-5 승인으로 수정주가, SMA20·50·120, 거래량 20일 비율, Wilder RSI14, 보유 에피소드
고점과 ETF look-through 계약을 `selected`로 확정했다. 이후 DEC-049가 ETF look-through만 초기 V2
인수범위에서 제외했으며 source 후보와 품질 계약은 미래 재도입을 위해 보존한다.

## 7. 3차 조사 범위: 실적·가치·배당·매크로

### SRC-OPENDART-FILING-FUNDAMENTALS: 국내 공시·실제 실적

| 항목 | 조사 결과 |
| --- | --- |
| Provider | 금융감독원 OpenDART |
| Dataset/API | 공시검색, 공시서류 원문, 고유번호, 단일회사 전체 재무제표, 배당사항 |
| Identity | `stock_code ↔ corp_code`, 접수번호, 보고서코드, 사업연도, 연결/별도 |
| 반환 grain | filing revision 또는 회사·보고기간·재무제표·계정 |
| revision | 수정공시와 접수번호를 별도 보존 가능 |
| 요구 연결 | actual fundamentals, 실적발표, 배당 선언, 기업 사건 |
| 현재 상태 | `official-confirmed`; API key·보유종목 live coverage는 구현 전 검증 필요 |

OpenDART는 공시 원문 XML과 구조화된 주요·전체 재무정보를 제공한다. 국내 실제 실적의 canonical source로
권고한다. KIS 재무 endpoint는 더 빠른 cross-check가 가능하지만 공시 identity와 수정공시 원장을
대체하지 않는다.

공식 근거:
[OpenDART OpenAPI 소개](https://opendart.fss.or.kr/intro/main.do),
[OpenDART 공시검색](https://opendart.fss.or.kr/guide/detail.do?apiGrpCd=DS001&apiId=2019001),
[OpenDART 배당사항](https://opendart.fss.or.kr/guide/detail.do?apiGrpCd=DE002&apiId=AE00006)

### SRC-SEC-EDGAR-FUNDAMENTALS: 미국 공시·실제 실적

| 항목 | 조사 결과 |
| --- | --- |
| Provider | U.S. SEC EDGAR |
| Dataset/API | submissions, XBRL `companyfacts`, filing archives, nightly bulk ZIP |
| Identity | CIK, accession number, form, filed-at, fiscal period, XBRL concept·unit |
| 인증 | public data API는 API key 불필요; 식별 가능한 User-Agent와 공정접근 준수 필요 |
| 요구 연결 | 미국 actual fundamentals, filing event, revision history |
| 한계 | analyst consensus·목표주가를 제공하지 않음; ticker/CIK mapping은 보조자료 |
| 현재 상태 | `official-confirmed`; 현재 보유 CIK mapping과 concept normalization은 구현 전 검증 필요 |

공식 근거:
[SEC EDGAR data APIs](https://www.sec.gov/search-filings/edgar-application-programming-interfaces),
[SEC EDGAR data access](https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data)

### SRC-KIS-DOM-FINANCE: 국내 재무비율

| 항목 | 조사 결과 |
| --- | --- |
| Provider | 한국투자증권 Open API |
| Endpoint / TR ID | `/uapi/domestic-stock/v1/finance/financial-ratio` / `FHKST66430300` |
| 요청 축 | 종목, 연간/분기, KRX 시장 |
| 확인 필드 | 결산년월, EPS, BPS, SPS, ROE, 영업이익률, 순이익률, 부채·유보율 |
| live probe | 국내 6자리 보유 후보 8개 모두 호출 성공, 3개에서 row 반환 |
| 요구 연결 | actual ratio fast path·OpenDART cross-check |
| 현재 상태 | `official-confirmed`, `live-verified`; canonical actual source로는 `gap` |

재무상태표·손익계산서·성장성·수익성·안정성 API도 공식 예제에 있으나 현재 코드에는 구현돼 있지 않다.
보유 ETF는 회사 재무제표 대상이 아니므로 상품 전체 coverage 지표와 기업 coverage를 구분해야 한다.

공식 근거:
[KIS 공식 국내주식 예제](https://github.com/koreainvestment/open-trading-api/blob/main/examples_user/domestic_stock/domestic_stock_examples.py)

### SRC-KIS-DOM-ESTIMATE: 국내 종목추정실적

| 항목 | 조사 결과 |
| --- | --- |
| Provider | 한국투자증권 Open API |
| Endpoint / TR ID | `/uapi/domestic-stock/v1/quotations/estimate-perform` / `HHKST668300C0` |
| live probe | 국내 6자리 보유 후보 8/8 성공, 모두 row 반환 |
| 확인 metadata | analyst·추천의견과 추정연도 `E` label |
| 한계 | 공식 field mapping이 `DATA1`~`DATA5`로 남아 metric·unit·revision 의미 불명확 |
| 요구 연결 | 국내 consensus·forward 후보 |
| 현재 상태 | `official-confirmed`, `live-verified`, semantic contract는 `gap` |

최소 3개 종목·3개 metric을 독립 자료와 대조하기 전에는 canonical consensus로 선정하지 않는다. SEC와
OpenDART actuals에서 LLM이 만든 전망을 이 원천의 consensus와 섞지 않는다.

승인된 consensus 계약은 provider·as-of·회계기간·metric·unit·analyst count와 mean·median·high·low를
요구한다. 실적 surprise에는 발표 직전 snapshot만 사용하고, 발표 뒤 NTM revision은 별도 시계열로
보존한다. KIS semantic 검증 또는 licensed provider가 확보되지 않은 시장은 `source_gap`으로 유지한다.

공식 근거:
[KIS 공식 종목추정실적 예제](https://github.com/koreainvestment/open-trading-api/blob/main/examples_llm/domestic_stock/estimate_perform/estimate_perform.py)

### SRC-KIS-DIVIDEND-RIGHTS: 국내·미국 배당과 권리

| Dataset | Endpoint / TR ID | live 결과 | 적합성 |
| --- | --- | --- | --- |
| 국내 KSD 배당일정 | `/uapi/domestic-stock/v1/ksdinfo/dividend` / `HHKDB669102C0` | 후보 8개 중 5개 row | 선언·기준일·지급일·주당배당 일정 |
| 국내 계좌권리 | `/uapi/domestic-stock/v1/trading/period-rights` / `CTRGA011R` | RIA·ISA·일반·연금저축 row, IRP 0 row | entitled·배정·세금 후보, IRP gap |
| 미국 ICE 권리종합 | `/uapi/overseas-price/v1/quotations/rights-by-ice` / `HHDFS78330900` | 미국 직접보유 4/4 row | 공시·배당락·기준·지급일 일정 |
| 해외 기간별권리 | `/uapi/overseas-price/v1/quotations/period-rights` / `CTRGT011R` | 후보 13개 중 4개 row | 주당 외화배당·확정여부, actual receipt 아님 |

국내 계좌권리에는 최종배정액·세금 field가 있었지만 IRP에는 row가 없었다. 해외 권리 API는 계좌별 실제
입금액·원천징수세 identity를 제공하지 않는다. 따라서 선언·예상·권리·실수령을 별도 상태로 보존하고,
실수령 원천이 없는 해외/IRP는 statement 또는 manual provenance가 필요하다.

공식 근거:
[KIS 공식 국내 배당일정 예제](https://github.com/koreainvestment/open-trading-api/blob/main/examples_llm/domestic_stock/ksdinfo_dividend/ksdinfo_dividend.py),
[KIS 공식 국내 계좌권리 예제](https://github.com/koreainvestment/open-trading-api/blob/main/examples_llm/domestic_stock/period_rights/period_rights.py),
[KIS 공식 미국 ICE 권리 예제](https://github.com/koreainvestment/open-trading-api/blob/main/examples_llm/overseas_stock/rights_by_ice/rights_by_ice.py)

### SRC-MACRO-OFFICIAL: 매크로·VIX 시계열

| Provider | Dataset | 계약과 한계 | 상태 |
| --- | --- | --- | --- |
| 한국은행 | ECOS Open API | 한국 금리·환율·물가·실물지표; series metadata와 관측시점 보존 | `official-confirmed` |
| Federal Reserve Bank of St. Louis | FRED/ALFRED API | series observation·release·vintage; 원 제공기관과 이용조건도 보존 | `official-confirmed` |
| Cboe | VIX Index | 향후 약 30일 S&P 500 옵션 내재변동성; 개별종목 방향·실현변동성 아님 | `official-confirmed` |

뉴스 전문을 매크로 사건의 canonical source로 자동 채택하지 않는다. 정책·통계 release와 기업 filing을
원천 사건으로 두고, 종목 영향은 direct·rule-based·analyst hypothesis·validated 상태를 구분한다.

초기 `macro_profile_v1`은 한국 기준금리·원/달러·물가·산업생산·수출과 미국 정책금리·국채 2년/10년·
장단기차·물가·고용·실질 GDP·광의 달러·WTI·VIX를 대상으로 승인했다. 정확한 series ID, release lag와
versioned 해석 규칙은 `governance/catalog/macro-series.toml`의 17개 approved-inactive 계약으로 확정했다.
ECOS exact identity는 `722Y001/D/0101000`, `731Y001/D/0000001`, `901Y009/M/0`, `901Y033/M/A00/2`,
`901Y118/M/T002`이고 미국·글로벌은 FRED/ALFRED `DFF`, `DGS2`, `DGS10`, `T10Y2Y`, `CPIAUCSL`,
`CPILFESL`, `UNRATE`, `PAYEMS`, `GDPC1`, `DTWEXBGS`, `DCOILWTICO`, `VIXCLS`다. VIX의 원소유자는
Cboe지만 초기 direct Cboe 수집은 dormant이고 호출 예산은 0이다.

공식 근거:
[한국은행 ECOS Open API](https://ecos.bok.or.kr/api/),
[FRED API](https://fred.stlouisfed.org/docs/api/fred/fred/),
[Cboe VIX](https://www.cboe.com/tradable-products/vix)

## 8. 다음 검증 게이트

패키지 C·D·E의 조사와 사용자 승인을 완료했다. 다음 단계는 비용 baseline을 포함한 구현계획을 작성하고
별도 승인을 받는 것이다.

1. 실제 GCP·MotherDuck·provider 월 비용을 측정하고 5만원 상한의 guardrail을 구현계획에 포함한다.
2. KRX PDF 자동 접근 방식과 이용조건은 Package B 구현계획의 acceptance gate로 유지한다.
3. 미국 consensus와 해외·IRP 실수령 배당 source gap은 승인된 provider/import가 생길 때까지 숨기지 않는다.
4. consensus point-in-time snapshot, macro series ID와 signal replay의 acceptance criteria를 구체화한다.

## 9. 조사 이력

| 날짜 | 상태 | 내용 |
| --- | --- | --- |
| 2026-08-27 | 패키지 C·D·E 승인 | point-in-time consensus와 revision 위험 신호, macro profile v1, Bollinger 보조 context, Remote MCP·저비용 batch 운영과 월 5만원 상한을 `selected` 요구로 확정함 |
| 2026-08-27 | 패키지 C 조사 완료 | OpenDART·SEC actual, KIS 국내 재무·추정, 국내·미국 배당·권리와 ECOS·FRED·Cboe 원천을 조사하고 live coverage와 source gap을 기록함 |
| 2026-08-27 | 패키지 B 승인 | dual price basis, SMA20·50·120·RSI14, 보유 에피소드 고점, KRX/운용사 PDF와 ETF 일별 3년 보존을 `selected`로 확정함 |
| 2026-08-27 | 패키지 B 승인 대기 | 국내·미국 일봉의 100행·조정 옵션, KIS ETF 구성 30행 제한, KRX/운용사 PDF와 지표 계약을 조사함 |
| 2026-08-27 | 패키지 A 승인 | IRP provisional·지연 reconciliation, 거래 3년 backfill, 해외 derived candidate link와 미지정 매도 FIFO inferred 배분을 `selected`로 확정함 |
| 2026-08-27 | 패키지 A 조사 | 공식 IRP 전용 현재 주문상태 endpoint를 확인하고 3년 backfill 복원성, 해외 주문·비용·환율 candidate link를 민감값 없이 측정함 |
| 2026-08-27 | `selected` | v1 purchase lot을 총체결수량이 0보다 큰 매수 주문 1건 단위로 승인함. fill grain은 신뢰 가능한 원천 확보 후 확장함 |
| 2026-08-27 | read-only live 검증 | 국내 5개 계좌 유형의 최근·이전 구간, 해외 주문체결 pagination, 해외 일별거래내역 field shape를 민감값 없이 확인함. 개별 fill identity 부재와 IRP 최근구간 gap을 기록함 |
| 2026-08-27 | 1차 조사 | 국내·해외 주문체결 및 해외 일별거래내역을 lot/thread 원천 후보로 대조하고 현재 coverage gap을 기록함 |
