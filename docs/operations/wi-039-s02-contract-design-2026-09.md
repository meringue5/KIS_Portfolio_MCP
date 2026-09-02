# WI-039-S02 macro profile contract design — 2026-09-02

> Work Item: `WI-039-S02`
> 상태: owner decision ready
> 변경 분류: architecture and data-contract clarification
> 범위: approved requirements/contracts, WI-039-S01 evidence and current official provider documentation에 대한 선행 설계
> 제외: source API call, credential use, contract lifecycle 변경, DDL, DB write, pipeline activation, schedule, MCP

## 결론

`macro_profile_v1`은 승인 요구사항 C-5에 적힌 17개 개념으로 고정한다. collection의 일반적인 예시에만 있던
한국 M2와 미국 산업생산은 v1에 추가하지 않고, 향후 profile version과 metric/source contract 승인을
거쳐야 한다.

- 한국 5개: 기준금리, USD/KRW, headline CPI, 산업생산, 수출.
- 미국·글로벌 12개: DFF, DGS2, DGS10, T10Y2Y, CPIAUCSL, CPILFESL, UNRATE, PAYEMS, GDPC1,
  DTWEXBGS, DCOILWTICO, VIXCLS.

미국·글로벌 transport는 FRED/ALFRED로 단일화한다. `VIXCLS`의 underlying owner와 attribution은 Cboe로
보존하지만 direct Cboe historical-file automation은 초기 v1에서 사용하지 않는다. FRED가 제공하는 API와
vintage semantics를 공통으로 사용하면서, Cboe 저작권 series는 owner-only private analysis와 attribution,
raw redistribution 금지로 제한한다.

ECOS 5개는 개념만 고정하고 exact table/item/cycle/unit은 아직 allowlist로 승인하지 않는다. 기억한 code나
third-party library 상수를 canonical로 복사하지 않고, 후속 `WI-039-S03`에서 official metadata discovery와
각 series 1회 bounded sample을 실행해 exact identity를 채운다. 따라서 이번 S02는 architecture와 contract
shape는 owner decision ready지만, canonical adoption은 S03 evidence 뒤의 S04가 담당한다.

이 설계는 profile scope, source transport, revision identity, natural key와 time semantics를 바꾸므로 제안
ADR-027과 major dataset/pipeline contract 변경이 필요하다. 이번 S02는 승인안을 만들 뿐 승인·활성화하지 않는다.

## 근거

### 승인 요구와 현재 충돌

- DEC-024는 공식 ECOS·FRED/ALFRED·Cboe source, standard macro profile과 versioned interpretation을 승인했다.
- C-5의 명시적 범위는 한국 5개와 미국·글로벌 12개다. 현재 collection 설명의 liquidity/M2와 U.S.
  industrial activity는 이 목록과 일치하지 않는다.
- `dataset.macro-observation` 1.0.0은 모든 source에 `realtime_start`와 `source_revision`을 사실상 강제하지만,
  ECOS와 file download는 ALFRED와 같은 provider vintage interval을 제공하지 않는다.
- `silver.macro_observations` foundation은 publication time, fetched/knowledge clock, native metadata, rights와
  source-specific revision kind를 충분히 표현하지 못한다.
- raw source fact와 `긴축/완화`, `물가 압력`, `성장 둔화/회복`, `달러 강세/약세`, `위험회피` 해석은 아직
  별도 metric/version contract로 분리돼 있지 않다.

### 공식 reference 재확인

- [FRED API terms](https://fred.stlouisfed.org/docs/api/terms_of_use.html)은 third-party series의 권리가 API
  제공만으로 소멸하지 않으며 personal use 밖의 사용은 원 소유자 조건을 따라야 한다고 명시한다.
- [FRED observations](https://fred.stlouisfed.org/docs/api/fred/series_observations.html)은 realtime interval과
  vintage-date query를 제공하고, [vintage dates](https://fred.stlouisfed.org/docs/api/fred/series_vintagedates.html)는
  값이 신규 공개되거나 수정된 날짜를 열거한다.
- [FRED VIXCLS](https://fred.stlouisfed.org/series/VIXCLS)는 source owner가 Cboe이고 daily close, index,
  non-seasonally-adjusted이며 copyrighted/citation-required임을 표시한다.
- [FRED DGS10](https://fred.stlouisfed.org/series/DGS10)은 Federal Reserve Board source의 daily public-domain
  series이고, [DCOILWTICO](https://fred.stlouisfed.org/series/DCOILWTICO)는 EIA source와 citation을 표시한다.
- [ECOS Open API](https://ecos.bok.or.kr/api/)는 table/item metadata와 statistic search를 분리한다. 공식
  metadata와 sample response 없이 table/item code를 추정하지 않는다.

## 제안 ADR-027

### Decision

`macro_profile_v1`을 17개 exact concept의 versioned series registry로 고정한다. raw observation은 하나의
heterogeneous append-only revision ledger를 사용하되 provider vintage interval은 nullable로 두고, 모든
source에 non-null typed `revision_key`, `revision_kind`, `knowledge_at`과 `fetched_at`을 요구한다.

미국·글로벌 series는 FRED/ALFRED API를 transport로 사용한다. VIX의 data owner는 Cboe로 유지하며 source
owner, copyright, citation과 permitted consumer를 series contract에 보존한다. direct Cboe download adapter는
initial v1에서 비활성이다. 한국 series는 ECOS official metadata sample이 통과한 exact identity만 등록한다.

### Consequences

- collection과 pipeline의 source transport가 ECOS + FRED/ALFRED로 좁아진다. `source.cboe-vix`는 삭제하지
  않고 approved reference/dormant contract로 남긴다.
- 기존 macro observation contract는 2.0.0 major version이 필요하다. provider realtime field를 가짜 값으로
  채우지 않고 typed source-specific revision을 사용한다.
- series definition은 governance-as-code와 target Control projection을 함께 가진다. arbitrary series ID,
  user URL과 provider-side transform parameter는 runtime input이 될 수 없다.
- raw native value와 단위는 그대로 보존한다. 변화율, spread, regime tag와 설명은 versioned metric/Gold
  projection이며 source fact를 덮어쓰지 않는다.
- 기존 empty foundation이 non-zero거나 consumer가 발견되면 자동 변환하지 않고 별도 mapping/reconciliation
  gate에서 중단한다.

## Frozen profile scope

### United States and global — exact candidate allowlist

| Contract ID | Provider ID | Native frequency / unit | Owner / initial use boundary |
| --- | --- | --- | --- |
| `macro.us.effective-fed-funds` | `DFF` | daily / percent, NSA | Federal Reserve Bank of New York via FRED; level, not target midpoint |
| `macro.us.treasury-2y` | `DGS2` | daily / percent, NSA | Federal Reserve Board via FRED; citation retained |
| `macro.us.treasury-10y` | `DGS10` | daily / percent, NSA | Federal Reserve Board via FRED; citation retained |
| `macro.us.treasury-10y-minus-2y` | `T10Y2Y` | daily / percentage points | FRED derived spread; component lineage retained |
| `macro.us.cpi-headline` | `CPIAUCSL` | monthly / index, SA | BLS via FRED; YoY is derived |
| `macro.us.cpi-core` | `CPILFESL` | monthly / index, SA | BLS via FRED; YoY is derived |
| `macro.us.unemployment` | `UNRATE` | monthly / percent, SA | BLS via FRED; level context |
| `macro.us.nonfarm-payrolls` | `PAYEMS` | monthly / thousands, SA | BLS via FRED; MoM change derived |
| `macro.us.real-gdp` | `GDPC1` | quarterly / chained 2017 USD billions, SAAR | BEA via FRED; growth derived and vintage-sensitive |
| `macro.us.broad-dollar` | `DTWEXBGS` | daily / index, NSA | Federal Reserve Board via FRED; not USD/KRW |
| `macro.global.wti-spot` | `DCOILWTICO` | daily / USD per barrel, NSA | EIA via FRED; citation retained |
| `macro.us.vix-close` | `VIXCLS` | trading day / index close, NSA | Cboe via FRED; copyrighted, citation-required, owner-only |

Formal adoption revalidates each FRED series metadata, owner, copyright note and citation on the adoption date. A series
whose rights field is missing or changed remains inactive even if its ID and values are available.

### Korea — concepts frozen, exact identity pending S03

| Contract ID | Concept | Preferred native observation | S03 evidence required |
| --- | --- | --- | --- |
| `macro.kr.base-rate` | 한국은행 기준금리 | effective-date level / percent | table/item/cycle/unit, date precision and revision behavior |
| `macro.kr.usd-krw` | 원/미국달러 환율 | daily KRW per USD | rate type, market/fixing basis, holiday and unit |
| `macro.kr.cpi-headline` | 소비자물가지수 | monthly native index | base year, SA/NSA, publication lag and revisions |
| `macro.kr.industrial-production` | 산업생산 | monthly native index | exact total-industry concept, SA/NSA and base year |
| `macro.kr.exports` | 수출 | monthly native amount/index | customs/BOP basis, currency, nominal/real and revision behavior |

S03 is metadata-only plus one bounded sample per concept. It records only redacted schema/metadata evidence and no API
key. Ambiguous concept, multiple plausible items, unexpected unit/frequency or missing rights metadata fails closed and
returns the choice to the owner; it does not silently select the first row.

## Series definition contract

A new machine-readable `macro_series` contract kind is proposed. It is a governance control, not a generic discovery
API. Required fields are:

```text
id, version, status, owner, decision_refs
source_id, provider_series_id, source_owner, source_license_class
region, concept, native_frequency, native_unit, seasonal_adjustment
vintage_capability, publication_cadence, expected_lag, history_start
rights_note, attribution, permitted_consumers, transform_policy
activation_state, valid_from
```

The DGH checker must reject duplicate provider identity, unknown unit/frequency/rights, active series on an inactive
source, and collection/pipeline references to unapproved series. The target Control projection stores definition hash,
not credentials. Runtime accepts only registry ID/version and logical partition; arbitrary provider series IDs are denied.

## Observation revision and point-in-time contract

| Field | Contract |
| --- | --- |
| identity | `series_contract_id + observation_period + revision_key` |
| revision kind | `provider_vintage` or `observed_content`; never inferred from source name alone |
| provider interval | `source_realtime_start/end` nullable and allowed only when source supplies it |
| source availability | source publication/vintage date and precision, when verified |
| system clock | monotonic `knowledge_at`; backfilled observations first known now do not become historical knowledge |
| fetch clock | actual `fetched_at`, request/run/partition and content hash |
| native fact | decimal value or explicit source missing marker, native unit/frequency/seasonal adjustment |
| current view | latest eligible revision by explicit `system_as_of`; retrospective source mode separately labeled |

FRED/ALFRED monthly and quarterly series may use official vintage dates for retrospective research, but production
signals and operational replay default to system knowledge. Daily series initial history is
`retrospective_reconstructed`; it becomes operational-strict only through forward collection. ECOS has no fabricated
realtime interval: `observed_content` revisions append when the governed fetch observes a content change.

Missing source values remain typed missing observations when the provider explicitly returns them. Absence caused by a
closed market, unreleased period, pagination gap, rate limit or source failure is quality state, not a zero or row deletion.

## Raw facts, transforms and regime interpretation

Initial raw collection and initial interpretation remain separate delivery steps.

1. Raw: all 17 native levels with source identity, clocks, rights and quality.
2. Transparent transforms: CPI and selected activity YoY, payroll MoM delta, GDP QoQ annualized growth, provider yield
   spread, and native-level/delta context for rates, FX, dollar and WTI.
3. Regime context: yield-curve state and VIX `<20`, `20–<30`, `30–<40`, `>=40` labels; these are context, not orders.
4. Composite tags: tightening/easing, inflation pressure, growth/labor, dollar/commodity and risk-off remain `unknown`
   until their exact formula/version, minimum inputs and historical validation are approved.

Proposed metric contracts for the first implementation are:

- `metric.macro-yoy-percent-change`
- `metric.macro-period-delta`
- `metric.macro-quarterly-annualized-growth`
- `metric.macro-yield-curve-state`
- `metric.macro-vix-regime`

Every metric selects observation revisions at `evaluation_at`, carries input series/version/revision lineage, and returns
`unknown` for missing, stale, rights-blocked or insufficient-history input. No forward-fill crosses an expected release
gap without a future explicit metric rule.

## Proposed DGH contract delta

Owner approval and S03 evidence precede canonical adoption. All producer contracts start `approved + inactive`.

| Contract | Version | Change |
| --- | --- | --- |
| DGH `macro_series` kind | schema v1 extension | exact series identity, rights, cadence, transform and activation contract |
| `source.fred-alfred` | 1.1.0 | owner-only third-party boundary, attribution and VIX transport clarification |
| `source.cboe-vix` | 1.1.0 | direct download dormant/reference; no initial production calls |
| `collection.macro-profile-v1` | 2.0.0 | exact 17-concept scope; M2/U.S. industrial activity excluded |
| 17 `macro_series.*` contracts | 1.0.0 | 12 exact FRED candidates + 5 S03-verified ECOS identities |
| `dataset.macro-observation` | 2.0.0 | typed heterogeneous revision, dual clocks, native metadata and rights |
| `dataset.macro-profile-snapshot` | 1.0.0 | rebuildable Gold metric/tag/coverage read model |
| five `metric.macro-*` contracts | 1.0.0 | transparent transforms, curve and VIX context only |
| `pipeline.macro-profile-v2` | 2.0.0 | registry-only source partitions, budgets, resume and publish gates |

Contract count is intentionally not frozen until S03 resolves the five ECOS identities and compatibility review. S04
will list the exact delta and registered-contract total before owner adoption.

## Proposed physical migration 0016

ADR-025 migration 0014 and ADR-026 migration 0015 are reserved predecessors. Macro uses additive
`0016_macro_profile.sql`.

| Layer | Proposed objects |
| --- | --- |
| Control | `macro_series_definitions` with contract/version/hash/validity and rights metadata |
| Silver | `macro_observation_revisions`, `macro_observations_current`, `macro_observations_as_of` |
| Gold | existing `metric_values` for approved macro metrics; `macro_profile_snapshots` rebuildable projection |

Preflight checks legacy `silver.macro_observations` row count, definition hash, known consumers and backup manifest. Any
non-zero or unknown result stops automatic conversion. Migration does not drop, rename or update legacy objects. Rollback
keeps new objects abandoned/inactive and restores the prior runtime registry; deletion needs separate approval.

## Pipeline, schedule, budget and capacity

`pipeline.macro-profile-v2` stages are `resolve-registry → check-release → collect → normalize → quality → publish →
evaluate → materialize-profile`. Release checks are optimizations, not completeness evidence. Each source/series/logical
period has an independent watermark and resume key.

### Recommended limits

| Control | Routine | Initial/backfill |
| --- | ---: | ---: |
| FRED physical calls | scheduled day 32 | day 256, series/partition 10 pages |
| ECOS physical calls | scheduled day 16 | day 96, series/partition 10 pages; enabled only after S03 |
| direct Cboe calls | 0 | 0 |
| concurrency | source sequential; shared bounded HTTP policy | same |
| history | changed/released allowlisted partitions | three years plus bounded ALFRED vintages for monthly/quarterly series |

Every physical attempt is durably reserved before I/O. 429, auth, unexpected metadata, repeated cursor/page, budget
exhaustion and response-shape drift fail closed. Retry is idempotent GET only, maximum two attempts for timeout/network/
429/5xx with `Retry-After`; auth/schema/rights errors have no same-run retry.

Candidate schedule is one weekday scale-to-zero Job at 09:00 KST. It evaluates source-native publication cadence and
does not fetch unchanged monthly/quarterly series merely because the Job ran. Korean releases published after the slot
are eligible on the next weekday run. Exact Scheduler activation and catch-up policy remain release decisions.

Initial stop lines are 512 MiB of macro Bronze observations/metadata, 500,000 Silver revision rows and 100,000 Gold
metric/profile rows. Review opens at 80%; backfill stops at 100% while bounded routine correction/freshness may continue
only under a recorded capacity exception. With 17 series and three years, these are anomaly/duplication circuit breakers,
not expected usage. First 30 production days must replace the estimate with observed byte/row/call growth.

## Rights, security and consumer boundary

- ECOS/FRED keys remain Secret Manager values and never enter the registry, warehouse, backup, log or MCP response.
- FRED third-party owner, copyright and citation fields are retained per series and re-reviewed quarterly or when metadata
  changes. Required application notice and terms link are exposed in the private data catalog.
- VIXCLS raw values and copyrighted source notes are for the owner-only private service. Telegram may receive only an
  allowlisted derived regime label and source attribution, never bulk/raw history.
- Remote MCP returns bounded owner-authenticated read models with source, as-of, rights/attribution and quality. It is not
  a public data redistribution endpoint or arbitrary series query.
- ECOS/FRED raw responses are not placed in Telegram. Bronze persistence is limited to fields and response evidence
  allowed by the series contract; credentials and provider free text are redacted.

## Quality and verification gate

- fixture set: daily missing marker, monthly/quarterly revision, late release, ECOS content change, rights block,
  unexpected unit/base year, rate limit, repeated page, partial source and stale profile.
- uniqueness: series/period/revision key and one current row per explicit cutoff.
- PIT: backfilled and later revised values are absent from earlier `system_as_of`; retrospective mode is labeled.
- metadata: source owner, native unit/frequency/seasonal adjustment, rights and attribution match series definition.
- transform: Decimal golden fixtures for YoY, delta and annualized growth; no division by zero or implicit forward-fill.
- regime: exact yield-curve and VIX boundary tests; missing/stale input yields `unknown` and never a trade action.
- restore: Parquet Control/Silver/Gold restore with definition hash, row count, current/as-of view and metric reconciliation.
- full Project OS/DGH/warehouse gate. Production API, DB, schedule and Remote MCP smoke are later release evidence.

## Owner decision package

다음 여덟 항목을 한 묶음으로 승인 또는 수정한다.

1. `macro_profile_v1`을 C-5의 한국 5개 + 미국·글로벌 12개로 고정하고 M2/U.S. industrial production 제외.
2. 미국·글로벌 transport를 FRED/ALFRED로 단일화하고 VIX는 Cboe-owned `VIXCLS`, direct Cboe calls 0.
3. typed heterogeneous revision ledger, nullable provider realtime interval, `system_as_of` default와 labeled retrospective mode.
4. `macro_series` governance contract kind와 registry-only runtime input; arbitrary series/query 금지.
5. raw facts와 five transparent metric contracts 분리; composite causal/trade interpretation은 later.
6. additive migration 0016과 legacy empty-foundation fail-closed preflight.
7. FRED 32/256, ECOS 16/96, 10-page cap, 512 MiB/500k/100k stop lines와 09:00 KST candidate cadence.
8. owner-only rights/attribution boundary, scale-to-zero shared runtime, no separate service/repository/always-on worker.

승인 뒤 `WI-039-S03`에서 credential value를 기록하지 않는 bounded ECOS metadata/sample verification을 수행한다.
그 결과와 exact five-series identity를 다시 보여준 뒤 `WI-039-S04`에서 ADR·requirements clarification·DGH
contracts를 canonical SSOT에 채택한다. MS-002가 닫히고 MS-003 formal gate가 열린 뒤에만 migration, adapter,
repository, fixture와 backfill implementation을 시작한다.

## Evidence and limits

- Repository requirements, S01 research, physical foundation, DGH contracts and current official provider documents를
  검토했다.
- FRED official pages confirm API vintage semantics, third-party rights boundary and VIXCLS owner/copyright metadata.
- source API, credential, account data, live DB와 Secret Manager를 사용하지 않았다. Exact ECOS table/item identity,
  current response shape and numeric provider limits are not claimed.
- contract status/version, checker schema, DDL, data, infrastructure, schedule, source activation and MCP surface를
  바꾸지 않았다.

## Verification

- `python3 .agent/skills/kis-data-governance/scripts/check_data_governance.py`: passed, 129 registered contracts
- `bash scripts/check.sh quick`: passed
- `bash scripts/check.sh full`: passed, 438 tests and 1 existing Authlib deprecation warning
