# WI-041-S02 bounded consensus sampling — 2026-09-01

> Work Item: `WI-041-S02`
> 분류: research-only source sampling
> 변경 경계: KIS 6 physical calls, Alpha Vantage public demo 1 call; raw-payload persistence, provider signup,
> credential issuance, contract activation, consensus DB write, DDL, pipeline, MCP와 deployment 없음

## 결론

이번 표본으로 KIS 국내 추정실적을 canonical consensus source로 채택할 수 없음을 확인했다. Alpha Vantage는
공식 demo key가 `EARNINGS_ESTIMATES`의 실제 payload를 반환하지 않아 credentialed schema sample이
수행되지 않았다. 어느 provider도 lifecycle을 `approved`로 올리지 않는다.

- KIS는 최신 asset overview에서 확인한 국내 직접발행사 3개를 익명 label로 표본화했다. 그 최신 overview는
  완전성 판정값이 없는 legacy 관측이므로 “현재 보유 전체”를 증명하지는 않지만, 이전 held-scope 조사에서
  확인한 국내 직접발행사 3개와 개수는 일치했다.
- `estimate-perform` 3회와 `invest-opinion` 3회는 HTTP 200, `rt_cd=0`으로 끝났다. 재시도와 pagination은
  사용하지 않았고 호출 예산 6회를 모두 소비했다.
- 추정실적의 `output4`는 세 표본 모두 5개 기간(과거 3개와 `E`가 붙은 미래 2개)을 제공했다. 그러나
  `output2`는 6개의 무명 행, `output3`은 종목별 3개 또는 8개의 무명 행이며 값 column도 모두
  `data1`~`data5`다. 공식 sample code와 local reference 역시 행 metric, unit과 회계 basis를 설명하지 않는다.
- `output1`은 단일 analyst-name-like field, recommendation과 estimate date를 포함했지만 analyst population,
  count, estimate distribution 또는 revision lineage를 제공하지 않았다. 두 표본은 같은 analyst/date를
  반환해 issuer별 consensus snapshot identity로도 불충분했다.
- 투자의견은 각 표본에서 단일 page 100행을 반환했고 business date, member-company name, opinion class,
  target price와 prior opinion을 제공했다. analyst identity/count와 estimate distribution은 없고, 100행에서
  잘렸을 가능성을 배제할 pagination coverage 증적도 이번 budget에는 없다.
- 따라서 3 issuers x 3 metrics의 독립 semantic 대조 acceptance는 실패했다. 값의 크기나 행 위치를 근거로
  매출·영업이익·순이익·EPS 같은 이름을 추측해서는 안 된다.
- Alpha Vantage 공식 문서는 `EARNINGS_ESTIMATES`가 annual/quarterly EPS·revenue estimates, analyst count와
  revision history를 반환한다고 설명한다. 하지만 문서의 IBM demo URL은 실제 payload 대신 무료 API key
  발급 안내만 반환했다. repository 환경에도 Alpha Vantage key가 없으며 가입·EULA 수락을 대신하지 않았다.
- Alpha Vantage 약관은 개인적 investment analysis, research, testing과 monitoring을 허용하지만, provider
  content의 MotherDuck 장기 snapshot 보존, 백업, 구독/계정 종료 후 retention과 LLM/MCP 내부 사용을 명시적으로
  허가하지 않는다. 공개 약관만으로 `backup_policy`를 바꾸지 않는다.

## 호출과 데이터 취급 증적

| Provider | Scope | Calls | Result | Persistence |
| --- | --- | ---: | --- | --- |
| KIS `estimate-perform` | anonymized held KRX direct issuers 3 | 3 | 3/3 HTTP 200, `rt_cd=0` | none |
| KIS `invest-opinion` | same 3 issuers, trailing 370-day request, first page only | 3 | 3/3 HTTP 200, `rt_cd=0`, 100 rows each | none |
| Alpha Vantage `EARNINGS_ESTIMATES` | official IBM demo request | 1 | informational denial; personal free key required | none |

계좌번호, 실제 issuer symbol, API key, token과 raw response는 repository 문서·DB·object storage에 기록하지
않았다. 이 문서는 익명 label의 row/column shape와 판정만 보존한다. KIS 인증 token cache의 일반 런타임
동작 외에 consensus dataset write는 없었다.

## 관측된 KIS shape

| Output | Observed shape across 3 issuers | Contract implication |
| --- | --- | --- |
| `output1` | 1 row each; symbol/name plus analyst-like name, estimate date, recommendation and unlabeled numeric fields | single research/opinion header candidate; consensus population 아님 |
| `output2` | 6 rows x `data1`~`data5` in every sample | six metrics may exist, but identity/unit/basis unavailable |
| `output3` | 3, 8, 8 rows x `data1`~`data5` | variable metric rows without labels; positional mapping unsafe |
| `output4` | five period labels: three historical, two forward `E` | forecast horizon exists; each value column can align only after metric semantics are proven |
| `invest-opinion.output` | 100 first-page rows each; date, member company, opinion/current-prior class, target/close/divergence fields | opinion history candidate; analyst count/distribution and full pagination unknown |

`fetched_at`을 우리 시스템의 earliest knowledge time으로 사용할 수는 있지만, KIS response 안에 각 estimate의
provider publication/version time과 analyst sample definition이 없으므로 발표 직전 consensus selection이나
7/30/90-day revision replay에는 사용할 수 없다.

## 공식 근거

- [KIS official estimate-perform sample](https://github.com/koreainvestment/open-trading-api/blob/main/examples_llm/domestic_stock/estimate_perform/estimate_perform.py)
- [KIS official invest-opinion sample](https://github.com/koreainvestment/open-trading-api/blob/main/examples_llm/domestic_stock/invest_opinion/invest_opinion.py)
- [Alpha Vantage EARNINGS_ESTIMATES documentation](https://www.alphavantage.co/documentation/)
- [Alpha Vantage terms of service](https://www.alphavantage.co/terms_of_service/)

## Gate disposition

| Required activation property | KIS | Alpha Vantage after S02 |
| --- | --- | --- |
| metric/unit/basis | failed: unlabeled positional rows | documented EPS/revenue only; live sample unavailable |
| analyst count and distribution | failed | documented count; distribution and sample definition unverified |
| revision lineage | failed | documented revision history; timestamps/identity unverified |
| historical PIT / no leakage | failed | not established by docs or demo |
| held-issuer coverage | 3/3 endpoint connectivity only | not sampled |
| internal retention/backup right | existing KIS account-private use does not prove this dataset contract | ambiguous; written clarification required |
| cost/call budget | 6-call research sample completed | free key advertised, actual entitlement unverified |

`source.kis-open-api`, `source.consensus-provider-tbd`, `collection.consensus-research-later`와
`dataset.consensus-snapshot`의 lifecycle은 변경하지 않는다. 특히 현재 `backup_policy = excluded`를 억지로
완화하지 않는다.

## Newly identified sub-item

`WI-041-S03`은 owner-controlled Alpha Vantage free key가 있을 때만 다음을 수행한다.

1. EULA를 사용자가 직접 수락하고 발급한 credential을 Secret Manager에 저장한다. credential을 repository나
   대화에 붙이지 않는다.
2. 현재 미국 직접발행사 4개를 다시 산정하고 최대 4 calls로 `EARNINGS_ESTIMATES`의 top-level/row field,
   null, period, analyst-count와 revision shape만 표본화한다. raw values는 저장하지 않는다.
3. provider에 private cloud warehouse snapshot, derived metrics, backup, LLM/MCP internal analysis와
   termination-after-retention을 서면 질의한다. 답변 전 raw PIT retention은 금지한다.
4. 실제 response가 historical snapshots가 아니라 현재 estimate와 lookback comparison만 제공하면
   DEC-021/032의 PIT source로 탈락시킨다.

이 sub-item은 무료 key 발급과 약관 수락이라는 owner action 전에는 실행할 수 있다거나 완료된 것으로
표시하지 않는다. 유료 plan, subscription과 production activation은 여전히 별도 승인 대상이다.

## Closeout

`WI-041-S02`는 bounded sampling을 실제로 수행하고 접근 불가를 fail-closed 결과로 기록했으므로 closed다.
Parent `WI-041`과 MS-003은 `proposed`다. 다음 실행 가능 sub-item은 owner credential/rights action이 필요한
`WI-041-S03`이며, 그 전에도 WI-037/038/039/040의 contract-hardening work는 별도로 진행할 수 있다.
