# Source Inventory and Collection Basket Review

> 상태: owner 승인 완료 — core·recommended approved, later·excluded proposed
>
> 기준일: 2026-08-28
>
> Work Item: WI-004
>
> 계약 SSOT: `governance/catalog/sources.toml`, `datasets.toml`, `collections.toml`

## 1. 결론

사용자가 원천을 하나씩 고르는 방식으로 진행하지 않는다. 이미 승인된 요구사항을 기준으로 data architect가
공식성, point-in-time 재현성, 권리, 비용, coverage와 운영 난이도를 비교해 기본 선택안을 만들고, owner는
material trade-off를 승인한다.

이번 권고안은 다음과 같다.

1. **필수 core**는 기존 KIS 계좌·거래·가격 API와 사용자 매매일지로 구성한다.
2. **공시 actual**은 국내 OpenDART, 미국 SEC EDGAR를 canonical source로 사용한다.
3. **ETF look-through**는 보유 ETF의 공식 운용사 holdings 파일을 canonical source로 사용하고 KRX는 공식
   참조와 국내 coverage 보완에 사용한다. KIS ETF 구성종목 API는 완전성 기준이 아니라 cross-check다.
4. **macro_profile_v1**은 ECOS, FRED/ALFRED와 Cboe VIX의 작은 allowlist로 시작한다.
5. **국내 consensus**는 KIS 종목추정실적·투자의견을 먼저 표본검증하되 canonical로 승격하지 않는다.
   **미국 consensus**는 point-in-time 분포·analyst count·revision을 제공하는 licensed provider가 선정될
   때까지 명시적 gap으로 둔다.
6. 사용자가 정당하게 입수한 리서치 PDF는 별도 `restricted` 수동 반입 경로로 허용한다. 자동 탐색과
   scraping은 하지 않으며 private 원본·versioned 추출·lineage만 owner-authorized 분석에 사용한다.
7. 권리 미확인 리서치 원문, 포털 consensus와 일반 웹 scraping은 제외한다.

2026-08-28 owner 승인에 따라 필수 core와 권장 장바구니의 의존 계약을 `approved`로 승격했다. 아직
production producer/consumer가 없으므로 `active`는 아니다. provider 가입, API key 발급, production 호출,
live DDL, backfill, Scheduler, MotherDuck 운영 변경과 비용 발생은 승인하지 않는다.

## 2. 선택 원칙

원천 선택 순서는 다음과 같다.

```text
법적·경제적 사실의 공식 원천
→ 이미 승인된 계좌 전용 KIS 원천
→ 무료이며 재현 가능한 공공 API
→ 권리와 point-in-time 계약이 명확한 유료 원천
→ 권리 미확인 web scraping은 제외
```

`canonical`은 모든 도메인에서 무조건 우선한다는 뜻이 아니다. 계약에 적은 사실 종류에 한정한다. 예를 들어
KIS는 보유수량·체결·실수령 현금의 canonical source지만, 국내 공시 actual은 OpenDART가 canonical이고 ETF
전체 구성종목은 공식 issuer 파일이 canonical이다.

## 3. 요구사항에서 수집대상으로의 매핑

| 승인 요구 | 필요한 사실 | 선택 source | Dataset | 장바구니 |
| --- | --- | --- | --- | --- |
| 현재 보유 국내·미국 주식/ETF/REIT | 계좌잔고, 현금, 상품 identity | KIS; owner 보정 | portfolio-position-observation, instrument-master | required core |
| 매수 lot·thread·매매일지 | 주문체결, 현금거래, owner intent와 revision | KIS; portfolio owner | trade-event, cash-transaction-event, trade-journal | required core |
| 3년 가격·거래 복원 | adjusted/raw OHLCV, 거래량, 주문·거래 | KIS | price-bar-daily, trade-event | required core |
| 자산추세·기여도·경보 | 포지션, 가격, FX, 현금과 session status | governed core datasets | portfolio-daily-state | required core |
| ETF impact | 공식 일별 구성, 비중, non-equity와 nested ETF | 공식 KR/US issuer; KRX reference | etf-constituent-snapshot | recommended ETF |
| 5년·8분기 actual | filing, XBRL/DART facts와 correction | OpenDART; SEC EDGAR | filing-event, financial-fact | recommended fundamentals |
| 배당 이력 | declared, entitled, received, corrected | OpenDART/SEC; KIS; owner evidence | dividend-event | recommended fundamentals |
| macro context | 금리, curve, 물가, 유동성, 경기, FX, VIX와 vintage | ECOS; FRED/ALFRED; Cboe | macro-observation | recommended macro |
| forward 전망 위험 | point-in-time consensus 분포·인원·revision | KIS sample; licensed provider TBD | consensus-snapshot | later |
| 시장 리포트 | metadata, link, rights-approved facts | KIS sample; licensed provider TBD | research-reference | later |
| owner 보유 리포트 PDF | private original, hash, rights, page/section extraction | owner-provided manual upload | owner-research-document, owner-research-extraction | recommended manual |
| 권리 미확인 원문/포털 | 수집하지 않음 | unapproved web content | zero-row sentinel | excluded |

## 4. Source inventory와 판정

### 4.1 KIS Open API — 조건부 승인 권고

- 역할: 계좌잔고, 주문체결, 해외 일별거래, 예수금, 시세, 환율과 상품정보의 canonical source.
- 보조 역할: 국내 종목추정실적·투자의견과 ETF 구성종목 API는 coverage sample/cross-check.
- 접근: 기존 account-private app key/secret과 OAuth token. credential은 catalog에 기록하지 않는다.
- 운영 제약: 프로젝트의 보수 정책은 production KIS REST를 150ms 이상 간격으로 직렬화한다. remote와 Job은
  별 process이므로 향후 run overlap 방지 또는 distributed lease가 필요하다.
- 근거: [KIS 공식 API 목록](https://apiportal.koreainvestment.com/apiservice-summary)은 국내·해외 계좌,
  기간별 시세, ETF 구성종목, 재무, 배당일정, 종목추정실적과 투자의견 endpoint를 제공한다.
- gap: IRP 최근 거래 coverage, 일부 해외 cash/dividend code 의미와 adjusted-price response shape는 recorded
  fixture로 재검증해야 한다.

판정: `source.kis-open-api`, core에는 canonical, consensus와 ETF 구성에는 secondary 성격을 dataset 품질
규칙으로 제한한다.

### 4.2 Portfolio owner — 승인 권고

- 역할: 투자 이유, thread·lot 연결과 설명 가능한 수동 correction의 canonical source.
- 제한: LLM은 질문·초안·review queue를 만들 수 있지만 owner intent를 임의 생성하거나 KIS 사실을
  덮어쓰지 않는다.
- 비용·권리: 추가 비용 없음, account-private/confidential.

판정: `source.portfolio-owner`, journal과 explicit allocation에만 canonical.

### 4.3 OpenDART — 승인 권고

- 역할: 국내 filing, actual financial facts와 declared dividend 사실의 canonical source.
- 접근: 무료 API key, filing 검색·원문과 정형 재무/주요사항 API.
- 근거: [OpenDART 개발가이드](https://opendart.fss.or.kr/guide/main.do)와
  [OpenDART 이용약관](https://opendart.fss.or.kr/intro/terms.do).
- 운영 제약: endpoint별 quota와 오류코드를 존중하고 보유 issuer만 증분 조회한다. 수정공시는 과거본을
  덮어쓰지 않는다.
- gap: issuer identity와 DART corp code mapping, 연결/별도 재무제표 선택, taxonomy mapping을 bounded sample로
  확정해야 한다.

판정: `source.opendart`, canonical.

### 4.4 SEC EDGAR — 승인 권고

- 역할: 미국 filing, submissions와 XBRL company facts의 canonical source.
- 접근: API key 없이 `data.sec.gov` JSON과 filing archive를 사용한다.
- 근거: [SEC EDGAR API 문서](https://www.sec.gov/search-filings/edgar-application-programming-interfaces)는
  submissions와 company facts API를 설명한다. [SEC developer resources](https://www.sec.gov/about/developer-resources)의
  fair-access 정책을 적용한다.
- 운영 제약: 전체 최대 10 requests/second 아래에서 client identity, caching, bounded concurrency와 backoff를
  사용한다. 이 프로젝트는 보유 issuer의 daily incremental 요청으로 훨씬 낮게 운용한다.
- gap: ticker/CIK history, ADR·foreign private issuer와 non-US GAAP/XBRL taxonomy mapping을 sample로 확인한다.

판정: `source.sec-edgar`, canonical.

### 4.5 KRX와 ETF issuer — 계약 승인, activation 전 terms review 권고

- KRX 역할: exchange reference, 시장일과 국내 ETF 공식 자료 후보. Open API는 로그인, 인증키 신청,
  개별 API 이용신청과 승인 절차가 있다.
- 근거: [KRX Open API 이용 절차](https://openapi.krx.co.kr/contents/OPP/INFO/OPPINFO003.jsp).
- 국내 ETF 역할: 보유 ETF 운용사의 공식 PDF/CSV/XLS를 전체 구성의 canonical source로 한다. 예를 들어
  [삼성자산운용 KODEX 상품 페이지](https://m.samsungfund.com/etf/product/view.do?id=2ETF52)는 구성종목과
  전체 다운로드 표면을 제공한다.
- 미국 ETF 역할: 실제 보유 issuer만 allowlist한다. 공식 상품 페이지가 제공하는 holdings download를
  사용한다. 예: [iShares IVV](https://www.ishares.com/us/products/239726/ishares-core-sp-500-etfIVV),
  [State Street SPY](https://www.ssga.com/us/en/intermediary/etfs/state-street-spdr-sp-500-etf-trust-spy),
  [Vanguard VEA](https://investor.vanguard.com/investment-products/etfs/profile/vea).
- 운영 제약: 공개 다운로드가 자동수집·장기보존·재배포 권한을 자동 의미하지 않는다. activation 전에
  issuer별 terms, robots/technical policy, 허용 보존 범위와 attribution을 기록한다.
- gap: 3년 historical constituent 파일은 issuer가 제공하지 않을 수 있다. 없는 과거를 현재 구성으로
  재구성하지 않고 `unavailable_backfill`로 기록한다.

판정: KRX는 `reference`, allowlisted official issuer files는 해당 ETF 구성의 `canonical`. KIS ETF 구성은
cross-check에만 사용한다.

### 4.6 U.S. exchange calendars — 승인 권고

미국 시장일과 조기종료는 [NYSE Holidays & Trading Hours](https://www.nyse.com/markets/hours-calendars)와
[Nasdaq Trading Calendar](https://nasdaqtrader.com/Trader.aspx?id=Calendar)를 공식 교차참조한다. 이는
`source.us-exchange-calendars`로 등록하고 연 단위 또는 변경 발생 시에만 갱신한다. 두 source가 다르면
자동으로 어느 한쪽을 선택하지 않고 calendar quality exception으로 격리한다.

### 4.7 ECOS — 승인 권고

- 역할: 한국 기준금리, 물가, 통화·유동성, 실물활동과 USD/KRW 맥락의 canonical source.
- 접근: 무료 ECOS API key와 allowlisted series.
- 근거: [한국은행 ECOS 소개](https://www.bok.or.kr/portal/bbs/B0000522/view.do?menuNo=201692&nttId=10070977)와
  [ECOS Open API](https://ecos.bok.or.kr/api/).
- 운영 제약: series의 월·분기·일 발표주기를 보존하며 매일 값이 바뀐 것처럼 생성하지 않는다.
- gap: exact 통계표·항목 코드는 implementation sampling에서 official metadata와 함께 고정한다.

판정: `source.bok-ecos`, allowlisted Korean macro series에 canonical.

### 4.8 FRED/ALFRED — 계약 승인, series별 rights review 권고

- 역할: 미국 rates, yield curve, inflation, liquidity와 activity 관측, ALFRED vintage의 point-in-time 원천.
- 접근: 무료 API key. [FRED API overview](https://fred.stlouisfed.org/docs/api/fred/overview.html)와
  [ALFRED vintage dates API](https://fred.stlouisfed.org/docs/api/fred/series_vintagedates.html)를 사용한다.
- 권리 제약: [FRED API Terms](https://fred.stlouisfed.org/docs/api/terms_of_use.html)에 따라 FRED에 있다는
  사실만으로 모든 제3자 series의 재사용 권리를 가정하지 않는다. series allowlist마다 source owner와
  license note를 기록한다.
- gap: 빈티지가 없는 series를 point-in-time 복원 가능하다고 표시하지 않는다.

판정: `source.fred-alfred`, 승인된 series에 canonical, license class는 보수적으로 `restricted`.

### 4.9 Cboe VIX — 계약 승인, usage review 권고

- 역할: daily VIX close의 canonical source.
- 근거: [Cboe VIX Historical Data](https://www.cboe.com/tradable_products/vix/vix_historical_data)는
  1990년 이후 daily history를 제공하고 daily update한다고 설명한다.
- 범위: v1은 무료 daily index history만 사용한다. 유료 DataShop의 VIX futures/options dataset은 범위 밖이다.
- 운영 제약: attribution과 usage terms를 activation 전에 기록하고 하루 한 번 이하로 수집한다.

판정: `source.cboe-vix`, daily VIX에 canonical, license class는 보수적으로 `restricted`.

### 4.10 Consensus와 research — 후순위 유지 권고

- KIS 공식 catalog에는 국내 종목추정실적과 투자의견 endpoint가 있으므로 무료 후보로 표본검증한다.
- 그러나 point-in-time 분포, analyst count, 과거 revision과 coverage가 확인되기 전 canonical consensus로
  선언하지 않는다.
- 미국 consensus는 SEC filing 같은 공식 무료 대체재가 아니다. provider 이름, historical snapshot 권리,
  export/backup 제한과 비용이 확정될 때까지 `source.consensus-provider-tbd`로 남긴다.
- report full text는 이용권한 전에는 수집하지 않는다. metadata, link와 명시적으로 허용된 구조화 사실만
  `dataset.research-reference` 후보가 된다.

판정: `later`. 이번 승인 묶음에는 provider 계약이나 비용 지출을 포함하지 않는다.

### 4.11 Owner-provided research PDF — 수동 반입 승인

- 역할: 사용자가 정당하게 입수하고 개인 분석 권한을 확인한 PDF의 provenance anchor와 분석 입력.
- 접근: owner-authenticated 단건 수동 반입만 허용한다. Scheduler, 폴더 자동탐색, web crawling과 bulk
  import는 허용하지 않는다.
- 보존: SHA-256 content-addressed private original과 문서 metadata를 Bronze에, extractor/version/page 또는
  section lineage가 있는 추출 결과를 Silver에 append-only로 보존한다.
- 제한: 원문·추출물은 `restricted`이며 외부 재배포, 공개 MCP 응답과 Telegram 원문 전송을 금지한다.
  DRM 또는 이용조건이 처리·보존을 금지하면 반입을 거부하거나 metadata만 남긴다.

`restricted`는 유료라는 뜻이 아니다. 이는 이용조건·저작권·재배포·처리 범위를 통제하는 legal/use
분류이며, 비용은 별도 `cost_class`와 월비용 gate가 판단한다.

판정: `source.owner-provided-research-document`, `dataset.owner-research-document`,
`dataset.owner-research-extraction`과 `collection.owner-research-pdf-v1`을 `approved`로 등록한다.

## 5. 실제 수집 장바구니

### Required — `collection.owned-portfolio-core-v1`

지금 제품이 존재하려면 필요한 최소 범위다.

- 현재 보유상품과 계좌별 position/cash observation
- 국내·IRP·해외 주문체결과 cash transaction event
- 보유상품 instrument identity와 자산유형
- adjusted/raw daily OHLCV, FX와 market calendar
- owner-authored journal/thread/lot revision
- quality-gated daily portfolio state

초도 적재는 가격·거래에 최근 3년을 목표로 하되, API가 제공하지 않는 과거를 현재 평단가나 현재 구성으로
꾸며내지 않는다. KR 10:00/14:30/16:00과 미국 장 마감 후 한국 오전 요약 요구를 platform Scheduler가
소유하며 LLM 예약 작업은 allowlisted 보조 trigger다.

### Recommended — `collection.etf-lookthrough-v1`

- 현재 보유 ETF만 대상으로 한다.
- 거래일별 공식 issuer composition file을 한 번 수집한다.
- source date, URL, hash, 비중·수량·통화와 원래 instrument type을 보존한다.
- nested ETF는 3단계/cycle guard, 미해결 비중은 residual로 공개한다.
- official historical files가 없으면 activation 이후부터 축적하며 3년을 가짜로 재구성하지 않는다.

### Recommended — `collection.fundamentals-dividends-v1`

- 보유 issuer의 5년·8분기 OpenDART/SEC actual.
- filing metadata, 허용된 원문 object reference, source taxonomy와 normalized mapping.
- declared/entitled/received/corrected dividend ledger와 KIS cash reconciliation.
- research full text와 consensus는 이 collection에 넣지 않는다.

### Recommended — `collection.macro-profile-v1`

초기 개념 allowlist는 다음처럼 작게 시작한다. exact source series ID, 단위, 변환식과 vintage 가능 여부는
metric contract에서 sample response와 함께 확정한다.

| 축 | 초기 개념 |
| --- | --- |
| 정책금리 | 한국 기준금리, 미국 effective federal funds rate |
| 금리곡선 | 미국 2년·10년 국채금리와 10Y-2Y spread |
| 물가 | 한국 CPI, 미국 CPI와 YoY 변화 |
| 유동성 | 한국 M2, 미국 M2 |
| 경기 | 한국 산업활동 대표지표, 미국 unemployment/industrial activity 대표지표 |
| 환율 | USD/KRW 공식 관측 |
| 위험선호 | Cboe VIX daily close |

이 profile은 “많이 모으기”가 목적이 아니다. 보유종목 impact와 regime 해석에 실제로 쓰이는 series만
versioned allowlist로 추가한다.

### Recommended manual — `collection.owner-research-pdf-v1`

- owner가 선택한 PDF만 단건 반입한다.
- PDF signature, byte-size limit, SHA-256와 권리 assertion을 통과해야 한다.
- original은 private object, extraction은 versioned result로 분리하고 page/section lineage를 남긴다.
- full text 재배포, Telegram 전송, 무인 재수집과 권리 미확인 파일 처리를 금지한다.

### Later — `collection.consensus-research-later`

- KIS 국내 추정실적·투자의견 recorded sample
- point-in-time coverage 검증
- KIS 국내 sample은 bounded source-sampling Work Item에서 즉시 수행한다.
- core actual·배당·macro가 구현되고 KIS sample이 knowledge time, coverage, analyst count와 revision 요구를
  충족할 때 국내 production 채택을 검토한다.
- 미국 licensed provider 비교는 DEC-032 실적·forward 위험신호 구현 직전에 시작한다.
- provider는 point-in-time history, 분포/dispersion, analyst count, revision, 내부 저장·분석 권리와
  정상·backfill·장애월 비용이 확인돼야 진입할 수 있다.
- provider 계약 전 수집, backfill, schema와 경보 사용 금지

### Excluded — `collection.unlicensed-market-content-excluded`

- unnamed portal scraping
- paywall 또는 저작권 있는 analyst report full text
- knowledge time이 없는 현재 consensus 페이지로 과거 consensus 재구성
- source URL·권리·비용이 없는 LLM 생성 수치

## 6. Dataset contract 요약

이번 패키지는 19개 logical dataset을 등록한다.

| Layer | Dataset | 핵심 grain/역할 |
| --- | --- | --- |
| Bronze | portfolio-position-observation | KIS fetch별 계좌·보유·현금 관측 |
| Bronze | filing-event | filing ID와 document version |
| Silver | trade-event | 체결 주문 사건; fill을 추정하지 않음 |
| Silver | cash-transaction-event | 현금·비용·환전·배당 receipt 사건 |
| Silver | instrument-master | effective interval별 canonical instrument identity |
| Silver | price-bar-daily | instrument/session/price basis별 OHLCV |
| Silver | fx-rate-daily | currency pair/date/rate type |
| Control | market-calendar | market/date와 session timestamps |
| Silver | trade-journal | journal ID/revision별 owner intent |
| Silver | etf-constituent-snapshot | ETF/source date/file hash/constituent row |
| Silver | financial-fact | issuer/filing/concept/period/dimension |
| Silver | consensus-snapshot | issuer/forecast/metric/provider/knowledge_at |
| Silver | dividend-event | instrument/account/state/date/source fact |
| Silver | macro-observation | series/period/vintage/revision |
| Silver | research-reference | provider record와 published revision |
| Bronze | owner-research-document | SHA-256별 private immutable PDF와 권리 metadata |
| Silver | owner-research-extraction | 문서/extractor/version/page·section별 추출과 lineage |
| Gold | portfolio-daily-state | date/slot/account/instrument/aggregate level |
| Control sentinel | unlicensed-market-content | zero rows; prohibited boundary |

물리 table 이름, migration, pipeline ID와 column-level schema는 아직 승인하지 않는다. 다음 implementation
design은 이 logical grain, natural key, time semantics, quality와 sensitivity를 좁힐 수는 있어도 조용히
넓히거나 의미를 바꿀 수 없다.

## 7. 비용·용량 검토

- 이번 selected source는 KIS의 기존 계정과 무료 OpenDART, SEC, ECOS, FRED/ALFRED, Cboe daily file,
  공식 issuer download를 사용하므로 **신규 provider 정액비용은 0원**이다.
- 비용을 키우는 요인은 API fee보다 3년 backfill의 request 횟수, filing/ETF 원문 object storage, MotherDuck
  typed rows와 Cloud Run Job 실행시간이다.
- 수집 범위를 전체 시장이 아니라 **현재 보유 instrument와 그 issuer/ETF constituent**로 제한하고,
  conditional download, content hash와 source publication cadence를 적용하므로 정상월은 기존 월 50,000원
  상한보다 충분히 작아야 한다.
- 다만 이는 architecture estimate다. activation 전에 각 collection은 instrument count, 3년 row/file 수,
  compressed bytes, API calls, Job minutes와 MotherDuck scan bytes를 측정하는 bounded rehearsal을 거친다.
- consensus subscription은 이번 비용 계산에서 0원인 것이 아니라 **도입하지 않았기 때문에 0원**이다.
  향후 제안은 normal/backfill/failure month 비용을 모두 제시하고 전체 상한 안에서 승인받아야 한다.

## 8. 알려진 gap과 다음 gate

| Gap | 현재 처리 | activation 전 증거 |
| --- | --- | --- |
| KIS 국내 consensus의 point-in-time field/역사 깊이 | later, secondary candidate | 보유종목 소표본 response fixture와 coverage report |
| 미국 consensus provider | 명시적 TBD | provider 비교, rights, PIT history, 정상/초도/장애월 비용 |
| ETF issuer별 자동수집 권리·format | restricted proposed | 현재 보유 issuer allowlist, terms review, parser fixture |
| ETF 3년 구성 history | 제공되는 범위만 | 날짜별 official archive inventory; 없는 기간은 gap |
| FRED 제3자 series 권리 | restricted allowlist | series owner/license note |
| U.S. market calendar parse·교차검증 | NYSE/Nasdaq 공식 source 선정 | holiday·early-close golden fixture와 source disagreement rule |
| DART/SEC taxonomy mapping | source actual 보존 우선 | representative KR/US issuer golden fixture |
| 원문 storage size | estimate만 존재 | bounded sample byte size와 3년 projection |
| owner PDF parser·권리 경계 | approved manual contract | PDF fixture, hash dedupe, DRM/rejection, page lineage와 restricted-output test |

다음 Work Item은 **bounded source sampling and contract hardening**과 승인 범위의 V2 local 구현을 함께
진행한다. source별 1~3개 보유상품, 짧은 기간과 비민감 fixture로 response shape, quota, rights,
row/file size와 quality rule을 검증한다. 그 결과가 승인 계약과 다르면 contract review로 되돌아온다.

## 9. Owner 승인 기록

2026-08-28 owner가 다음 권고를 모두 승인했다.

1. `required` core와 세 `recommended` basket을 source/dataset/collection **approved contract**로 승격한다.
   이 승격은 production key 발급·수집·backfill 승인이 아니다.
2. KRX/ETF issuer, FRED series와 Cboe는 공개 접근 가능하더라도 activation 전 terms review를 요구하는
   `restricted` 분류를 유지한다.
3. consensus/research는 `later`, unlicensed scraping은 `excluded`로 유지하고 지금 유료 provider를
   선택하거나 결제하지 않는다.
4. owner-provided PDF는 별도 restricted manual collection으로 승인하고 자동 web collection과 분리한다.
5. DEC-044 범위의 repository-local 구현·fixture·test·migration dry-run은 추가 Work Item별 질문 없이
   진행하되 production·외부·유료 gate는 유지한다.

manifest lifecycle과 decision evidence를 갱신하고 WI-004를 닫았다. consensus source/dataset/collection과
unlicensed sentinel은 activation 조건을 충족하지 않았으므로 `proposed` 상태를 유지한다.
