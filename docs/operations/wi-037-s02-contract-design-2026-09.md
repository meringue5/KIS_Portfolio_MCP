# WI-037-S02 filing contract design — 2026-09-02

> Work Item: `WI-037-S02`
> 상태: ready for owner architecture/data-contract decision
> 분류: architecture/data-contract clarification; design only
> 선행 증거: `WI-037-S01`
> 변경 경계: production code, DDL, migration, DB write, source call, credential, payload fixture, deployment와 schedule activation 없음

## Purpose

OpenDART와 SEC EDGAR actual을 구현하기 전에 issuer identity, immutable source evidence, canonical filing event,
financial fact revision과 point-in-time query의 의미를 하나의 승인 가능한 설계로 고정한다. S01이 발견한
논리 Bronze `dataset.filing-event`와 물리 `silver.filing_events`의 layer mismatch를 조용히 수용하지 않는다.

## Starting evidence

- `source.opendart`와 `source.sec-edgar`는 canonical·approved이고 무료 공식 source다.
- `collection.fundamentals-dividends-v1`, `dataset.filing-event`, `dataset.financial-fact`와
  `pipeline.fundamentals-dividends-v2`는 approved지만 아직 active가 아니다.
- 현재 직접 filing 대상은 보유 KRX equity 3개와 미국 equity/REIT 4개다. S01 시점에 미국 4개는 CIK가
  있었고 국내 3개는 DART `corp_code`가 없었다.
- `silver.filing_events`와 `silver.financial_facts`는 foundation DDL에 존재하지만 S01 live inventory에서
  모두 0행이었다. 이 빈 foundation을 승인된 의미의 구현 완료로 간주하지 않는다.
- 현재 filing table은 jurisdiction, source URL, reporting period, correction relation과 object manifest를,
  fact table은 period start, context/revision identity와 source/normalized concept 분리를 충분히 표현하지 못한다.

## Questions to freeze

1. source observation/object evidence와 canonical filing ledger를 어떤 Bronze/Silver dataset ID로 분리할 것인가?
2. KRX `stock_code ↔ corp_code`와 U.S. ticker/exchange ↔ CIK alias의 유효시점·관찰시점·품질을 어떻게 보존할 것인가?
3. SEC acceptance timestamp, OpenDART day-grain receipt date, system `fetched_at`과 `knowledge_at`을 어떻게 구분할 것인가?
4. amendment/correction/withdrawal relation을 무엇을 근거로 확정하고 불명확한 관계를 어떻게 격리할 것인가?
5. source taxonomy/context를 보존하면서 normalized concept mapping을 어떤 version/provenance로 추가할 것인가?
6. 원문 object의 허용 media, content hash, private GCS retention, backup/restore와 재배포 금지를 어떻게 고정할 것인가?
7. routine/backfill 호출예산, pagination, conditional request, retry, partial quarantine와 watermark gate를 어떻게 고정할 것인가?
8. 기존 v1 계약과 빈 Silver foundation의 compatibility, additive migration, dual-read와 rollback 경계를 어떻게 정의할 것인가?

## Work plan and checkpoints

| Checkpoint | State | Output |
| --- | --- | --- |
| S02 registration and immutable scope | complete | registry, parent Work Item, traceability and milestone revision |
| current contract/physical compatibility matrix | complete | logical/physical mismatch and consumer impact |
| target identity/time/correction/object model | complete | keys, timestamps, relation quality and source-specific rules |
| bounded pipeline/cost/failure design | complete | routine/backfill budgets, pacing, retry, quarantine and watermark |
| alternatives and ADR/approval package | complete | versioning, migration, rollback, residual risk and owner decisions |
| quick/full verification and closeout | complete | 118 DGH contracts and 438 tests; no production mutation |

## Initial constraints

- directly held equity/REIT issuer만 포함하며 ETF look-through issuer를 다시 끌어오지 않는다.
- ticker, 종목명이나 heuristic만으로 issuer를 확정하지 않는다. missing/ambiguous alias는 fail closed다.
- backfill의 historical filing time과 시스템 최초 관찰시각을 동일시하지 않는다.
- correction은 이전 filing/fact를 덮어쓰지 않고 새 revision과 relation으로 보존한다.
- source taxonomy, concept, unit, period와 dimensional context를 normalized mapping이 대체하지 않는다.
- 원문은 허용된 official artifact만 private content-addressed object로 보존하고 MCP·Telegram에 재배포하지 않는다.
- approved contract를 구현 편의에 맞춰 같은 version으로 조용히 변경하지 않는다.

## Current-to-target compatibility matrix

| Concern | Current contract/physical state | Recommended target | Compatibility |
| --- | --- | --- | --- |
| Bronze evidence | `bronze.source_observations`와 `raw_object_manifest`는 있으나 filing logical dataset이 없음 | `dataset.filing-source-artifact`가 두 physical object의 filing-specific envelope/object 계약을 소유 | additive |
| issuer identity | `instrument_versions.issuer_id`와 metadata에 의존; alias validity/quality ledger 없음 | `dataset.issuer-source-alias`와 `silver.issuer_alias_revisions`에서 source alias를 bitemporal 보존 | additive |
| filing dataset | `dataset.filing-event` 1.0은 Bronze, 물리는 빈 `silver.filing_events` | 2.0을 Silver canonical identity/revision으로 재정의하고 Bronze artifact를 입력으로 명시 | breaking contract; new major |
| filing relation | 한 row에 `document_version`; correction type/target/quality가 없음 | identity와 revision을 분리하고 explicit/verified/candidate/unresolved relation을 보존 | additive physical replacement |
| facts | 빈 `silver.financial_facts`; period start/context/revision identity 부족 | raw source fact revision, mapping revision과 as-of projection을 분리 | breaking contract; new major |
| concept mapping | JSON `mapping_provenance`만 존재 | versioned `dataset.fundamental-concept-mapping` Control contract | additive |
| pipeline | filing, dividend, account reconciliation을 한 approved-but-inactive pipeline이 소유 | dedicated `pipeline.filing-actual-v1`; umbrella pipeline은 active로 올리지 않음 | additive and narrower |
| collection | approved umbrella가 ETF look-through-relevant issuer까지 표현 | direct held equity/REIT only인 `collection.filing-actual-v1` 분리 | additive and DEC-049 aligned |
| existing data | 두 foundation table 모두 S01 live 기준 0행, 알려진 consumer 없음 | migration preflight에서 다시 0행을 확인; non-zero면 자동 변환하지 않고 중단 | fail closed |

`dataset.filing-event`의 layer, grain, natural key와 time semantics가 바뀌므로 DGH의 architecture-impact 조건에
해당한다. 권고안은 신규 `ADR-025`를 승인한 뒤 contract major version을 변경하는 것이다. 기존 ADR-021/023은
저장 위치와 절차를 승인하지만 이 구체적인 SSOT·시점 의미를 대신 결정하지 않는다.

## Recommended logical model

```text
OpenDART / SEC EDGAR
        │
        ▼
dataset.filing-source-artifact (Bronze)
  ├─ bronze.source_observations  ── discovery/API envelope
  └─ bronze.raw_object_manifest ── private GCS content hash
        │
        ├──────────────► dataset.issuer-source-alias (Silver)
        │
        ▼
dataset.filing-event 2.0 (Silver)
  ├─ filing identity
  ├─ immutable filing revision
  └─ current/system-as-of/retrospective-source-as-of views
        │
        ▼
dataset.financial-fact 2.0 (Silver)
  ├─ immutable source fact revision
  └─ joins versioned Control concept mapping without overwriting source fact
```

### Issuer and alias identity

- canonical `issuer_id`는 jurisdiction과 공식 registry identity로 결정한다. 국내는 OpenDART `corp_code`,
  미국은 zero-padded SEC CIK가 authority다. ticker, 종목명과 heuristic은 authority가 아니다.
- alias revision은 `issuer_id`, `source_id`, `alias_type`, normalized `alias_value`, market/exchange,
  `source_valid_from/to`, `observed_at`, `knowledge_at`, evidence observation, `relation_quality`와 content hash를
  보존한다.
- `relation_quality`는 `verified`, `ambiguous`, `missing`, `superseded`로 제한한다. 한 cutoff에서 alias가 둘
  이상의 issuer를 가리키거나 직접보유 instrument가 mapping되지 않으면 해당 issuer partition을 publish하지
  않고 전체 run의 missing coverage에 기록한다.
- latest canonical holdings 중 직접보유 `equity`와 `REIT`만 선택한다. ETF 및 look-through issuer는
  DEC-049 후속 경로가 승인될 때까지 제외한다.

### Filing identity, revision and correction

- stable identity는 `source_id + jurisdiction + source_filing_id`다. SEC는 accession number, OpenDART는
  `rcept_no`를 사용한다.
- content revision key는 stable filing identity와 document/content hash다. source가 같은 identifier의 내용을
  바꾸면 기존 row를 덮지 않고 새 revision을 추가한다.
- 각 revision은 form/report code, filing title, fiscal year/period, statement scope, source URL,
  object-manifest hash, source-accepted/filed/receipt time, first-observed/fetched/knowledge time, parser version과
  quality를 가진다.
- correction relation은 `relation_type`, `target_filing_id`, `relation_quality`, evidence를 가진다.
  source가 명시한 연결 또는 검증된 deterministic evidence만 `verified`로 승격한다. OpenDART `rm=정`과 SEC
  `/A` form만으로는 correction 존재 후보일 뿐 원본 target을 확정하지 않는다.
- current/as-of view는 `verified` supersession만 원본을 대체한다. candidate/unresolved relation은 양쪽을
  보존하고 quality를 partial로 표시한다.

### Two point-in-time clocks

| Clock/query mode | Meaning | Rule |
| --- | --- | --- |
| `system_as_of` | 이 시스템이 실제로 알고 있던 상태 | `knowledge_at <= cutoff`; backfill row를 과거에 알았다고 소급하지 않음 |
| `retrospective_source_as_of` | 당시 공식 source에 공개됐다고 검증할 수 있는 상태 | `source_available_at <= cutoff`; 결과에 retrospective label과 timestamp precision을 표시 |

- SEC는 official `accepted_at`을 `source_available_at`으로 사용하되 first observation과 분리한다.
- OpenDART receipt date가 day-grain뿐이면 같은 날 장중 cutoff에 사용하지 않는다. 안전 경계는 다음 KST
  00:00이며 `source_time_precision=day`를 표시한다. 더 정확한 공식 timestamp가 확보된 문서만 별도 승격한다.
- canonical `knowledge_at`은 첫 성공 governed observation/publish 시각이며 뒤로 이동하지 않는다.
- 두 query mode의 row를 한 분석에서 무표시로 섞지 않는다. 실적 surprise와 live signal은 기본적으로
  `system_as_of`; 명시적 historical research만 retrospective mode를 사용할 수 있다.

### Financial fact and concept mapping

- source fact identity는 filing revision, source taxonomy/concept, period start/end, instant/duration,
  statement scope(CFS/OFS 등), unit와 original dimension/context hash를 포함한다.
- value, raw lexical representation, decimals/scale, context hash, filing revision, source/knowledge time과
  fact content hash를 보존한다. 변경된 value/context는 append-only fact revision이다.
- normalized concept는 source `taxonomy/concept`를 대체하지 않는다. 별도 Control mapping은
  `mapping_id/version`, source taxonomy/concept, normalized concept, unit/period constraints, valid/knowledge time,
  provenance와 review status를 가진다.
- `unmapped`와 ambiguous mapping은 그대로 노출하고 공식 ratio/valuation input으로 publish하지 않는다.
  as-of view는 cutoff에 유효한 filing revision과 mapping version을 각각 선택한다.

## Raw object, security and recovery contract

- 허용 입력은 official OpenDART/SEC의 JSON, XML/iXBRL/HTML, ZIP과 filing index/document다. API key, HTTP
  authorization header, cookie와 provider free-text error message는 object나 manifest에 넣지 않는다.
- object key는 SHA-256 content address이며 private GCS에 저장한다. manifest에는 source URL, media type,
  byte size, source publication/acceptance time, fetched time, rights/sensitivity, archive member inventory와 parser
  version을 기록한다.
- Silver publish 전에 upload와 hash 확인이 끝나야 한다. activation 전 source별 대표 artifact를 private
  download해 hash, archive inventory와 parse reconciliation을 검증한다.
- object는 MCP·Telegram·public response로 반환하지 않는다. normalized allowlisted facts와 lineage reference만
  후속 private MCP read model의 후보가 된다.
- initial guardrail은 단일 object 50 MiB, expanded archive 200 MiB/2,000 members, 전체 filing object 5 GiB다.
  초과·unexpected media·path traversal·encrypted archive는 quarantine하고 owner 재계획 전 ingest하지 않는다.
- collected canonical artifact는 자동 삭제하지 않는다. 5 GiB preflight를 넘거나 source rights가 바뀌면
  collection을 멈추고 retained object의 보존/삭제를 별도 승인한다.

## Bounded pipeline contract

### Scope and schedule

- pipeline ID proposal: `pipeline.filing-actual-v1`; source별 partition을 같은 managed runner와 control-plane
  evidence 형식으로 실행한다.
- OpenDART incremental은 KRX 영업일 18:10 KST, SEC incremental은 완료된 미국 session 뒤 08:10 KST를
  초기 후보로 둔다. 실제 Scheduler 생성은 release gate에서 확정하며 source가 닫혔거나 issuer allowlist가
  비면 no-op한다.
- allowlisted managed refresh는 후속 Remote MCP command가 같은 fixed partition을 요청할 수 있지만 arbitrary
  ticker, CIK, corp_code, date range와 raw URL을 받지 않는다.

### Physical-call budgets

| Mode | OpenDART | SEC EDGAR | Enforcement |
| --- | ---: | ---: | --- |
| routine daily | global 100/day, issuer 20, search max 2 pages | global 64/day, issuer 16, concurrency 1 and at most 1 request/sec | reserve before every call; retry도 소비 |
| initial backfill | total 250, issuer/fiscal-year/report/CFS-OFS partitions | total 320, issuer/year/base-form partitions | immutable plan/budget hash; cap 초과 시 실행 전 fail closed |

Provider published ceiling은 project budget으로 사용하지 않는다. cap은 현재 3개 국내 직접보유 issuer와 4개
미국 직접보유 issuer를 위한 상한이다. scope 증가, pagination preflight 초과 또는 provider policy 변경은
contract version과 owner review를 요구한다.

### Retry, partial and watermark

- GET/download만 retry하며 timeout, network, 429와 5xx에 최대 2회 exponential backoff를 허용한다.
  `Retry-After`를 우선하고 모든 physical attempt를 budget에 포함한다. auth, identity mismatch, schema drift,
  invalid media와 4xx는 같은 run에서 retry하지 않는다.
- `collect → land → parse → normalize → reconcile → quality → publish` 각각의 count/hash/status를 기록한다.
  landed object는 partial 증거로 남길 수 있지만 Silver publish는 issuer identity, page/document coverage,
  object hash, correction relation quality와 fact reconciliation gate를 통과해야 한다.
- watermark는 source·issuer partition별이다. 마지막 search page, filing identity와 fetched cutoff를 기록하고
  object upload, parse, reconciliation과 publish가 모두 성공한 뒤에만 advance한다. partial/quarantine/failure는
  기존 watermark를 유지한다.
- 같은 plan/partition/content hash replay는 no-op이고 다른 content가 같은 source identity로 오면 새 revision이다.

## Capacity and cost envelope

- 직접보유 7개 issuer, 5개 fiscal year와 최소 8 quarters만 대상으로 하며 ETF issuer는 포함하지 않는다.
- design preflight ceiling은 filing artifact 5 GiB와 typed fact revision 2,000,000 rows다. 이는 목표량이 아니라
  무계획 확장을 차단하는 stop line이다. 초과 예상 시 source/form/concept 범위를 재설계한다.
- 기존 MotherDuck, private GCS, Secret Manager와 scale-to-zero Cloud Run Job을 재사용한다. 새 warehouse,
  always-on service와 유료 provider는 없다. 따라서 월 50,000원 architecture tier는 바뀌지 않지만 실제
  object bytes, query/storage와 Job duration은 backfill dry-run에서 다시 산정한다.

## Proposed DGH and ADR delta

아래는 승인 전 proposal이며 catalog lifecycle을 아직 바꾸지 않는다.

| Contract/decision | Proposed version/status | Purpose |
| --- | --- | --- |
| `ADR-025` | proposed | official filing artifact, dual clock, issuer alias and append-only revision SSOT |
| `dataset.filing-source-artifact` | 1.0.0 / proposed | Bronze filing-specific source envelope and private object lineage |
| `dataset.issuer-source-alias` | 1.0.0 / proposed | bitemporal corp-code/CIK/ticker/exchange alias revisions |
| `dataset.filing-event` | 2.0.0 / proposed | Silver filing identity/revision and verified correction selection |
| `dataset.financial-fact` | 2.0.0 / proposed | immutable source fact revisions with dual-clock as-of selection |
| `dataset.fundamental-concept-mapping` | 1.0.0 / proposed | versioned Control mapping without source fact overwrite |
| `collection.filing-actual-v1` | 1.0.0 / proposed | direct held equity/REIT official actual only; no ETF or dividend receipt scope |
| `pipeline.filing-actual-v1` | 1.0.0 / proposed | source-specific bounded scale-to-zero filing collection |

`source.opendart`와 `source.sec-edgar` 1.0은 canonical provider, rights와 auth가 바뀌지 않으므로 유지하고 exact
physical-call cap은 pipeline contract에 둔다. 기존 `collection.fundamentals-dividends-v1`과
`pipeline.fundamentals-dividends-v2`는 historical umbrella로 approved-but-inactive 상태를 유지하며 이 경로로
activation하지 않는다. dividend는 WI-038에서 전용 계약으로 분리한다.

## Migration and rollback design

1. proposed ADR/contract 승인 뒤 migration `0014`를 additive로 만든다. 예상 객체는
   `silver.issuer_alias_revisions`, `silver.filing_identities`, `silver.filing_revisions`,
   `silver.financial_fact_revisions`, `control.fundamental_concept_mappings`와 as-of/current view다.
2. migration preflight는 기존 `silver.filing_events`와 `silver.financial_facts`가 여전히 0행이고 알려진
   consumer가 없는지 확인한다. 하나라도 non-zero면 자동 이관하지 않고 별도 mapping/reconciliation item으로
   중단한다.
3. legacy foundation table은 삭제·rename하지 않는다. 새 repository는 새 객체만 쓰고 fixture/replay에서
   current/system-as-of/retrospective-source-as-of 결과를 검증한다.
4. synthetic 또는 redistribution-safe fixture로 KR/US standard, DART day precision, SEC accepted timestamp,
   correction/amendment, withdrawal, CFS/OFS, custom taxonomy, dimension, ambiguous alias와 changed-content replay를
   검증한다.
5. temporary DuckDB migration/backup/restore와 private object round-trip이 통과한 뒤 bounded source sample을
   별도 sub-item에서 수행한다. production backfill과 Scheduler는 다시 분리한다.
6. rollback은 Scheduler/accessor를 비활성화하고 이전 schema minimum/image manifest로 되돌린다. append-only
   object와 rows는 삭제하지 않고 미사용 상태로 보존한다.

## Alternatives considered

| Alternative | Disposition | Reason |
| --- | --- | --- |
| 현 `silver.filing_events`에 nullable column만 추가 | reject | identity/revision과 Bronze/Silver mismatch가 남고 같은 v1 의미를 silent widening함 |
| source JSON만 Bronze에 보존하고 typed Silver를 최소화 | reject | correction, taxonomy/context와 deterministic as-of query가 JSON path에 종속됨 |
| companyfacts/OpenDART structured endpoint만 저장 | reject | original filing/context와 correction lineage를 완전히 재현하지 못함 |
| raw object와 normalized fact를 한 table에 저장 | reject | 권리·backup·parse lifecycle과 Silver query grain이 결합됨 |
| 권고안: dedicated filing contracts and additive ledger | select pending owner | SSOT, replay, rollback과 downstream WI-038/041 경계를 가장 명확히 유지함 |

## Owner decision package

다음 여섯 항목을 한 묶음으로 승인하는 것을 권고한다.

1. `ADR-025`로 canonical issuer alias, Bronze artifact, Silver filing/fact revision과 dual as-of clock을 고정한다.
2. 위 7개 DGH contract delta를 승인하되 모두 inactive로 두고 기존 umbrella를 activation하지 않는다.
3. migration 0014는 additive new object만 허용하고 기존 foundation non-zero 시 fail closed한다.
4. OpenDART routine/backfill 100/250, SEC 64/320, 1 rps·concurrency 1과 retry-counted budget을 승인한다.
5. private official artifact 5 GiB, object 50 MiB/expanded 200 MiB guardrail과 no redistribution을 승인한다.
6. contract/fixture/schema 구현은 다음 순차 sub-item으로, credential/source sample, live migration, backfill,
   Scheduler/production activation은 각각 이후 gate로 분리한다.

Residual risk는 OpenDART day-grain availability, source가 명시하지 않은 correction target, custom taxonomy와
facts volume이다. conservative next-day boundary, verified-only supersession, unmapped fail-closed, 2,000,000-row/
5-GiB stop line과 source-specific bounded sample로 완화한다.

## Acceptance criteria

- [ ] Bronze/Silver dataset 경계, grain, natural key, time semantics와 compatibility가 명시된다.
- [ ] issuer alias, filing correction, fact revision과 point-in-time selection이 source별로 정의된다.
- [ ] raw object retention, restore, security와 consumer 경계가 정의된다.
- [ ] routine/backfill call budget, partial/failure, idempotency와 watermark가 수치로 제안된다.
- [ ] ADR 필요 여부, contract version delta, migration/rollback과 owner approval 항목이 제시된다.
- [ ] 구현·DB·source·credential·deployment 변경이 없고 quick/full gate가 통과한다.

## Current disposition

S02 설계는 owner가 한 번에 검토할 수 있는 `ready` 상태다. parent `WI-037`과 MS-003은 `proposed`이고,
현재 approved 계약은 active로 승격하지 않았다. catalog, SPEC, DDL, code, DB, source, credential와 deployment는
변경하지 않았다. owner 승인 전 proposed ADR-025와 7-contract delta는 이 문서의 proposal일 뿐 결정 SSOT가
아니다. Full verification은 118개 DGH contracts와 438 tests를 통과했다.
