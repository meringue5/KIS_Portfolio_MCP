# KIS Portfolio Data Governance Harness

> 정식 명칭: Data Governance Harness
> 한국어 명칭: 데이터 거버넌스 하네스
> 약칭: DGH
> 상태: 승인·활성
> 기준일: 2026-08-28
> 소유 범위: source, collection basket, dataset, metric, pipeline의 계약과 데이터 수명주기 통제

## 1. 목적과 위치

Data Governance Harness는 KIS Portfolio의 데이터가 **수집할 수 있다는 이유만으로 수집되거나,
DB에 존재한다는 이유만으로 공식 데이터가 되는 것**을 막는 전문 control system이다. Project OS 아래에서
data architecture를 집행하며, MotherDuck이나 특정 governance SaaS를 정책 SSOT로 만들지 않는다.

```text
KIS Portfolio Project Operating System
└── Data Governance Harness
    ├── policy and authority
    ├── source / collection / dataset / metric / pipeline contracts
    ├── design-time and CI gates
    ├── migration, runtime quality and publish gates
    └── catalog, quality, lineage and audit evidence

Product Data Plane
├── Source adapters and raw landing
├── MotherDuck Bronze / Silver / Gold / Control
├── Firestore operational state and Secret Manager
└── Remote MCP and Telegram consumers
```

DGH는 product data plane을 대신하지 않는다. 정책과 계약은 DGH가 소유하고, 실제 데이터·실행 증거는
승인된 application/data architecture에 저장한다. 현재는 repository-local governance-as-code를 사용한다.
상시 운영되는 별도 catalog SaaS는 1인 운영과 월 50,000원 비용 상한에 필요하지 않다.

## 2. Authority와 SSOT

| 책임 | Canonical source | 집행 수단 |
| --- | --- | --- |
| DGH 정책·예외·gate | 이 문서 | Project OS, Skill, review |
| 계약 형식과 허용 값 | `governance/contract-schema.toml` | DGH checker |
| source 계약 | `governance/catalog/sources.toml` | DGH checker |
| 수집 장바구니 | `governance/catalog/collections.toml` | DGH checker |
| dataset 계약 | `governance/catalog/datasets.toml` | DGH + warehouse checker |
| metric 계약 | `governance/catalog/metrics.toml` | DGH + analytics tests |
| pipeline 계약 | `governance/catalog/pipelines.toml` | DGH + pipeline runner |
| application read-model 계약 | `governance/catalog/read-models.toml` | DGH bounds·sensitivity·activation gate |
| macro exact-series registry | `governance/catalog/macro-series.toml` | DGH identity·rights·activation gate |
| ETF provider 실행 profile | `governance/catalog/etf-source-profiles.toml` | DGH rights/host gate |
| ETF exact instrument route | `governance/catalog/etf-instrument-routes.toml` | DGH route/reference gate |
| 물리 object·grain·key·backup | `docs/data-catalog.md` + `src/kis_portfolio/db/catalog.py` | warehouse checker |
| DDL·migration | versioned migration; 전환 전에는 `db/schema.py` | migration/release gate |
| run·watermark·quality·lineage | 목표 MotherDuck `control` schema | runtime/release gate |
| 요구·장기 결정 | 승인 DEC와 `SPEC.md` ADR | Project OS ADR gate |

문서 설명과 manifest가 충돌하면 구현을 진행하지 않는다. 정책은 이 문서, 계약 필드와 enum은 machine
schema, 개별 계약값은 catalog manifest가 우선한다. 물리 객체는 dataset contract와 data catalog 양쪽에
연결되어야 하며 어느 한쪽만 존재하면 drift다.

Phase 0 전환 시점의 V1 managed object와 현재 batch command는 `docs/data-catalog.md`, `db/catalog.py`와 기존
운영 문서의 계약으로 grandfather한다. 빈 DGH registry가 기존 운영 데이터를 미관리 상태로 되돌리지는
않지만, 새 source·수집·dataset·metric·pipeline 또는 기존 의미 변경은 manifest 없이 추가할 수 없다.
Phase 1 source inventory에서 기존 V1 producer/consumer도 DGH contract로 역등록한 뒤 이 임시 경계를 닫는다.

## 3. 통제 대상과 계약 수명주기

### 3.1 계약 종류

| Kind | 질문 | 구현 전 필수 결과 |
| --- | --- | --- |
| `source` | 어디서 어떤 권리와 제약으로 가져오는가? | canonical 역할, 인증, license, 지역, 비용·호출·가용성 정책 |
| `collection` | 가능한 source 중 지금 무엇을 어느 범위로 모으는가? | scope, 우선순위, history, schedule, trigger, 비용·인수 기준 |
| `dataset` | 어떤 의미와 grain으로 보존·공개하는가? | source/input, key, 시간, schema, layer, 품질·보존·backup·consumer |
| `metric` | 어떤 시점의 입력으로 무엇을 계산하는가? | formula version, unit, point-in-time, quality와 검증 계약 |
| `pipeline` | 어떤 입력을 어떤 통제로 출력하는가? | stage, schedule, idempotency, retry, call budget, quality/publish gate |
| `read_model` | 승인된 manifest와 운영 증거를 소비자에게 어떤 제한으로 투영하는가? | input, response schema, allow/suppress fields, query/status/unavailable policy, size/page/lookback와 activation gate |
| `macro_series` | 승인된 macro 개념을 어느 provider identity와 권리·단위·빈티지로 고정하는가? | exact source/series identity, native metadata, rights, transform와 inactive/production gate |
| `etf_profile` | 해당 provider를 어떤 형식·host·권리로 실행할 수 있는가? | parser/version, media type, host, history와 rights tri-state, activation |
| `etf_route` | 어떤 ETF를 어느 provider product에 연결하는가? | exact canonical instrument, provider key와 유효시점; holding fact 금지 |

수집 장바구니는 단순 TODO가 아니다. 승인된 `source`와 `dataset`만 참조하는 versioned `collection`
contract다. 우선순위가 바뀌어도 과거 version을 덮어쓰지 않는다.

### 3.2 Lifecycle

```text
proposed → approved → active → deprecated → retired
```

- `proposed`: 조사·대안 비교 단계. production 수집이나 공식 소비 금지.
- `approved`: owner가 계약과 비용·권리를 승인했으나 아직 활성화되지 않음.
- `active`: production producer/consumer가 사용할 수 있음.
- `deprecated`: 신규 consumer 금지. 종료일·대체 계약·migration 계획이 필요함.
- `retired`: production producer/consumer 금지. 보존·삭제는 retention 계약과 별도 승인에 따름.

`approved` 이상은 비어 있지 않은 `decision_refs`를 가져야 한다. active 계약은 proposed/retired 계약에
의존할 수 없다. quality failure는 lifecycle을 자동 변경하지 않고 운영 상태를 `partial`, `stale`,
`failed`, `quarantined`로 별도 기록한다.

## 4. Contract-first 규칙

1. source 조사 결과를 바로 adapter 코드나 table로 만들지 않는다.
2. source contract를 proposed로 등록하고 license, 인증, rate limit, 비용과 canonical 역할을 검토한다.
3. 수집할 대상을 collection contract로 선택하고 dataset 계약과 함께 승인한다.
4. dataset의 grain, key, time semantics, schema, freshness, quality, lineage, retention과 backup을 먼저 고정한다.
5. pipeline과 metric은 승인된 dataset ID를 참조한다.
6. 구현 Work Item은 관련 contract ID/version을 명시한다.
7. contract가 approved/active가 되기 전 production DDL, schedule, backfill과 public MCP 노출을 금지한다.
8. 계약 변경은 새 version과 compatibility 판정을 남긴다. 과거 의미를 같은 version으로 바꾸지 않는다.

필수 ID namespace는 `source.`, `collection.`, `dataset.`, `metric.`, `pipeline.`, `read_model.`, `macro.`,
`etf_profile.`, `etf_route.`이다. version은 semantic
version 문자열을 사용한다. v1 manifest의 필수 필드와 enum은 `governance/contract-schema.toml`이 소유한다.

외부 source나 upstream dataset이 없는 runtime Control 증거는 예외적으로 `layer=control`이면서
`control_origin=managed-pipeline-runtime`인 dataset만 허용한다. 이는 managed pipeline 자체가 생성하는 run
ledger에만 적용되며 source-less analytics dataset을 허용하지 않는다.

ETF provider rights는 `allowed`, `prohibited`, `unknown`의 tri-state다. production profile은 automation,
cloud processing, raw retention과 derived use가 모두 `allowed`여야 한다. exact route에는 계좌, 보유수량,
평가액을 넣지 않으며 name/brand heuristic은 provider를 선택할 수 없다. fixture-only profile과 route는 합성
payload parser 검증에만 사용할 수 있고 network registry에는 등록되지 않는다.

## 5. Gate architecture

### 5.1 Design-time gate

- manifest parse, 필수 필드, ID/version/status와 enum 검증
- 중복 ID와 존재하지 않는 cross-reference 거부
- 승인 근거 없는 approved/active 계약 거부
- source 없는 collection, 입력 없는 metric, 출력 없는 pipeline 거부
- source/input 없는 dataset은 allowlisted managed-runtime Control origin이 아니면 거부
- read model의 allow/suppress field 중복, 256 KiB 초과 응답, 비양수 page·음수 lookback과 active input 없는
  production activation 거부
- 중복 macro provider identity, source가 누락된 profile 참조와 active source 없는 production macro series 거부
- physical object 변경 시 dataset contract와 data catalog 동시 변경 요구
- SSOT, grain, key, retention, lineage, provider, 비용 단계 변경 시 ADR gate 요구

### 5.2 Commit과 CI gate

`.agent/skills/kis-data-governance/scripts/check_data_governance.py`가 결정적 검사 엔진이다.
`scripts/check.sh`의 staged, quick, full mode와 Git hook·CI가 같은 엔진을 호출한다. Skill은 이 정책을
복제하지 않고 문서를 읽은 뒤 공통 하네스를 실행한다.

현재 checker는 repository contract의 구조, lifecycle, 참조 무결성을 강제한다. 미래 source와 pipeline
구현은 checker를 우회하지 않고 같은 registry를 runtime catalog 입력으로 사용한다.

### 5.3 Migration과 release gate

- runtime auto-DDL을 제거하고 checksum을 가진 versioned migration만 schema를 변경한다.
- temporary DuckDB와 temporary MotherDuck에서 migration, view compile과 rollback을 검증한다.
- row count, key uniqueness, null, 합계 reconciliation과 backup/restore를 확인한다.
- live inventory가 registry와 다르면 release를 실패시킨다. 알려진 drift 통합 전에는 drift register로
  격리하고 공식 consumer가 사용하지 않는다.
- destructive migration은 별도 Work Item, backup, 영향·rollback과 사용자 승인이 필요하다.

### 5.4 Runtime quality와 publish gate

pipeline은 `collect → land → normalize → reconcile → quality → publish → evaluate → deliver`의 적용 stage와
생략 이유를 기록한다. 각 run/stage는 최소한 다음 evidence를 남긴다.

- contract와 code version, logical date/slot/partition, idempotency key
- source/effective/fetched time과 input/output watermark
- request/object/row count, content hash와 pagination coverage
- retry, rate-limit/call budget, partial/empty/error 구분
- freshness, completeness, uniqueness, reconciliation과 domain quality result
- input/output dataset version과 lineage edge

Bronze observation은 source의 partial 결과를 사실대로 보존할 수 있다. Silver canonical publish, Gold,
metric, signal과 Telegram은 해당 계약의 quality gate를 통과해야 한다. 제한적으로 사용한 partial/stale
결과는 응답에 status, missing coverage와 lineage를 표시하고 정상으로 가장하지 않는다.

### 5.5 Consumer와 MCP gate

Remote MCP의 관리 데이터 조회는 다음 read model을 목표로 한다.

- `get-data-catalog`: source/dataset/metric/pipeline/macro series와 physical object의 grain, version, owner와 지원 범위
- `get-data-quality`: freshness, completeness, reconciliation, known gap
- `get-pipeline-run`: run/stage/watermark와 재처리 가능 상태

분석 응답은 `schema_version`, `as_of`, `source`, `freshness`, `quality`, `missing_coverage`, `lineage_ref`,
`request_id`를 공통 envelope로 가진다. LLM은 임의 SQL writer나 임의 Job argument를 받지 않고 승인된
read model과 allowlisted managed pipeline만 사용한다.

초기 계약은 `read_model.data-catalog-v1`, `read_model.data-quality-v1`, `read_model.pipeline-run-v1`이며 모두
owner 승인 상태지만 runtime `inactive`다. 요청 중 provider call을 하지 않고 packaged canonical manifest와
MotherDuck Control 증거만 읽는다. serialized response는 256 KiB 이하이고 query page/lookback은 계약 상한을
넘지 않는다. raw JSON, error text, partition key, raw lineage/object locator, secret/auth/cost internals은
suppressed field다. 전체 상태는 `unavailable > failed > partial > stale > not_assessed > pass` 순서로 합성하며
succeeded run, 빈 결과나 증거 부재만으로 `pass`를 만들지 않는다. Public MCP 등록과 OAuth adapter는 WI-042가
별도로 소유한다.

## 6. 권한, 보안과 예외

- source credential과 bearer token은 manifest, catalog, logs, raw landing과 MCP 응답에 넣지 않는다.
- sensitivity와 license class는 저장 위치, backup, MCP 노출과 외부 전송을 제한한다.
- `restricted`는 유료 여부가 아니라 이용조건·저작권·재배포·처리 권한에 따른 법적/사용 제한이다.
  무료 공개 다운로드도 `restricted`일 수 있고, 유료 여부는 별도 `cost_class`와 비용 gate가 판단한다.
- current `main` schema 기간에는 application allowlist로 논리 통제한다. V2 schema 분리 뒤 runtime identity는
  필요한 schema의 DML만 받고 migration identity만 DDL을 가진다.
- Security state는 V2 승인대로 Firestore/Secret Manager로 이동하며 일반 analytics catalog에서 제외한다.
- emergency exception은 incident/Work Item ID, 사유, 범위, owner, 시작·만료, 보완 통제와 사후 reconciliation을
  가져야 한다. 영구 bypass나 silent allowlist 확장은 금지한다.

## 7. 변경 분류와 compatibility

다음 변경은 architecture impact를 가진다.

- canonical source, SSOT, grain, natural key 또는 time semantics 변경
- retention 단축, destructive migration, sensitivity/license 완화
- quality publish gate 완화 또는 lineage 단절
- 새 provider, warehouse, orchestrator, 상시 service나 월비용 단계 추가

column 추가처럼 호환 가능한 변경도 contract version과 consumer 영향을 기록한다. breaking 변경은 새 major
version, migration, dual-run/reconciliation과 cutover 승인을 요구한다. deprecated/retired 계약의 데이터는
자동 삭제하지 않는다.

## 8. 운영 cadence와 증거

| 주기 | 검토 |
| --- | --- |
| 매 pipeline run | idempotency, freshness, quality, lineage, publish 결과 |
| 매일 | stale/missing dataset, failed stage, reconciliation gap, backup 결과 |
| 매월 | source·dataset drift, capacity·cost, deprecated consumer, exception 만료 |
| 분기 | restore rehearsal, source API/license, IAM/service account, retention·삭제 후보 |
| release | manifest/DDL/repository/backup/live inventory, remote/batch smoke, rollback |

증거 없는 green 상태를 만들지 않는다. query history가 unavailable한 plan 제약도 quality/operability gap으로
기록한다. 운영 데이터와 코드가 어긋나면 자동 채택·삭제하지 않고 drift로 격리해 provenance와 consumer를
먼저 확인한다.

## 9. 도구 채택 원칙

초기 하네스는 Git, TOML manifest, Python checker, DuckDB/MotherDuck SQL, GitHub Actions와 기존 Project OS를
사용한다. 이는 비용 0에 가깝고 코드·결정과 동일한 review 경계를 제공한다.

Silver/Gold SQL model과 lineage가 충분히 커지면 dbt Core 또는 SQLMesh를 별도 Work Item에서 비교한다.
도입하더라도 이 문서와 contract registry가 결정 SSOT이며, transformation tool은 execution·test·artifact
producer다. OpenMetadata, DataHub, Collibra 같은 catalog platform은 다중 팀, 외부 consumer, 자동 discovery,
세밀한 RBAC·감사 요구가 실제로 생길 때 검토한다.

## 10. 적용 단계

### Phase 0 — 지금 활성화

- canonical 정책, machine schema와 빈 registry
- DGH Skill, deterministic checker, hook·CI 연결
- 기존 physical data catalog와 V2 계획의 선행 계약 연결

### Phase 1 — source catalog와 collection basket

- KIS/OpenDART/SEC/ECOS/FRED/Cboe/ETF/consensus 후보를 source contract로 조사
- 필수/권장/후순위/제외를 collection contract로 승인
- dataset grain, history, schedule, license, capacity·cost 산정

### Phase 2 — V2 warehouse와 pipeline runtime

- versioned migrations와 physical schemas
- pipeline/run/stage/watermark/quality/lineage control objects
- runtime publish gate, daily quality와 managed backfill

### Phase 3 — governed consumption

- MCP catalog/quality/pipeline read model
- metric/signals point-in-time contract와 Telegram quality gate
- 필요 시 dbt/SQLMesh 또는 external catalog 도입 gate 재평가

이 문서의 활성화는 Phase 1~3 구현, 외부 provider 계약, production migration, backfill 또는 deployment를
승인하지 않는다. 각 단계는 별도 Work Item과 Project OS gate를 거친다.
