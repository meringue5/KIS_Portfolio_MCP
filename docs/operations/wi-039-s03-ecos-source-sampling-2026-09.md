# WI-039-S03 bounded ECOS metadata and sample verification — 2026-09-02

> Work Item: `WI-039-S03`
> 상태: closed research evidence
> 승인 근거: owner approved the complete WI-039-S02 package and bounded S03 verification on 2026-09-02
> 범위: ECOS public `sample` metadata and value-presence checks only
> 제외: credential issuance/use, value retention, DDL, DB write, contract adoption, pipeline, schedule, MCP

## Result

The five Korean `macro_profile_v1` concepts now have exact official ECOS identities. No API key was available in local
`.env` or GCP Secret Manager, so the documented public `sample` access was used. Values were never printed or persisted;
the evidence retained only table/item identity, dimensions, cycle, unit, period and value-presence boolean.

| Contract ID | ECOS request identity | Official meaning | Native unit | Initial history start | Decision |
| --- | --- | --- | --- | --- | --- |
| `macro.kr.base-rate` | `722Y001 / D / 0101000` | 한국은행 기준금리 | 연% | 1999-05-06 | accept daily effective level |
| `macro.kr.usd-krw` | `731Y001 / D / 0000001` | 원/미국달러(매매기준율) | KRW per USD | 1964-05-04 | accept; not broker execution FX |
| `macro.kr.cpi-headline` | `901Y009 / M / 0` | 소비자물가지수 총지수 | 2020=100 | 1965-01 | accept monthly native index |
| `macro.kr.industrial-production` | `901Y033 / M / A00 / 2` | 전산업생산지수(농림어업 제외), 계절조정 | 2020=100 | 2000-01 | accept SA variant for monthly cycle context |
| `macro.kr.exports` | `901Y118 / M / T002` | 수출금액, 통관 기준 | thousand USD | 2000-01 | accept nominal customs export amount |

The industrial-production sample returned both `A00/1 원계열` and `A00/2 계절조정`. Initial v1 selects `A00/2`
because its first interpretation is month-to-month cycle context. The original series is not silently collected as a
second contract; adding it later requires a profile version and explicit metric purpose. CPI and exports retain their
native untransformed level, with YoY computed only by an approved metric.

## Evidence by concept

### Base rate

- Table: `1.3.1. 한국은행 기준금리 및 여수신금리`
- Item: `0101000 한국은행 기준금리`
- Available cycles in metadata: A, D, M, Q
- Selected cycle: D
- Unit: `연%`
- Bounded sample: 9 requested-date rows, all with a present value
- Boundary: the daily series repeats the effective level; it is not a daily policy decision event.

### USD/KRW

- Table: `3.1.1.1. 주요국 통화의 대원화환율`
- Item: `0000001 원/미국달러(매매기준율)`
- Selected cycle: D
- Unit: `원`, direction one USD in KRW
- Bounded sample: 7 business-date rows, all with a present value
- Boundary: market/reference FX context only; portfolio cash conversion keeps its own governed FX basis.

### Headline CPI

- Table: `4.2.1. 소비자물가지수`
- Item: `0 총지수`
- Available cycles in metadata: A, M, Q
- Selected cycle: M
- Unit/base: `2020=100`, weight 1000 in metadata
- Bounded sample: 7 monthly rows, all with a present value
- Boundary: stored value is the index level; inflation YoY is derived.

### Industrial production

- Table: `8.1.4. 전산업생산지수(농림어업제외)`
- Item 1: `A00 전산업생산지수(농림어업 제외)`
- Item 2 candidates observed: `1 원계열`, `2 계절조정`
- Selected identity: `A00 / 2`, cycle M, unit/base `2020=100`
- Bounded sample: the same month returned both variants with present values
- Boundary: the SA level supports month-to-month cycle interpretation; no claim is made that it is all Korean output.

### Exports

- Table: `3.2.1. 수출입 총괄`
- Item: `T002 수출금액`
- Available cycles in metadata: A, M
- Selected cycle: M
- Unit: `천불`
- Bounded sample: 6 monthly rows, all with a present value
- Boundary: nominal customs-basis export amount; not real exports, GDP exports or balance-of-payments goods credit.

## Time and revision finding

The sampled ECOS responses expose observation period and current content but do not establish an original publication
timestamp, historical knowledge interval or provider revision identity. Therefore the ADR-027 proposal is confirmed:

- `source_realtime_start/end = null` for ECOS;
- `revision_kind = observed_content`;
- `revision_key = series contract + observation period + normalized native content hash`;
- `knowledge_at = fetched_at` for the earliest governed observation;
- later changed content appends a revision and never rewrites the earlier row;
- historical backfill is labeled `retrospective_reconstructed`, not what the system knew in the past;
- expected publication lag remains a quality/cadence field learned from forward operational evidence, not an invented
  timestamp.

## Call-budget evidence

The approved S03 ceiling was 16 ECOS physical calls and was fully consumed, not exceeded.

| Calls | Purpose | Result |
| ---: | --- | --- |
| 1 | over-wide public sample table-list probe | expected `ERROR-301`; confirmed sample maximum 10 rows |
| 5 | item metadata, one per candidate table | passed; identity/cycle/unit/history metadata obtained |
| 5 | concept samples whose local JSON filter path was invalid | source calls occurred; responses discarded and still charged |
| 5 | final concept samples with corrected local filter | passed; only redacted schema/period/value-presence emitted |
| 16 | total | ceiling reached exactly; no further ECOS call made |

The local filtering mistake did not change or expose source data. It is retained in the audit because physical-call
budgets count every attempt. Future implementation must use a tested parser and durable pre-I/O reservation rather than
shell filtering.

## Contract implications for S04

- The five ECOS `macro_series` contracts can be approved with the exact identities above.
- The total profile remains 17 concepts and 17 series contracts; no extra original industrial-production series is added.
- No ECOS provider vintage is claimed. Dataset 2.0.0 must support nullable provider realtime fields and non-null typed
  observed-content revision.
- A real ECOS API key is still absent. S04 contract adoption does not provision it; future implementation must create
  `kis-portfolio-ecos-api-key`, grant only the batch runtime accessor and pin a numeric version.
- Numeric ECOS production quotas are local fail-closed budgets, not a claim about an official provider entitlement.

## Verification boundary

No raw response, value, credential, secret metadata or account data was written to the repository. No DB, Cloud Run,
Scheduler, Secret Manager entity, contract lifecycle or MCP surface changed. S03 provides source evidence only; S04
requires the owner to review the exact five identities before canonical ADR and DGH adoption.

## Repository verification

- `python3 .agent/skills/kis-data-governance/scripts/check_data_governance.py`: passed, 129 registered contracts
- `bash scripts/check.sh quick`: passed
- `bash scripts/check.sh full`: passed, 438 tests and one existing Authlib deprecation warning
