# WI-039 macro profile pipeline pre-research — 2026-09-01

> Work Item: `WI-039-S01`
> 범위: repository와 공식 provider 문서에 대한 read-only research
> 변경 경계: source API call, credential use, contract lifecycle, DDL, DB write, pipeline, schedule와 MCP 변경 없음

## 결론

WI-039의 approved source·dataset·pipeline 계약과 `silver.macro_observations` 물리 기반은 이미 존재한다. 그러나
현재 상태에서 series allowlist를 활성화하면 안 된다.

- 요구사항 본문은 한국 기준금리·USD/KRW·CPI·산업생산·수출과 미국 effective policy rate·2Y·10Y·spread·
  headline/core CPI·unemployment·nonfarm payrolls·real GDP·broad dollar·WTI·VIX를 요구한다.
- governance 수집 장바구니는 한국 M2와 미국 industrial activity를 예시로 들지만 수출, nonfarm payrolls,
  real GDP와 WTI를 빠뜨린다. 요구사항과 장바구니가 동일한 profile을 가리키지 않는다.
- FRED 후보 ID는 공식 series page에서 검증할 수 있지만, ECOS 통계표·항목 코드는 공식 metadata discovery와
  sample response 없이 추정해서는 안 된다.
- FRED/ALFRED는 realtime vintage를 제공하지만 ECOS와 Cboe download는 동일한 revision identity를 보장하지
  않는다. 그런데 현재 logical/physical key는 모든 source에 `realtime_start`와 `source_revision`을 강제한다.
- Cboe page는 VIX의 의미와 historical-data entry를 제공하지만, 자동 다운로드·저장·MCP 제공 범위는 별도
  usage review가 끝나야 한다. FRED도 API 이용권이 underlying third-party series 권리를 대신 부여하지 않는다.

따라서 이번 조사에서는 미국 후보군, source별 point-in-time 전략, 예산과 fail-closed 조건만 implementation
input으로 고정한다. parent WI-039와 MS-003은 계속 `proposed`이며, profile/contract 활성화는 formal gate 뒤다.

## 현재 기반과 결손

| Area | Existing input | Gap before implementation |
| --- | --- | --- |
| source | approved ECOS, FRED/ALFRED, Cboe contracts | per-series rights, owner, exact endpoint/item and attribution record absent |
| collection | approved `collection.macro-profile-v1` concept basket | approved requirements와 개념 범위 불일치; exact allowlist absent |
| dataset | approved `dataset.macro-observation` | heterogeneous revision identity and publication timestamp not fully modeled |
| physical table | `silver.macro_observations` | `realtime_start` mandatory; publication time, fetched_at, frequency, seasonal adjustment and license fields absent |
| pipeline | approved cadence-aware `pipeline.macro-profile-v2` | adapter, metadata cache, per-source budget, watermark and schedule absent |
| interpretation | versioned regime requirement | source observation과 derived transform/tag contract 분리 미완료 |
| secrets | source contract requires ECOS/FRED keys | provisioning and runtime binding are formal implementation scope, not verified here |

Repository search found no macro source adapter, governed series manifest, collection schedule or macro repository. The
foundation DDL alone is not evidence that a production dataset exists. Live MotherDuck inspection was not repeated after
WI-040-S01's two session-creation `UNAVAILABLE` results, so this research makes no live row-count or freshness claim.

## Candidate `macro_profile_v1`

### United States and global candidates

These IDs are candidate inputs, not an activated allowlist. Native values are stored unchanged; YoY, change and regime
labels are separate versioned metrics.

| Contract ID candidate | Provider ID | Native frequency / unit | Role and boundary |
| --- | --- | --- | --- |
| `macro.us.effective-fed-funds` | `DFF` | daily / percent, NSA | effective traded rate; do not label it FOMC target midpoint |
| `macro.us.treasury-2y` | `DGS2` | daily / percent, NSA | 2-year constant maturity yield |
| `macro.us.treasury-10y` | `DGS10` | daily / percent, NSA | 10-year constant maturity yield |
| `macro.us.treasury-10y-minus-2y` | `T10Y2Y` | daily / percent, NSA | provider-calculated spread; retain underlying-series provenance |
| `macro.us.cpi-headline` | `CPIAUCSL` | monthly / index 1982-84=100, SA | raw headline index; inflation rate is derived |
| `macro.us.cpi-core` | `CPILFESL` | monthly / index 1982-84=100, SA | raw CPI less food and energy; inflation rate is derived |
| `macro.us.unemployment` | `UNRATE` | monthly / percent, SA | unemployment context, not a direct market signal |
| `macro.us.nonfarm-payrolls` | `PAYEMS` | monthly / thousands of persons, SA | level; monthly change is derived |
| `macro.us.real-gdp` | `GDPC1` | quarterly / chained 2017 USD billions, SAAR | level; growth is derived and vintage-sensitive |
| `macro.us.broad-dollar` | `DTWEXBGS` | daily / Jan 2006=100, NSA | broad dollar context; not USD/KRW replacement |
| `macro.global.wti-spot` | `DCOILWTICO` | daily / USD per barrel, NSA | EIA WTI spot observation distributed through FRED |
| `macro.us.vix-close` | Cboe VIX daily history | trading day / index | near-term implied-volatility context; not direction or realized volatility |

The FRED series pages confirm each candidate's source, native frequency and unit. They also mark series as revisable and
carry source-specific copyright/citation notes. Formal activation therefore requires a frozen metadata snapshot and
per-series `source_owner`, `license_class`, attribution and permitted consumer fields.

### Korea candidates

The approved concepts remain:

1. Bank of Korea base rate;
2. USD/KRW;
3. headline CPI;
4. industrial production/activity;
5. exports.

Exact ECOS table code, item code, frequency, unit, seasonal adjustment and publication lag remain **unresolved**. No code
such as a remembered `...Y...` identifier may enter the allowlist until an authenticated metadata-only discovery records
the official `StatisticTableList`/`StatisticItemList` response and one bounded sample. The formal WI must also decide
whether Korean M2 is an additional requirement or whether its collection-basket mention is removed. It must similarly
resolve whether the U.S. industrial-activity example is additional to the approved real-GDP series.

## Point-in-time and revision contract

The following timestamps are distinct and must never be substituted for one another:

- `observation_period`: the economic period represented by the value;
- `published_at`: source publication time when the source exposes it;
- `realtime_start` / `realtime_end`: FRED/ALFRED knowledge-validity interval;
- `knowledge_at`: earliest defensible time this system could know the source value;
- `fetched_at`: collector observation time;
- `revision_key`: stable source-specific identity for the observed version.

For FRED/ALFRED, the observations endpoint supports realtime ranges and vintage dates, and the vintage-dates endpoint
enumerates revision dates. Backfill/replay should use these fields rather than today's revised history. For sources without
provider vintages, a historical download performed today has `knowledge_at=fetched_at`; it must not be portrayed as what
the system knew in the past. A content hash can detect changes but does not prove a historical publication time.

The present natural key and DDL require non-null `realtime_start` and `source_revision` for every source. Formal WI-039
must approve one of these before adapter work:

1. make provider realtime dates nullable and use a non-null typed `revision_key`; or
2. split vintage-aware observations from latest-only source observations and publish a union read model.

Fabricating `realtime_start` from fetch date is rejected. Publication time, fetched_at, frequency, seasonal adjustment,
source owner, license decision and raw provenance also need governed fields or linked metadata contracts.

## Call budget, cadence and cost

The collector remains batch-first and scale-to-zero.

- FRED/ALFRED: cache series metadata and release mapping; use a daily bounded update check, then fetch only allowlisted
  series whose release/update window opened. `series/updates` covers only the last two weeks, so it is an optimization,
  not a completeness ledger. Initial working cap: 32 API requests per scheduled day; backfill uses a separately approved
  page budget and resumable watermark.
- ECOS: first run a bounded metadata discovery after key provisioning, then schedule by native cadence. A numeric cap is
  not approved until current official key/rate policy and exact item shapes are sampled.
- Cboe: at most one conditional retrieval after the U.S. close, content-hash deduplicated. No repeated intraday polling.
- All sources: budget exhaustion, missing metadata, unknown license, unexpected unit/frequency, malformed revision or
  missing expected release produces `partial`/`blocked`, never an empty success.

Even with three years of daily history and all macro vintages, this small allowlist is negligible beside market-price and
portfolio facts. Network calls, correctness and rights review—not MotherDuck storage—are the controlling constraints.

## Interpretation boundary

Source facts and interpretations are separate products. `tightening/easing`, inflation pressure, growth slowdown/recovery,
dollar strength/weakness and risk-off tags need metric IDs, formula/version, input vintages, evaluation time and quality.
VIX 20/30/40 may remain versioned regime thresholds, but VIX alone cannot create a buy/sell decision. Missing or stale
inputs yield `unknown`; no forward-fill crosses an expected publication gap without an explicit rule.

## Contract hardening gate

Formal WI-039 should resolve these items before implementation:

1. Reconcile the approved requirements and collection basket, then freeze one profile version with exact concepts.
2. Run ECOS metadata discovery and bounded samples; freeze exact table/item IDs, native metadata and publication lags.
3. Freeze the verified FRED IDs above and review every underlying series rights/citation note.
4. Complete Cboe usage/attribution review for automated private storage and bounded MCP-derived output.
5. Choose the heterogeneous revision model and update dataset contract, DDL, physical catalog, migration and backup in
   one governed change.
6. Add a versioned series-manifest contract containing provider ID, owner, frequency, unit, seasonal adjustment, cadence,
   vintage capability, start date, rights, attribution, transform policy and active state.
7. Freeze source-specific call/page budgets, freshness windows, expected-release gaps and fail-closed error taxonomy.
8. Define derived transform/regime metric contracts separately from raw observations.
9. Provision ECOS/FRED secrets only after the contracts are ready, then implement adapters and replay under the formal WI.

## Suggested implementation sequence

1. Contract-hardening decision and exact series manifest.
2. Source metadata clients and fixtures with credentials excluded from evidence.
3. Revision-safe repository/migration plus unit, frequency, rights and gap quality gates.
4. Bounded three-year/latest-available backfill planner with resume and point-in-time replay tests.
5. Cadence-aware jobs, source-specific watermarks and disabled publish rehearsal.
6. Local/full verification, live read-only reconciliation and only then production activation.

## Official references reviewed

- [Bank of Korea ECOS Open API](https://ecos.bok.or.kr/api/)
- [FRED series observations API](https://fred.stlouisfed.org/docs/api/fred/series_observations.html)
- [FRED series vintage dates API](https://fred.stlouisfed.org/docs/api/fred/series_vintagedates.html)
- [FRED series updates API](https://fred.stlouisfed.org/docs/api/fred/series_updates.html)
- [FRED API terms of use](https://fred.stlouisfed.org/docs/api/terms_of_use.html)
- [Cboe VIX and historical-data entry](https://www.cboe.com/tradable-products/vix)
- Candidate FRED pages: [DFF](https://fred.stlouisfed.org/series/DFF),
  [DGS2](https://fred.stlouisfed.org/series/DGS2), [DGS10](https://fred.stlouisfed.org/series/DGS10),
  [T10Y2Y](https://fred.stlouisfed.org/series/T10Y2Y), [CPIAUCSL](https://fred.stlouisfed.org/series/CPIAUCSL),
  [CPILFESL](https://fred.stlouisfed.org/series/CPILFESL), [UNRATE](https://fred.stlouisfed.org/series/UNRATE),
  [PAYEMS](https://fred.stlouisfed.org/series/PAYEMS), [GDPC1](https://fred.stlouisfed.org/series/GDPC1),
  [DTWEXBGS](https://fred.stlouisfed.org/series/DTWEXBGS), [DCOILWTICO](https://fred.stlouisfed.org/series/DCOILWTICO)

## Limits of this research

- No source API was called and no API key or secret metadata was read.
- ECOS exact series identity, Cboe automated-use permission and source-specific numeric rate limits remain unresolved.
- No live database claim is made because the immediately preceding live session checks were unavailable.
- No manifest lifecycle, schema, data, pipeline, schedule, infrastructure or MCP surface was changed.

`WI-039-S01` is closed as implementation input. Parent `WI-039` remains `proposed`, and MS-003 remains gated by MS-002
operational acceptance and the contract-hardening decisions above.
