# 검토 패키지 C — 실적·가치·배당·매크로

> 상태: 조사 완료, 통합 승인 대기
> 기준일: 2026-08-27
> 범위: 요구사항 분석, 공식 원천 조사와 read-only source 검증
> 비범위: API key 발급, schema, 수집 코드, backfill, DB 적재, 배포

## 1. 한눈에 보는 권고안

| ID | 승인할 권고 | 핵심 이유 |
| --- | --- | --- |
| C-1 | 국내 실제 실적·공시는 OpenDART, 미국은 SEC EDGAR를 canonical source로 사용 | 공시 원문과 XBRL 사실을 재현할 수 있고 KIS 재무 coverage만으로는 부족함 |
| C-2 | forward 전망은 `consensus`, `user_scenario`, `model_scenario`를 분리하고 미국 consensus gap을 숨기지 않음 | 공시기관은 미래 consensus를 제공하지 않고 KIS 추정실적의 field 의미도 불완전함 |
| C-3 | valuation band와 trade thread의 risk/reward band를 서로 다른 데이터 제품으로 관리 | 기업가치 범위와 진입가·목표가·손절가의 손익비는 같은 개념이 아님 |
| C-4 | 배당을 `declared → entitled → received` 세 상태로 보존하고 실수령이 확인되지 않으면 예상액으로 표시 | 일정·주당배당과 계좌 입금은 원천과 확정 시점이 다름 |
| C-5 | 매크로 수치는 BOK ECOS, FRED/ALFRED, Cboe VIX를 사용하고 사건 연결은 관측·규칙·가설을 구분 | 재현 가능한 공식 시계열과 LLM의 해석을 섞지 않아야 함 |
| C-6 | 리서치 보고서는 라이선스가 확인될 때까지 원문 수집 대신 metadata·link·허용된 파생 사실만 저장 | 유료·저작권 자료의 무단 복제와 출처 없는 전망을 피함 |

## 2. 확인된 현황

### 2.1 국내 실제 실적과 추정실적

KIS 공식 예제에는 손익계산서, 재무상태표, 재무비율, 성장성·수익성·안정성 비율과 종목추정실적 API가
있다. 최신 canonical holding snapshot에서 식별된 국내 6자리 후보 8개를 민감값 없이 시험한 결과는
다음과 같다. 이 snapshot은 일부 계좌 누락 가능성이 있으므로 보유범위의 완전성 근거로 사용하지 않는다.

| 원천 | 시험 결과 | 판정 |
| --- | --- | --- |
| KIS 재무비율 `FHKST66430300` | 8/8 호출 성공, 3/8에서 row 반환 | 국내 개별주식 fast path·cross-check 후보. ETF를 포함한 전체 보유상품 원천은 아님 |
| KIS 종목추정실적 `HHKST668300C0` | 8/8 호출 성공, 모두 row 반환 | 후보 원천이지만 공식 mapping이 `DATA1`~`DATA5` 수준이라 semantic 검증 전 canonical 사용 금지 |

종목추정실적의 실제 응답에는 analyst·추천의견과 `2026.12E`, `2027.12E` 같은 추정연도 label이 있었지만,
공식 예제의 field 설명만으로 각 `DATA` 값의 회계항목·단위·수정 의미를 확정할 수 없었다. 따라서 응답이
있다는 사실과 12개월 forward 계산에 쓸 수 있다는 판단은 분리한다.

OpenDART는 공시목록, 공시 원문 XML, 회사 고유번호, 정기보고서 전체 재무제표와 배당 관련 정기보고서
항목을 제공한다. 종목코드와 DART `corp_code`를 공식 목록으로 연결하고 접수번호·보고서·연결/별도·
회계기간·수정공시를 natural identity에 포함할 수 있다.

### 2.2 미국 실제 실적과 forward gap

SEC `data.sec.gov`는 인증키 없이 회사 제출 이력과 XBRL `companyfacts`를 JSON으로 제공한다. 제출 자료는
실시간에 가깝게 갱신되며 nightly bulk archive도 제공된다. ticker와 CIK 연결 파일은 검색 보조자료이고
SEC도 정확성과 범위를 보장하지 않으므로 filing의 CIK를 최종 identity로 사용해야 한다.

SEC 공시와 XBRL은 실제 실적의 canonical source가 될 수 있지만 analyst consensus나 목표주가를 제공하지
않는다. 현재 KIS 공식 catalog에서도 미국 종목의 공시 기반 재무제표·forward consensus를 국내
종목추정실적과 같은 계약으로 확인하지 못했다. 따라서 미국 12개월 consensus는 현재 `source_gap`이다.

### 2.3 배당 원천

| 요구 상태 | 국내 | 미국 | 확인 결과 |
| --- | --- | --- | --- |
| 선언·예정 | OpenDART 배당사항, KIS 예탁원 배당일정 | KIS ICE 권리종합·기간별권리 | 국내 후보 8개 중 5개, 미국 직접보유 4개 모두 일정 row 확인 |
| 계좌 권리 | KIS 기간별계좌권리현황 | KIS 기간별권리는 계좌가 아닌 종목·기간 성격 | 국내 RIA·ISA·일반·연금저축에서 row 확인, IRP는 0 row |
| 실제 수령액·세금 | 국내 계좌권리의 최종배정액·세금 field를 후보로 검증 가능 | 현재 확인한 API에는 계좌별 실제 입금 identity가 없음 | 해외와 IRP는 statement/import 또는 추가 원천이 필요 |

미국 ICE 권리종합은 공시일, 배당락일, 기준일과 지급일을 반환했다. 기간별권리는 주당 외화배당과 확정
여부를 제공하지만 실제 계좌 입금액·원천징수세를 증명하지 않는다. `주당배당 × 보유수량`을 실수령액으로
기록해서는 안 된다.

### 2.4 매크로와 사건

- 한국 시계열: 한국은행 ECOS Open API를 우선 사용한다.
- 미국·글로벌 시계열: FRED API와 필요할 때 ALFRED vintage를 사용한다. FRED가 다른 기관의 값을
  재배포하는 series는 source와 이용조건을 series metadata에 함께 보존한다.
- 미국 주식시장 변동성: Cboe VIX를 공식 지수 source로 사용한다. VIX는 향후 약 30일의 옵션 내재변동성
  기대를 나타내며 개별 종목의 실제 변동성이나 방향 예측으로 표시하지 않는다.
- 기업 사건: 국내는 OpenDART, 미국은 SEC filing을 일급 사건으로 둔다.
- 뉴스·리서치 해석: 라이선스가 확인된 원천이 없으면 LLM이 만든 요약을 원천 사실로 승격하지 않는다.

## 3. 권고 계약

### C-1. 실제 실적·공시 원장

1. 국내 canonical filing·actual fundamentals는 OpenDART를 사용한다. KIS 재무 endpoint는 빠른 조회와
   cross-check에 사용한다.
2. 미국 canonical filing·actual fundamentals는 SEC submissions와 `companyfacts`를 사용한다.
3. 회사 identity는 국내 `stock_code ↔ corp_code`, 미국 `ticker ↔ CIK`를 effective-date와 함께 관리한다.
4. 정정·수정공시는 기존 row를 덮어쓰지 않고 accession/접수번호와 filed-at 기준으로 revision을 보존한다.
5. 최초 적재는 현재 보유기업의 최근 5개 연도와 최근 8개 분기를 목표로 한다. 이후 새 filing을 증분
   수집한다. 가격·거래의 3년 backfill과 다른 기간인 이유는 경기·이익 cycle 비교에 더 긴 실제 실적이
   필요하고 typed row 용량은 작기 때문이다.
6. 원문 binary/XML은 content hash와 source URL을 가진 object storage 대상으로 두고 MotherDuck에는
   metadata와 typed facts를 둔다.

### C-2. 12개월 forward와 시나리오

1. `consensus_forward`, `user_scenario`, `model_scenario`를 source type으로 분리한다.
2. consensus에는 provider, as-of, fiscal period, analyst count·coverage, metric, unit와 revision identity가
   있어야 한다. 이 조건을 만족하지 못한 값은 canonical consensus가 아니다.
3. KIS 국내 종목추정실적은 semantic mapping을 최소 3개 종목·3개 지표에서 독립 자료와 대조한 후에만
   `experimental_consensus`로 채택한다.
4. 미국 consensus는 승인된 licensed provider가 생길 때까지 `source_gap`으로 표시한다. SEC 실제값에서
   LLM이 만든 추정을 consensus라고 부르지 않는다.
5. NTM은 결산월이 다른 회사를 지원하도록 현재·다음 회계연도 추정치를 남은 기간으로 선형 가중하는
   versioned 계산을 기본으로 한다. 원천이 분기 추정을 제공하면 4개 forward quarter 합계를 우선한다.
6. 실적 발표·추정치 revision마다 forward snapshot을 새로 만들고 과거 as-of 결과를 재작성하지 않는다.

### C-3. Valuation band와 risk/reward band

- `valuation band`: 실제 또는 승인된 forward EPS/BPS/EBITDA와 역사적 multiple·시나리오를 사용해
  기업가치 범위를 계산한다. 사용한 metric, 기간, percentile, peer 또는 가정을 노출한다.
- `risk/reward band`: 현재가·trade thread의 목표가·손절가에서 예상 upside, downside와 reward/risk를
  계산한다. 목표·손절의 작성 주체와 revision을 보존한다.
- 두 band 모두 단일 `매수/매도` 정답으로 축약하지 않고 bear/base/bull 또는 저·기준·고 범위와 근거를
  제공한다.
- consensus가 없는 경우 valuation은 실제 실적·사용자 시나리오만으로 계산하고 coverage를 낮게 표시한다.

### C-4. 배당 원장

1. 배당 event는 `declared`, `entitled`, `received`, `reversed/corrected` 상태를 가진다.
2. 선언·일정은 국내 OpenDART/KSD와 미국 ICE 권리 원천에서 수집한다.
3. 계좌 권리는 종목·기준일·계좌·권리유형 grain으로 보존한다. IRP 무응답을 0원 수령으로 해석하지 않는다.
4. 실제 수령은 계좌·통화·지급일·gross·tax·net·source identity를 가진 현금흐름 event로만 확정한다.
5. 해외와 IRP는 실제 입금 원천을 확보할 때까지 statement/CSV 또는 사용자 확인 import 경로를 허용하되
   `manual` provenance로 보존한다.
6. 월별 배당은 received net과 gross를 각각 집계하고 선언·예상액과 reconciliation한다.

### C-5. 매크로·사건 context

초기 관리 series는 한국 기준금리·원/달러·물가·산업/수출, 미국 정책금리·2년/10년 국채금리·물가·고용,
VIX로 제한한다. 각 series는 provider series ID, frequency, unit, release/vintage, observed period와 fetched-at을
보존한다.

사건과 종목의 연결은 다음 근거를 구분한다.

- `direct`: 회사 공시가 해당 회사 또는 보유상품을 직접 지목
- `rule_based`: 산업·국가·통화·ETF look-through mapping 규칙으로 연결
- `analyst_hypothesis`: 사용자 또는 LLM이 제안한 영향 가설
- `validated`: 사후 검토에서 근거를 확인한 관계

사건 전후 수익률은 관찰된 동행성이고, 별도 검증 없이 인과관계로 표현하지 않는다.

### C-6. 시장 리포트와 저작권 경계

- 공개 공시 원문과 공식 통계는 원천 계약에 따라 보존한다.
- 증권사·유료 리서치는 명시적인 이용권한이 확인될 때까지 제목, 발행기관, analyst, 발행시각, URL,
  대상 종목, rating·target 같은 허용된 구조화 사실과 사용자 작성 메모만 저장한다.
- 유료 PDF 전문, 장문 본문 또는 출처가 불명확한 복제본을 데이터레이크에 자동 적재하지 않는다.
- 향후 provider를 고를 때 API 제공, 개인 사용권, 보존·재배포 허용범위, 과거 revision과 비용을 함께 승인한다.

## 4. 대안과 영향

| 선택 | 장점 | 단점 | 판정 |
| --- | --- | --- | --- |
| KIS 재무·추정만 사용 | 인증과 코드가 단순 | 실제 재무 coverage와 추정 field 의미가 불완전 | 비권고 |
| OpenDART/SEC actual + KIS 보조 | 공식 원문과 빠른 조회를 함께 사용 | identity·revision pipeline 필요 | **권고** |
| LLM 전망을 consensus로 저장 | 즉시 모든 종목 coverage | 출처와 재현성이 없음 | 금지 |
| 일정×수량을 실수령으로 계산 | 구현이 쉬움 | 세금·보유기준일·정정·계좌 차이를 오인 | 금지 |
| 뉴스 전문을 무차별 수집 | 사건 coverage가 넓음 | 라이선스·잡음·중복·용량 문제 | 비권고 |

## 5. 승인할 결정

| ID | 결정 | 승인 상태 |
| --- | --- | --- |
| C-1 | OpenDART·SEC actual fundamentals와 5년/8분기 최초 적재 | 대기 |
| C-2 | source-separated forward와 미국 consensus gap 유지 | 대기 |
| C-3 | valuation band와 risk/reward band 분리 | 대기 |
| C-4 | declared·entitled·received 배당 원장과 해외/IRP manual fallback | 대기 |
| C-5 | ECOS·FRED/ALFRED·Cboe 및 evidence-typed 사건 연결 | 대기 |
| C-6 | 리서치 metadata-first와 licensed-source gate | 대기 |

승인해도 구현은 시작하지 않는다. 승인 결과만 통합 요구사항의 다음 DEC 번호로 승격한다.

## 6. 공식 근거

- [OpenDART OpenAPI 소개](https://opendart.fss.or.kr/intro/main.do)
- [OpenDART 공시검색 개발가이드](https://opendart.fss.or.kr/guide/detail.do?apiGrpCd=DS001&apiId=2019001)
- [OpenDART 배당사항 개발가이드](https://opendart.fss.or.kr/guide/detail.do?apiGrpCd=DE002&apiId=AE00006)
- [SEC EDGAR data APIs](https://www.sec.gov/search-filings/edgar-application-programming-interfaces)
- [SEC EDGAR data access와 ticker/CIK 자료](https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data)
- [KIS 공식 Open Trading API 예제](https://github.com/koreainvestment/open-trading-api)
- [한국은행 ECOS Open API](https://ecos.bok.or.kr/api/)
- [FRED API](https://fred.stlouisfed.org/docs/api/fred/fred/)
- [Cboe VIX](https://www.cboe.com/tradable-products/vix)
