# WI-041 consensus and forward-outlook pre-research — 2026-09-01

> Work Item: `WI-041-S01`
> 범위: repository, KIS reference와 provider 공개 문서의 research-only 비교
> 변경 경계: provider 가입·구독·API 호출, credential 발급, contract activation, DB write, DDL, pipeline,
> public MCP와 deployment 없음

## 결론

WI-041의 제품 의도와 논리 dataset 초안은 존재하지만, 구현 가능한 point-in-time(PIT) 데이터 제품 계약은
아직 완성되지 않았다. 현재 어떤 source도 canonical consensus provider로 승인할 수 없다.

- KIS 국내 `estimate-perform`과 투자 의견 API는 bounded sample 후보이지만 공식 field가 `DATA1`~`DATA5`로
  남아 있어 metric·단위·revision 의미가 검증되지 않았다. analyst count, 분포/dispersion과 원천 knowledge
  time도 계약상 확인되지 않았다.
- 미국 후보 중 Alpha Vantage는 analyst count와 estimate revision history를 제공하고 무료 계정의 표준 한도도
  25 requests/day라서 첫 schema sample 후보로 가장 적합하다. 그러나 공개 문서만으로 historical PIT가
  “그 당시 알 수 있었던 값”인지, 원본 snapshot의 장기 내부 보존이 허용되는지 확정할 수 없다.
- EODHD는 개인적 저장·분석을 명시적으로 허용하고 trend/revision 필드를 제공하지만 Fundamentals 요금이
  월 USD 59.99이며, 구독 종료 후 1개월 안에 보유 사본을 삭제해야 한다. 현재 비용 상한과 영구 PIT replay
  요구 양쪽에 맞지 않는다.
- Finnhub는 analyst count·분포와 surprise endpoint를 문서화했지만 필요한 estimate endpoint는 premium이고,
  공개 문서에서 가격·장기 저장권·historical PIT lineage를 확인하지 못했다.
- Financial Modeling Prep(FMP)은 일부 요금제가 명목상 비용 범위에 들어올 수 있으나, 기본 약관은 사전
  서면 승인 없는 content 복사·다운로드와 third-party access를 제한한다. MotherDuck PIT 적재 권리를 별도로
  확인하기 전에는 후보에서 제외한다.
- 현재 `dataset.consensus-snapshot`은 `backup_policy = excluded`이다. 이는 provider 접근이 끝난 뒤에도 과거
  판단을 재현해야 하는 DEC-021/032와 충돌한다. 보존권이 확보되지 않으면 이 기능은 `unavailable`로 남겨야
  하며, 현재값으로 과거 consensus를 역산해서는 안 된다.
- consensus와 사용자/model scenario를 분리한다는 요구는 승인됐지만 scenario용 dataset 계약은 없다.
  consensus, company guidance와 scenario는 서로 다른 fact class와 lineage로 분리해야 한다.

따라서 이번 sub-item은 provider를 선정하지 않고, 다음 sampling과 contract-hardening gate를 구체화하는 것으로
닫는다. parent `WI-041`과 MS-003 상태는 `proposed` 그대로다.

## 현재 재사용 가능한 기반과 결손

| Area | Existing input | Gap before implementation |
| --- | --- | --- |
| requirement | DEC-021/022/032/041/043 | provider, PIT semantics, 권리와 비용 승인 없음 |
| collection | `collection.consensus-research-later` proposed | production schedule, call budget와 producer 없음 |
| source | `source.consensus-provider-tbd` proposed | provider identity, license, rate/SLO와 coverage 없음 |
| dataset | `dataset.consensus-snapshot` proposed | 필수 field, retained PIT backup와 physical object 없음 |
| research metadata | `dataset.research-reference` proposed | consensus provider의 구조화 estimate와 혼용하면 안 됨 |
| metric | 없음 | surprise, NTM, revision, dispersion의 versioned metric 계약 없음 |
| pipeline | 없음 | collection, normalization, event-window snapshot과 publish gate 없음 |
| KIS domestic | estimate/opinion reference API와 8/8 row 반환 선행 표본 | `DATA1`~`DATA5` 의미, analyst count/distribution/revision/knowledge time 미확정 |
| V2 design | `consensus_snapshot`, `guidance_event`, forward-outlook read model | DDL, repository, quality, lineage와 consumer DTO 미구현 |

논리 dataset의 현재 natural key인 issuer, forecast period, metric, provider, knowledge time은 출발점일 뿐이다.
최소한 fiscal period start/end, annual/quarterly horizon, estimate basis(GAAP/non-GAAP 등), currency와 unit,
estimate mean/median/high/low, analyst count와 sample definition, provider updated time, system observed/fetched time,
provider record/version, snapshot reason, rights class와 source observation을 계약해야 한다.

## Provider 공개 문서 비교

2026-09-01 현재의 공개 문서만 비교했다. 가격과 약관은 바뀔 수 있으며, 공개 페이지의 개인 사용 허용을
장기 보존 또는 LLM/MCP 사용 허가로 확대 해석하지 않는다.

| Candidate | Useful documented shape | Cost/call observation | Rights and PIT finding | Research disposition |
| --- | --- | --- | --- | --- |
| KIS domestic | 종목 추정실적과 투자 의견 | 기존 KIS 계약 범위의 bounded sample 후보 | semantic mapping과 analyst population/PIT 불명 | 국내 3 issuers x 3 metrics 표본 우선 |
| Alpha Vantage | annual/quarterly EPS·revenue estimates, analyst count, revision history | free standard limit 25 requests/day | personal research use는 허용되나 retained snapshot과 historical knowledge-time 권리 불명 | 미국 첫 no-cost schema sample 후보; 미승인 |
| EODHD | estimate avg/low/high, analyst count, 7/30/60/90-day trend와 revisions | Fundamentals USD 59.99/month, paid plans 100,000 calls/day | private storage/analysis 허용, subscription 종료 뒤 1개월 내 데이터 삭제 | 비용·retention gate 불합격 |
| Finnhub | recommendation counts, price-target distribution, estimate analyst count, surprise | estimate/target 기능 premium; 공개 가격 미확정 | historical PIT lineage와 저장권 미확정 | 비교 후보; activation 불가 |
| FMP | estimates, ratings, historical ratings, target consensus | Starter USD 22/month billed annually부터; endpoint entitlement 별도 확인 필요 | 기본 약관상 copy/download와 external access 제한이 warehouse 보존과 충돌 | 서면 허가 전 제외 |

공식 근거:

- [Alpha Vantage API documentation](https://www.alphavantage.co/documentation/),
  [pricing and free usage](https://www.alphavantage.co/premium/),
  [terms of service](https://www.alphavantage.co/terms_of_service/)
- [EODHD Fundamentals API](https://eodhd.com/financial-apis/stock-etfs-fundamental-data-feeds),
  [pricing](https://eodhd.com/pricing),
  [terms and storage/deletion conditions](https://eodhd.com/financial-apis/terms-conditions)
- [Finnhub API documentation](https://finnhub.io/docs/api/quote)
- [FMP pricing](https://site.financialmodelingprep.com/developer/docs/pricing),
  [terms of service](https://site.financialmodelingprep.com/terms-of-service)

## Point-in-time and no-leakage contract

`knowledge_at` 하나로 provider의 시점 의미와 우리 시스템의 관측 시점을 섞지 않는다.

1. `provider_effective_at`은 provider가 명시한 estimate/version 시각이며, 없으면 null이다.
2. `observed_at`은 우리 collector가 성공 응답을 받은 시각이다. provider 시각이 없을 때 우리가 주장할 수
   있는 가장 이른 knowledge time은 이것뿐이다.
3. `fetched_at`과 immutable source-observation hash를 보존해 replay lineage를 만든다.
4. “7/30/90일 전 대비”처럼 현재 응답에 포함된 trend field는 provider가 지금 제공한 비교값이다. 과거 날짜의
   독립 snapshot이나 그때 우리 시스템이 알았던 값으로 승격하지 않는다.
5. earnings history의 actual/estimate pair도 provider가 마지막 pre-release consensus였다고 보증하지 않으면
   unbiased backtest 입력으로 사용하지 않는다.
6. pre-release consensus는 공식 release 시각보다 앞선 마지막 eligible snapshot으로 고른다. release timezone,
   BMO/AMC/장중 여부 또는 수신 지연이 불명확하면 surprise signal을 fail closed한다.
7. post-release revision은 일별 snapshot 또는 명시된 +1/+7/+30/+90 day slots로 비교한다. 오늘 값으로 이전
   snapshot을 재구성하지 않는다.
8. NTM은 가능한 경우 다음 4개 분기를 사용한다. FY1/FY2 가중 보간은 분기 coverage가 없을 때의 별도
   versioned formula이며 fiscal calendar, weight와 missing input을 함께 남긴다.
9. 회사 guidance는 filing/earnings release에서 온 `guidance_event`이고 analyst consensus가 아니다.
   사용자/model scenario도 별도 dataset과 provenance를 가져야 한다.

## 비용과 호출 예산 경계

이전 held-scope 조사에서 직접 발행사는 국내 3개와 미국 4개였다. 이는 live inventory가 아니라 연구 기준선이며
구현 시작 시 다시 계산한다.

- Alpha Vantage 표본 가설은 7 issuers x 1 estimate request = 7 calls/day이다. 무료 25/day 안에서 schema와
  coverage를 볼 수 있으나 entitlement, 응답 크기, error call accounting을 실제 표본 전 확인해야 한다.
- 첫 production contract의 정상 budget은 최대 12 physical calls/day를 권고한다. retry도 동일 budget을
  소비하며 전 종목 polling보다 보유 direct issuer와 event window를 우선한다.
- historical PIT endpoint와 보존권이 확인되지 않으면 backfill budget은 0이다. 과거 current-response를 반복
  호출하는 행위는 backfill이 아니다.
- 유료 후보는 provider 요금만 보지 않고 기존 GCP·MotherDuck·외환/세금까지 포함한 정상월, backfill월과
  장애월 총액을 DEC-041의 KRW 50,000 gate로 다시 계산한다.
- paid signup, credential 발급, sample API call과 데이터 적재는 별도 사용자 승인 전 수행하지 않는다.

## Contract-hardening and sampling gate

Formal WI-041 구현 전에 다음을 순서대로 통과해야 한다.

1. KIS 국내 sample을 3 issuers x 3 metrics 이상으로 고정하고 공식 field, unit, fiscal period, analyst count,
   distribution, revision과 knowledge-time 의미를 독립 자료와 대조한다.
2. 미국은 Alpha Vantage를 첫 no-cost schema sample로 검토하되, sample 전에 현재 free entitlement와 약관상
   private warehouse retention/LLM analysis를 확인한다. 불명확하면 data를 저장하지 않고 schema/coverage만
   기록하거나 provider에 서면 질의한다.
3. source contract에 coverage, allowed use, retention-after-termination, derived metric retention, credential,
   rate/call budget, SLO와 deletion obligation을 명시한다.
4. consensus dataset의 필수 field와 natural key를 보강하고 `backup_policy = excluded`를 권리와 replay 요구에
   맞게 결정한다. 보존할 수 없다면 해당 provider는 PIT signal source가 될 수 없다.
5. consensus, company guidance, owner scenario와 model scenario dataset을 분리하고 각각 provenance와
   consumer-visible label을 고정한다.
6. pre-release surprise, NTM level/revision, dispersion와 guidance delta metric contract를 version, unit,
   eligible-window, missing-data behavior와 함께 등록한다.
7. event-aligned collection/publish pipeline contract에 physical-call budget, snapshot slots, idempotency,
   watermark, future-leakage quality rule와 fail-closed publish 조건을 등록한다.
8. provider·권리·coverage·비용을 사용자가 승인한 뒤에만 DGH lifecycle을 활성화하고 구현한다.

## Suggested implementation sequence after approval

1. Close the domestic and U.S. bounded schema/rights samples without DB writes.
2. Approve one source contract and retained-PIT policy, or explicitly keep U.S. consensus unavailable.
3. Add dataset/metric/pipeline contracts and fixtures before physical DDL.
4. Implement append-only source observations and Silver normalization with no-leakage tests.
5. Implement event-window Gold metrics and `unavailable`/`partial`/`stale` consumer states.
6. Hand the stable DB-only service contract to WI-042; do not expose provider raw payloads through MCP.

## Limits of this research

- No provider endpoint was called and no response sample was persisted.
- No provider account, API key, subscription or commercial license was requested.
- Provider pricing, plan entitlement and terms were read from public pages and require a fresh check at activation.
- No live portfolio inventory, database object, DGH lifecycle, schema, service, MCP tool or deployment was changed.
- KIS field semantics remain unverified; prior row-return evidence proves connectivity/coverage only, not consensus quality.

`WI-041-S01` is closed as implementation input. Parent `WI-041` remains `proposed`, and MS-003 remains gated by
MS-002 operational acceptance plus the provider/contract approval above.
