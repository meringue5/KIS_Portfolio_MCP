# 검토 패키지 B — 가격·추세·ETF 노출

> 상태: 승인 완료
> 기준일: 2026-08-27
> 범위: 요구사항 분석과 read-only source 검증
> 구현 상태: 미승인. 이 문서는 schema, 수집기, backfill, 배포 또는 운영 데이터 변경을 승인하지 않는다.

## 1. 승인 결과

2026-08-27 사용자가 B-1~B-5 권고안을 모두 승인했다. 각 항목은 통합 요구사항 문서의
DEC-015~DEC-019로 승격됐다.

1. 조정·비조정 가격을 어떻게 보존하고 어떤 가격을 분석 기준으로 사용할지
2. 20·50·120일 이동평균, 거래량 및 RSI 계산 계약
3. 보유기간 고점과 엄밀한 의미의 ATH를 어떻게 구분할지
4. ETF 구성종목의 canonical 원천, 갱신주기와 look-through 범위
5. 최근 3년 적재가 MotherDuck 용량 안에서 합리적인지

## 2. 확인된 현황

### 2.1 현재 보유 범위

2026-08-27 최신 canonical holding snapshot의 민감하지 않은 범위만 집계했다.

| 구분 | 서로 다른 보유상품 수 | 비고 |
| --- | ---: | --- |
| 국내 상장 주식 | 3 | KRX |
| 국내 상장 ETF | 14 | 동일 ETF의 복수 계좌 보유는 한 종목으로 합산 |
| 미국 상장 주식 | 4 | NASDAQ 직접 보유 |
| 미국 상장 ETF | 0 | 현재 보유에는 없음 |

국내 ETF 중 일부는 이름 기반으로 `overseas_indirect`로 분류돼 있지만 실제 KIS 구성종목 표본은 국내
주식, 국내 ETF, 채권 ETF 또는 ETN을 주로 포함했다. 따라서 상품명 heuristic만으로 경제적 해외노출을
확정하면 안 된다.

### 2.2 국내 일봉

| 항목 | 확인 결과 |
| --- | --- |
| API | 국내주식기간별시세(일/주/월/년) `[v1_국내주식-016]` |
| Endpoint / TR ID | `/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice` / `FHKST03010100` |
| 일봉 필드 | 거래일, OHLC, 거래량, 거래대금, 변경 여부, 분할비율, 재평가사유 |
| 1회 반환 | 최대 100행 |
| 조정 옵션 | 이 endpoint의 `FID_ORG_ADJ_PRC=0`은 수정주가, `1`은 원주가 |
| 3년 적재 | 약 8개 이하의 날짜 shard를 종목별로 호출해야 함 |

실제 3년 범위를 한 번 호출하면 최신 100행만 반환되고 별도 continuation header는 없었다. 현재 서비스는
`FID_ORG_ADJ_PRC=0`으로 수정주가를 요청하면서 `price_history.adjusted=FALSE`로 저장하므로 값의 의미와
metadata가 어긋날 수 있다. 또한 현재 PK `(symbol, exchange, date)`는 조정·비조정 가격을 동시에 보존할
수 없다.

### 2.3 미국 일봉

| 항목 | 확인 결과 |
| --- | --- |
| API | 해외주식 기간별시세 `[v1_해외주식-010]` |
| Endpoint / TR ID | `/uapi/overseas-price/v1/quotations/dailyprice` / `HHDFS76240000` |
| 일봉 필드 | 거래일, OHLC, 거래량, 거래대금, 호가·잔량 |
| 1회 반환 | 100행; 실제 응답 header `tr_cont=F` 확인 |
| 조정 옵션 | `MODP=0` 미반영, `1` 반영 |
| 3년 적재 | 공식 연속조회와 기준일 이동을 사용해 약 8 page 예상 |

주식분할이 있었던 미국 종목의 100거래일 구간을 익명 집계한 결과, `MODP=0`과 `1`은 100행 모두
종가가 달랐지만 거래량은 한 행도 달라지지 않았다. 따라서 KIS 수정주가 옵션이 가격을 보정한다고 해서
거래량까지 분할 조정됐다고 가정하면 안 된다.

### 2.4 현재 가격 저장 상태

read-only live inventory에서 `price_history`는 838행이었다. KRX 53행과 NAS 785행이 모두
`adjusted=FALSE`였고, 현재 `kis_portfolio` database 크기는 약 49 MiB였다. 이 수치는 조사 시점의
운영 상태이며 목표 수집 계약은 아니다.

### 2.5 ETF 구성종목

KIS의 국내 `ETF 구성종목시세`를 현재 보유한 국내 ETF 14종에 read-only로 호출했다.

| 항목 | 확인 결과 |
| --- | --- |
| Endpoint / TR ID | `/uapi/etfetn/v1/quotations/inquire-component-stock-price` / `FHKST121600C0` |
| 성공률 | 14/14 |
| API가 선언한 총 구성종목 | 642행 |
| 실제 반환 | 286행 |
| 30행 반환 ETF | 8종 |
| 선언 수가 반환 수보다 큰 ETF | 14종 모두 |
| continuation header | 확인되지 않음 |

KIS 응답은 현재 시세와 상위 구성종목 확인에는 유용하지만, 완전한 look-through 원장에는 부족하다.
해외간접 ETF 4종의 반환 구성종목 26행도 24행이 국내 6자리 코드였고 나머지 2행은 다른 상품 코드였다.
즉 해외 최종노출을 얻으려면 국내 재간접 ETF를 재귀적으로 펼치고 채권·ETN·파생·현금 잔여분을 별도로
보존해야 한다.

한국거래소는 ETF 납입자산구성내역(PDF, Portfolio Deposit File)을 거래소와 운용사 홈페이지에 매일
공시한다고 설명하며 KRX Data Marketplace에 `ETF > PDF(Portfolio Deposit File)` 데이터셋을 제공한다.
현재 보유 ETF 운용사인 TIMEFOLIO, KoAct, RISE, PLUS도 상품 페이지에서 구성종목 또는 Excel 다운로드를
제공한다. 다만 자동 수집 방식, 과거 날짜 coverage와 이용 조건은 구현 전에 별도 검증해야 한다.

## 3. 승인된 논리 계약

### B-1 / DEC-015. 가격 원장 — 수정주가를 분석 기준으로 하고 원주가도 잃지 않는다

- Bronze에는 vendor raw 응답, 요청한 조정 옵션, 요청 범위, page와 수집 시각을 보존한다.
- Silver 일봉은 `price_basis` 또는 이에 준하는 구분으로 `adjusted`와 `unadjusted`를 함께 표현할 수 있어야
  한다.
- 수익률, 이동평균, RSI, 고점·낙폭의 기본 입력은 **수정주가 OHLC**로 한다.
- 거래내역 reconciliation, 실제 체결가 대조와 원천 감사에는 원주가를 사용한다.
- 거래량과 거래대금은 vendor 관측값으로 보존한다. 분할 전후 거래량 비교는 corporate action 보정이
  없으면 품질 경고를 붙인다.
- 현재 `price_history`의 의미 불일치와 단일 price basis PK는 구현 단계의 migration 대상이다.

### B-2 / DEC-016. 추세·RSI·거래량 — 서로 다른 기간 개념을 섞지 않는다

- 추세의 기본 이동평균은 수정 종가의 `SMA20`, `SMA50`, `SMA120`으로 한다.
- v1 거래량 지표는 당일 원거래량, `SMA20(volume)` 및 `volume / SMA20(volume)`로 한다.
- 거래량 급증 판단 시 split·병합일과 그 직전 비교구간은 `corporate_action_affected` 품질 상태로 표시한다.
- RSI 기본값은 일봉 수정 종가와 Wilder smoothing을 사용하는 `RSI14`로 한다.
- `RSI20`은 비교·연구용으로 계산할 수 있지만 기본 경보 입력으로 사용하지 않는다.
- `RSI50`과 `RSI120`을 이동평균과 맞추기 위해 기본 생성하지 않는다. 긴 RSI는 전통적인 RSI의
  과매수·과매도 민감도를 크게 낮추며 50·120일 추세는 이동평균이 담당한다.
- 모든 지표는 계산 버전, 입력 price basis, 필요한 최소 관측 수와 계산 시각을 노출한다. 관측이 부족하면
  0이나 중립값으로 채우지 않고 `insufficient_history`로 둔다.

Wilder RSI14의 계약은 일별 종가 변화에서 상승분과 하락분을 분리하고, 최초 14개 구간 평균 이후
`(이전 평균 × 13 + 현재 값) / 14`로 갱신한 RS를 `100 - 100 / (1 + RS)`로 변환하는 방식이다.

### B-3 / DEC-017. 고점 — 보유기간 고점을 주 지표로 하고 ATH라는 이름을 엄격히 쓴다

- 사용자-facing 주 지표는 **보유 에피소드 고점**과 그 대비 낙폭이다.
- 보유 에피소드는 같은 계좌·종목의 수량이 0보다 커진 날 시작하고 0이 된 날 종료한다. 전량 매도 후
  재매수하면 새 에피소드로 시작한다.
- 포지션, purchase lot과 trade thread는 각자의 시작일부터 수정주가 일중 고가의 최고값을 별도로 가진다.
- 시작일이 `inferred_opening`이면 고점도 `partial_history`로 표시한다.
- 단기 맥락은 20·50·120거래일 rolling high와 대비 낙폭으로 함께 제공한다.
- 엄밀한 `all_time_high`는 상장 이후 전 기간을 완전하게 수집한 경우에만 사용한다. 승인된 3년 backfill의
  최고값을 ATH라고 부르지 않고 `available_history_high_3y`로 표시한다.
- 252거래일/52주 고점은 후속 연구 지표로 둘 수 있으나 v1 기본 경보 기준에는 넣지 않는다.

### B-4 / DEC-018. ETF look-through — KRX/운용사 PDF를 canonical로, KIS를 보조로 사용한다

- 국내 상장 ETF의 canonical 구성종목 원천은 KRX PDF 또는 동일한 운용사 공식 PDF로 한다.
- KIS 구성종목시세는 당일 빠른 확인과 상위 구성종목 cross-check에 사용하되 완전성 source로 사용하지
  않는다.
- 거래일마다 최신 공개 PDF를 한 번 수집하며 `effective_date`, `published_at` 또는 확인 가능한 기준일,
  `fetched_at`, source URL·hash를 보존한다. 10:00 평가 전 새 PDF가 없으면 직전본과 age를 명시한다.
- 구성 row는 종목뿐 아니라 현금, 채권, 선물, swap, ETN, 다른 ETF를 원래 자산유형으로 보존한다.
- nested ETF는 최대 3단계, cycle guard와 source-date 일치 규칙으로 펼친다. 펼칠 수 없는 비중은
  `unexpanded_residual`로 남긴다.
- ETF 임팩트는 `내 포트폴리오 내 ETF 비중 × ETF 구성비중`을 기본 1단계 노출로 계산하고, 재귀 결과는
  별도 지표 버전으로 구분한다.
- 총 비중, 선언된 구성종목 수, 파싱 행 수, 식별자 매핑률과 미분류 잔여비중을 품질 지표로 제공한다.
- 현재 직접 보유 미국 ETF는 없으므로 미국 운용사별 holdings adapter 구현은 보류한다. 향후 편입 즉시
  canonical source가 확인될 때까지 look-through를 `unsupported_source`로 표시한다.

### B-5 / DEC-019. 용량 — 3년 보존은 현재 범위에서 충분히 작다

현재 보유 ETF 14종의 KIS 선언 구성종목 642행을 기준으로 하면:

| 데이터 | 1년 예상 | 3년 예상 |
| --- | ---: | ---: |
| ETF 구성 row | 약 161,784행 (`642 × 252`) | 약 485,352행 |
| 현재 보유 21종 일봉 | 약 5,292행 | 약 15,876행 |

ETF row당 typed column과 lineage metadata를 200~500 byte로 넉넉히 가정해도 3년 parsed 구성원장은
약 0.10~0.25 GB 규모다. raw 문서와 index까지 포함해도 1 GB 안쪽을 목표로 관리할 수 있다. 조사 시점
MotherDuck database는 약 49 MiB이고 Lite plan의 공식 무료 storage grant는 10 GB이므로 현재 범위의
3년 적재는 용량상 충분하다.

원본 Excel/CSV/PDF binary를 매일 MotherDuck BLOB으로 중복 저장하지 않는다. 원본 파일은 압축 Parquet
또는 승인된 object/file backup에 두고 MotherDuck에는 source URL, hash, 기준일, 수집 이력과 정규화 row를
보존하는 방식을 패키지 E에서 확정한다.

## 4. 대안과 영향

| 선택 | 장점 | 단점 | 판정 |
| --- | --- | --- | --- |
| 원주가만 저장 | 체결가 대조가 단순 | 분할 시 수익률·추세·ATH 왜곡 | 비권고 |
| 수정주가만 저장 | 분석이 단순 | 원천 감사와 체결가 대조가 어려움 | 비권고 |
| 수정·원주가 dual basis | 분석과 감사 모두 가능 | logical key와 migration 필요 | **결정** |
| RSI 20·50·120 | 이동평균과 숫자가 같아 보임 | RSI 의미와 민감도 혼동 | 비권고 |
| RSI14 + SMA20·50·120 | 역할이 분명하고 재현 가능 | 지표 종류가 둘로 나뉨 | **결정** |
| 3년 최고를 ATH로 표시 | 구현이 쉬움 | 상장 이후 ATH로 오인 | 비권고 |
| 보유 에피소드 고점 중심 | 사용자 손익 맥락과 일치 | episode identity 필요 | **결정** |
| KIS ETF 구성만 사용 | 인증·호출 경로 재사용 | 30행 제한으로 불완전 | 비권고 |
| KRX/운용사 PDF + KIS 검증 | 전체 구성과 빠른 cross-check | 파일 adapter·라이선스 검토 필요 | **결정** |

## 5. 승인된 결정

아래 다섯 항목은 2026-08-27 한 묶음으로 승인됐다.

| ID | 승인된 결정 | 상태 |
| --- | --- | --- |
| B-1 / DEC-015 | 수정주가를 분석 기준으로 하고 원주가와 raw provenance를 병렬 보존 | 승인 완료 |
| B-2 / DEC-016 | SMA20·50·120, 거래량 20일 비율, Wilder RSI14를 v1 기본 지표 계약으로 사용 | 승인 완료 |
| B-3 / DEC-017 | 보유 에피소드 고점을 주 지표로 하고 3년 최고를 ATH라 부르지 않음 | 승인 완료 |
| B-4 / DEC-018 | KRX/운용사 PDF를 ETF canonical source로, KIS 상위 구성종목을 보조 검증으로 사용 | 승인 완료 |
| B-5 / DEC-019 | ETF 구성종목 일별 snapshot 3년 보존을 용량 기준선으로 채택 | 승인 완료 |

승인은 논리 계약만 확정한다. 실제 API 변경, schema migration, 3년 backfill, PDF 자동수집과 배포는
후속 구현 계획을 다시 승인받은 뒤 시작한다. 패키지 B는 닫고 다음 검토 패키지는 C
`실적·가치·배당·매크로`다.

## 6. 공식 근거

- [KIS 국내주식기간별시세 공식 예제](https://github.com/koreainvestment/open-trading-api/blob/main/examples_llm/domestic_stock/inquire_daily_itemchartprice/inquire_daily_itemchartprice.py)
- [KIS 해외주식 기간별시세 공식 예제](https://github.com/koreainvestment/open-trading-api/blob/main/examples_llm/overseas_stock/dailyprice/dailyprice.py)
- [KIS ETF 구성종목시세 공식 예제](https://github.com/koreainvestment/open-trading-api/blob/main/examples_user/etfetn/etfetn_functions.py)
- [KRX ETF 정보와 일별 PDF 설명](https://m.krx.co.kr/contents/06/0609/060901/JHPETP060901M01.jsp)
- [KRX Data Marketplace](https://data.krx.co.kr/contents/MDC/MAIN/main/index.cmd)
- [MotherDuck 공식 가격·용량](https://motherduck.com/product/pricing/)
