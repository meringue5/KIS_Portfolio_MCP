# WI-037 filing and fundamental pre-research — 2026-08-31

> Work Item: `WI-037-S01`
> 범위: repository, official documentation and live aggregate metadata read-only research
> 변경 경계: source call, credential use, payload collection, DB write, migration, deployment and schedule activation 없음

## 결론

OpenDART와 SEC EDGAR를 국내·미국 actual의 canonical source로 쓰는 승인 방향은 유효하다. 그러나 현재
`WI-037`은 adapter 구현보다 **identity와 point-in-time 계약 hardening**이 먼저다.

- live `silver.filing_events`와 `silver.financial_facts`는 모두 0행이다.
- 최신 양수 보유범위는 31 instruments다. 직접 filing 대상은 KRX equity 3개와 미국 equity 3개·REIT 1개다.
  미국 4개는 CIK issuer mapping이 있으나 국내 equity 3개는 모두 DART `corp_code`가 없다.
- 승인된 `dataset.filing-event`는 Bronze지만 물리 catalog와 DDL은 `silver.filing_events`다.
- 현재 DDL은 correction relation, jurisdiction, source URL, reporting period, period start, original context,
  normalized concept and fact revision을 충분히 표현하지 못한다.
- OpenDART key configuration과 Secret Manager resource는 아직 없다. SEC fair-access User-Agent와 bounded
  submissions lookup은 기존 코드에 있다.

따라서 production collection, backfill과 Scheduler는 계속 금지한다. 먼저 compatible contract revision 또는
새 Bronze/Silver dataset 경계를 owner가 승인하고, additive migration·repository·fixture를 만든 뒤 bounded
source sampling으로 넘어가야 한다.

## 공식 source 확인

### OpenDART

OpenDART는 누구나 이용 가능한 무료 OpenAPI로 공시 원문 XML, 고유번호, 공시검색과 정형 재무정보를
제공한다. 공식 고유번호 자료에는 8자리 `corp_code`, 6자리 `stock_code`와 `modify_date`가 있다.
공시검색은 14자리 `rcept_no`, 접수일과 정정·철회 등을 나타내는 `rm`을 반환한다. 원문은 `rcept_no`로 ZIP을
받고, 단일회사 전체 재무제표는 `corp_code`, 사업연도, 보고서코드와 CFS/OFS 구분으로 조회한다.

- [OpenDART OpenAPI 소개](https://opendart.fss.or.kr/intro/main.do)
- [고유번호 API](https://opendart.fss.or.kr/guide/detail.do?apiGrpCd=DS001&apiId=2019018)
- [공시검색 API](https://opendart.fss.or.kr/guide/detail.do?apiGrpCd=DS001&apiId=2019001)
- [공시서류 원본 API](https://opendart.fss.or.kr/guide/detail.do?apiGrpCd=DS001&apiId=2019003)
- [단일회사 전체 재무제표 API](https://opendart.fss.or.kr/guide/detail.do?apiGrpCd=DS003&apiId=2019020)
- [OpenDART 이용약관](https://opendart.fss.or.kr/intro/terms.do)

일반적인 request-limit 오류 기준은 20,000건 이상이지만 key나 endpoint에 따라 다를 수 있고 허용량도
변경될 수 있다. 약관은 무료 원칙과 공공데이터법 적용, 인증키 비공개, 과도한 접속 제한, 제공 정보의
정확성·완전성 비보장을 명시한다. 개인 분석용 원문은 private content-addressed object로만 보존하고 public
MCP나 Telegram에 원문을 재배포하지 않는 현재 보안 경계를 유지한다.

`rm=정`은 후속 정정 존재를 알려주지만 그 값만으로 원본과 정정본의 완전한 관계를 구성했다고 주장할 수
없다. 모든 receipt를 보존하고 bounded fixture에서 report name, receipt metadata와 원문 relation을 검증해야
한다. OpenDART list의 접수일은 일 단위이므로 intraday backtest의 정확한 지식시각으로 사용해서는 안 된다.

### SEC EDGAR

SEC `data.sec.gov`의 submissions와 XBRL APIs는 API key 없이 공개된다. submissions는 current filing history와
additional history file ranges를 제공하고, companyfacts는 한 CIK의 standard taxonomy entity-wide facts를
한 번에 제공한다. APIs are updated throughout the day; submissions typically lag under a second and XBRL under a
minute, while bulk ZIP files are republished nightly.

- [SEC EDGAR data APIs](https://www.sec.gov/search-filings/edgar-application-programming-interfaces)
- [SEC developer resources and fair access](https://www.sec.gov/about/developer-resources)
- [Accessing EDGAR data](https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data)

The official ceiling is 10 requests/second across all machines. The project must remain substantially below that,
declare a contact-bearing User-Agent, cache responses, use bounded concurrency and back off. SEC also states that its
ticker/CIK association files are periodically updated but do not guarantee accuracy or scope. CIK and accession number,
not ticker alone, are canonical filing identity.

Companyfacts only aggregates non-custom taxonomy facts that apply to the entire filing entity. It therefore cannot by
itself satisfy the approved requirement to preserve original taxonomy and dimensional context. The filing XBRL/iXBRL
instance or an equivalent official filing artifact must be landed for original facts; submissions/companyfacts remain
discovery, fast-path and reconciliation inputs.

## Current repository and live readiness

| Area | Ready input | Gap before implementation |
| --- | --- | --- |
| source contracts | OpenDART and SEC approved, free/public, canonical | numerical routine/backfill budgets are still prose |
| collection | five fiscal years and eight quarters, daily held-issuer incremental | collection still mentions look-through ETF issuers although DEC-049 excludes them from initial V2 |
| issuer identity | exact SEC ticker/CIK and submissions validation code; US 4/4 direct issuers mapped | KRX equity DART corp-code mapping 0/3; mapping history and validity contract absent |
| raw landing | generic Bronze observation/manifest and private GCS content-addressed store exist | filing-specific rights/media/receipt manifest and bounded restore fixture absent |
| filing ledger | approved logical contract and empty physical table exist | layer mismatch and missing correction/source/reporting fields |
| fact ledger | approved logical contract and empty physical table exist | period start/context/revision/normalized mapping fields and PIT view absent |
| SEC access | contact-bearing User-Agent validation and bounded submissions header lookup | filings/companyfacts/XBRL adapters and shared SEC rate governor absent |
| OpenDART access | official API contract approved | env/Secret Manager key, adapter, parser and response error policy absent |
| runtime | resumable V2 pipeline/run/quality/lineage foundation exists | fundamentals stages, repository and fixed schedule target absent |

The other held instruments—14 KRX ETFs and 10 unresolved instruments—must not expand the initial issuer scope. Filing
collection is limited to directly held equity/REIT issuers until an independently approved look-through route exists.

## Contract and schema hardening gate

Before code implementation, formal `WI-037` planning must resolve these items together:

1. Separate immutable Bronze source observation/object evidence from the Silver canonical filing ledger. Recommended
   direction is to bind raw payloads to the existing Bronze foundation and version `dataset.filing-event` as the Silver
   canonical event, or introduce separate Bronze and Silver dataset IDs. The current Bronze-logical/Silver-physical
   mismatch cannot remain silent.
2. Make issuer aliases bitemporal: KRX `stock_code ↔ corp_code`, U.S. ticker/exchange ↔ CIK, source effective time,
   observed time and mapping quality. Missing or ambiguous mappings fail closed.
3. Add filing fields for jurisdiction, source filing ID, form/report code, reporting period, filed/accepted/source-date,
   observed/fetched/knowledge time, source URL, object manifest reference, amendment/correction relation, document hash
   and relation quality.
4. Add fact fields for source taxonomy and concept, normalized concept separately, period start/end, instant/duration,
   unit, decimals/scale, raw dimensional context/hash, accession/receipt, fact revision/hash, accepted/source time,
   knowledge time and mapping version/provenance.
5. Create point-in-time selection semantics. Historical source acceptance and the system's first observation are distinct.
   Backfilled facts may support explicitly labelled retrospective replay, but must not pretend the system knew them at
   the historical period end. OpenDART day-only timestamps require a conservative daily boundary.
6. Add canonical current/as-of views only after corrections and duplicate contexts reconcile. Mapping may add a
   normalized concept but must never discard or overwrite the source concept.

These changes affect layer, grain, natural key and time semantics. They require an approved contract version/ADR review
before parent `WI-037` can honestly retain `architecture_impact: none`.

## Candidate bounded execution policy

The exact numerical policy belongs to formal planning, but a safe starting proposal is:

- routine OpenDART: directly held mapped KRX issuers only, incremental date window, all original/corrected filings,
  daily cap 100 physical calls and per-request pagination cap; new filing details only after list discovery;
- OpenDART initial load: separate resumable backfill, issuer/report/CFS-or-OFS partitions, proposed total cap 250 calls
  for the current three direct issuers; CFS preference and OFS fallback remain explicit rather than double counting;
- routine SEC: directly held mapped U.S. equity/REIT issuers only, concurrency 1, at most 1 request/second and proposed
  daily cap 64; one submissions and one companyfacts conditional refresh per issuer, then only newly discovered filing
  artifacts;
- all sources: reserve budget before each physical request, persist ETag/Last-Modified when supplied, stop before quota,
  quarantine partial pages/documents, and advance watermark only after object hash, identity, reconciliation and quality.

These project caps are intentionally far below provider ceilings. They are research recommendations, not activated
production policy.

## Suggested implementation sequence

1. Approve the Bronze/Silver, natural-key and bitemporal contract correction.
2. Add OpenDART credential contract and Secret Manager reference through the normal security/release gate.
3. Implement exact issuer alias mapping and close KRX 0/3 direct-equity coverage.
4. Add additive migration, repositories and as-of queries; retain the two empty foundation tables until migration and
   rollback are tested.
5. Record synthetic or redistribution-safe bounded fixtures for KR/US standard, correction/amendment, custom taxonomy,
   missing mapping and CFS/OFS cases.
6. Implement source governors and resumable backfill planner, then private-object backup/restore.
7. Run dry-run and reconciliation before any Scheduler activation. KIS estimate data remains separately labelled
   experimental and cannot enter official actual facts or consensus.

## Limits of this research

- No OpenDART key or provider payload was used; current held-issuer response coverage and byte-size projection remain
  unmeasured.
- No SEC/OpenDART filing was downloaded, and no raw document retention test was performed.
- Live database queries were aggregate-only; no account ID, instrument symbol, filing payload or secret was emitted.
- Provider documentation can change, so rate/terms review remains a release and quarterly source gate.

`WI-037-S01` is closed as implementation input. Parent `WI-037` remains `proposed` and MS-003 remains gated by MS-002.
