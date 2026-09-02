# WI-038-S02 dividend ledger contract design — 2026-09-02

> Work Item: `WI-038-S02`
> 상태: owner decision ready
> 변경 분류: architecture and data-contract clarification
> 범위: repository, approved requirements/contracts and current official reference metadata에 대한 선행 설계
> 제외: source API call, credential use, contract lifecycle 변경, DDL, DB write, pipeline activation, schedule, MCP

## 결론

`declared → entitled → received → corrected`를 한 mutable row의 상태 전이로 구현하지 않는다. 배당은 서로
다른 권위 원천과 grain을 가진 세 fact와 append-only revision으로 분리한다.

1. **Dividend action**: issuer/instrument 수준의 선언·일정·배당 조건.
2. **Account entitlement**: action에 대한 계좌별 source-confirmed 권리 또는 point-in-time 추정 권리.
3. **Receipt reconciliation**: action/entitlement와 immutable cash event 사이의 versioned link.

실제 수령액의 monetary SSOT는 계속 `dataset.cash-transaction-event`다. dividend ledger가 cash amount를
독립 원장으로 복제하거나, 일정×현재수량을 실제 수령으로 승격하지 않는다. 월별 배당은 dividend로
분류된 cash event와 그 typed amount component에서만 계산한다.

이 설계는 grain, natural key, dataset boundary와 point-in-time semantics를 바꾸므로 제안 ADR-026과 major
dataset contract 변경이 필요하다. 이번 S02는 승인안을 만들 뿐 승인·활성화하지 않는다.

## 근거

### 승인 요구와 현재 기반

- DEC-023은 declared, entitled, received, corrected와 overseas/IRP manual fallback을 승인했다.
- ADR-025는 official filing의 source availability와 system knowledge를 분리하고, dividend reconciliation을
  filing actual과 논리적으로 격리하되 같은 modular-monolith 실행 기반을 재사용하도록 고정했다.
- `silver.dividend_events`는 빈 foundation table이며 issuer action, account entitlement와 receipt를 한 grain에
  섞는다. state-specific date, revision, knowledge clock, quantity basis, correction과 cash link가 부족하다.
- `silver.cash_flow_events`와 classification revisions는 immutable monetary identity와 point-in-time 분류를
  이미 제공한다. WI-021 적재 cash row를 근거 없이 dividend로 재분류할 수는 없다.
- OpenDART 배당 API는 `corp_code + fiscal year + report code` 단위 정기보고서 사실을 제공한다. KIS 국내
  기간별계좌권리는 account/product/date-range와 pagination을 사용하고, 해외 ICE/기간별권리는 종목·일정
  사실이다. 세 원천의 grain과 확정 수준은 동일하지 않다.

### 공식 reference 재확인

- [OpenDART 배당에 관한 사항](https://opendart.fss.or.kr/guide/detail.do?apiGrpCd=DE002&apiId=AE00006):
  company/fiscal-year/report-code request와 filing number를 제공하며, account receipt source가 아니다.
- [KIS 국내 기간별계좌권리](https://github.com/koreainvestment/open-trading-api/blob/main/examples_llm/domestic_stock/period_rights/period_rights.py):
  `/uapi/domestic-stock/v1/trading/period-rights`, `CTRGA011R`, account/product/date-range와 continuation key를
  사용한다. 공식 example의 recursion default가 10이어도 production은 명시적 page budget에서 먼저 멈춘다.
- [KIS 해외 기간별권리](https://github.com/koreainvestment/open-trading-api/blob/main/examples_llm/overseas_stock/period_rights/period_rights.py):
  `/uapi/overseas-price/v1/quotations/period-rights`, `CTRGT011R`, rights/date/instrument 조건과 50-row
  continuation을 사용하며 account receipt를 증명하지 않는다.
- [KIS 해외 ICE 권리종합](https://github.com/koreainvestment/open-trading-api/blob/main/examples_llm/overseas_stock/rights_by_ice/rights_by_ice.py):
  `/uapi/overseas-price/v1/quotations/rights-by-ice`, `HHDFS78330900`, country/symbol/date-range 일정 조회다.

KIS 국내 allocation/tax/date 필드의 실제 account-statement 의미와 provider history depth는 아직 bounded
fixture로 검증되지 않았다. 따라서 필드명만으로 `received`를 만들지 않는다.

## 제안 ADR-026

### Decision

배당의 action, entitlement와 receipt reconciliation을 별도 append-only identity/revision ledger로 분리한다.
cash receipt의 monetary SSOT는 cash event로 유지하고 dividend 쪽에는 relation, matching rule, allocation과
quality만 보존한다. current projection은 convenience view이며 system-as-of query는 당시 알려진 revision만
선택한다.

### Consequences

- 기존 `dataset.dividend-event` 1.0.0은 action 중심 2.0.0으로 major 변경한다.
- entitlement, reconciliation과 monthly summary를 별도 dataset contract로 추가한다.
- cash dataset은 typed gross/tax/net component와 dividend producer/linkage를 additive 1.1.0으로 명시한다.
- 기존 빈 `silver.dividend_events`는 자동 변환하거나 재사용하지 않는다. non-zero row 또는 consumer가
  발견되면 migration을 중단하고 mapping/reconciliation Work Item을 먼저 연다.
- correction은 original fact를 update/delete하지 않는다. economic reversal과 knowledge correction을 구분한다.

## Logical contract

### 1. Dividend action

| 항목 | 제안 계약 |
| --- | --- |
| identity | `dividend_action_id = jurisdiction + canonical issuer + instrument + source action identity` |
| revision key | `dividend_action_id + source_id + source_revision_id/content_hash` |
| source dates | declaration, ex, record, payable, cancellation/effective dates를 각각 nullable로 보존 |
| terms | cash/stock/special/option, per-share amount, currency, status, certainty와 source taxonomy |
| clocks | source available/effective time, observed/fetched time와 monotonic system `knowledge_at` 분리 |
| correction | explicit source correction/cancellation 또는 verified deterministic supersession만 적용 |
| matching | OpenDART/KSD/ICE fact는 원천 identity를 합치지 않고 action relation과 discrete quality로 연결 |

Ticker/name/proximity만으로 action identity를 확정하지 않는다. issuer/instrument effective identity가
missing/ambiguous이면 quarantine한다.

### 2. Account entitlement

| 항목 | 제안 계약 |
| --- | --- |
| identity | `dividend_action_id + canonical account_id` |
| revision key | entitlement identity + source/evidence hash + system knowledge revision |
| basis | source-confirmed KIS account right 또는 complete PIT position-derived estimate |
| values | eligibility date, eligible quantity, rate, expected gross, currency; unknown은 null |
| evidence | source observation, position snapshot/reconstruction, corporate-action revision과 rule version |
| coverage | `source_confirmed`, `estimated`, `not_observed`, `insufficient_history`, `ambiguous_action`, `source_gap` |

`estimated`는 entitlement 후보이지 receipt가 아니다. 현재 position을 과거 ex/record date로 소급하지 않고,
WI-036 corporate-action-adjusted quantity와 당시 completeness가 pass일 때만 계산한다.

### 3. Cash receipt and reconciliation

- receipt identity는 `cash_flow_event_id`다. account, effective/settled/knowledge time, native currency와 cash
  amount는 cash ledger가 소유한다.
- source가 gross/tax/net을 실제로 제공하면 `cash_flow_event_amount_components`에 typed component revision으로
  보존한다. net만 제공하면 gross/tax를 0으로 채우지 않는다.
- action/entitlement/cash 관계는 many-to-many를 허용한다. link revision은 `exact`, `reconciled`,
  `candidate`, `partial`, `unmatched`, `source_gap`과 reason/rule version/allocation을 가진다.
- exact source reference가 최우선이다. account+instrument+currency+payable window와 native amount tolerance는
  deterministic candidate/reconciliation 규칙이며 날짜·금액 proximity만으로 exact가 되지 않는다.
- reversal cash row는 반대 economic event이고 correction은 classification/link knowledge revision이다.

### 4. Point-in-time and monthly read model

- live/운영 재현의 기본은 `system_as_of`다. action, entitlement, cash classification과 link가 모두 cutoff
  이전에 알려진 revision이어야 한다.
- historical source-time 연구는 명시적 retrospective mode와 timestamp precision을 표시하며 live result와
  silently mix하지 않는다.
- monthly native summary grain은 `received month + account + instrument + currency`다. received cash만 합산하고
  declared/entitled 예상액은 별도 비교 열로 둔다.
- KRW summary는 governed FX rate/date/metric version을 가진 파생 결과다. native amount와 account/market/period
  receipt coverage를 함께 반환하며, 환산액을 broker gross/net이라고 부르지 않는다.
- gross·tax·net 중 source-confirmed component만 합산한다. unknown component coverage를 0으로 표현하지 않는다.

## Source and coverage policy

| Scope | Action | Entitlement | Receipt | Initial policy |
| --- | --- | --- | --- | --- |
| KRX 일반/RIA/ISA/연금저축 | OpenDART filing + KIS KSD | KIS account-right candidate | account-right allocation/tax는 statement fixture 전 candidate | bounded fixture 뒤 계좌별 활성화 |
| KRX IRP | OpenDART/KSD | prior probe 0 rows | verified source 없음 | `source_gap`; manual fallback only |
| U.S. brokerage | KIS ICE/period rights | complete PIT position estimate only | verified KIS receipt identity 없음 | `source_gap`; statement/manual fallback |
| unsupported market/product | approved complete source 없음 | 없음 | 없음 | unsupported, no synthetic facts |

빈 결과는 zero receipt가 아니다. account/product/period별 requested, paginated, returned, terminal status와
coverage reason을 Control quality evidence로 남긴다.

## Proposed DGH contract delta

아래는 owner approval 뒤에만 canonical catalog에 반영한다. 모두 `approved + inactive`로 시작한다.

| Contract | Version | Change |
| --- | --- | --- |
| `dataset.dividend-source-observation` | 1.0.0 | KIS/OpenDART-derived/manual account-private raw observation; shared Bronze landing 사용 |
| `dataset.dividend-event` | 2.0.0 | issuer/instrument action identity와 append-only revision으로 major hardening |
| `dataset.dividend-entitlement` | 1.0.0 | account/action entitlement revision, basis와 coverage |
| `dataset.dividend-reconciliation` | 1.0.0 | action/entitlement/cash many-to-many link revision |
| `dataset.dividend-monthly-summary` | 1.0.0 | received-only native summary와 labeled FX projection |
| `dataset.cash-transaction-event` | 1.1.0 | monetary SSOT 유지, optional typed amount components와 dividend lineage 추가 |
| `collection.dividend-ledger-v1` | 1.0.0 | 3년 bounded action/right/receipt basket; unsupported gap explicit |
| `pipeline.dividend-ledger-v1` | 1.0.0 | action, entitlement, receipt/link, quality와 monthly publish 전용 logical pipeline |

`collection.fundamentals-dividends-v1`과 `pipeline.fundamentals-dividends-v2` umbrella는 historical/future
orchestration intent로 approved-but-inactive 상태를 유지한다. dedicated dividend pipeline이 이 umbrella를
통해 실행되지 않는다.

## Proposed physical migration 0015

ADR-025의 예정 migration 0014 뒤 additive `0015_dividend_ledger.sql`을 사용한다.

| Layer | Proposed objects |
| --- | --- |
| Silver | `dividend_actions`, `dividend_action_revisions`, `dividend_actions_current` |
| Silver | `dividend_entitlements`, `dividend_entitlement_revisions`, `dividend_entitlements_current` |
| Silver | `dividend_receipt_links`, `dividend_receipt_link_revisions`, `dividend_receipt_links_current` |
| Silver | `cash_flow_event_amount_components` |
| Gold | `dividend_monthly_native`, `dividend_monthly_krw` rebuild views |

Preflight는 legacy `silver.dividend_events` row count, consumer/reference와 backup manifest를 검사한다. 하나라도
non-zero/unknown이면 fail closed한다. migration은 기존 object를 drop/rename/update하지 않고 new object만
추가한다. rollback은 consumer inactive 상태에서 new objects를 abandoned version으로 두고 V1/main writer와
기존 cash consumer를 유지한다; 데이터 삭제는 별도 승인이 필요하다.

## Pipeline, budget and capacity

`pipeline.dividend-ledger-v1`은 `collect → land → normalize-action → reconcile-action → normalize-entitlement →
link-receipt → quality → publish-monthly` stage를 가진다. filing actual에서 이미 수집한 OpenDART artifact와
filing identity는 input으로 재사용하고 같은 원문을 중복 호출/저장하지 않는다.

### Routine and backfill proposal

| Control | Routine | Backfill |
| --- | ---: | ---: |
| KIS physical calls | run당 64 이하 | 하루 320 이하 |
| pagination | partition당 10 pages 이하; continuation loop/hash 반복 시 중단 | 동일 |
| concurrency | account/endpoint 순차, KIS shared resilience 사용 | 동일 |
| history | new/corrected action/right와 account-history reconciliation | 최대 3년, account/market/month partition |
| owner import | network call 0; explicit dry-run/apply | same document hash는 idempotent no-op |

Routine은 filing publication/right schedule과 completed account-history 뒤에 실행한다. page/call budget 소진,
partial page, cursor loop, source error와 unsupported account를 success/zero로 기록하지 않는다. resume key는
pipeline/version/source/account/market/date partition/plan hash다.

Initial stop line은 private Bronze object 1 GiB, dividend action+entitlement+link+component 500,000 rows다. 80%에서
capacity review를 열고 stop line에서는 신규 backfill을 중단하되 routine correction과 existing receipt
reconciliation을 우선한다. 이 규모는 현재 직접보유 범위와 3년 이력에 넉넉하며 MotherDuck/GCS 비용을
기존 월 50,000원 상한 안에서 조기 통제하기 위한 guardrail이다.

현재 7개 직접보유 issuer/instrument, 최대 5개 계좌, 월 1회 지급이라는 보수적 상한을 적용해도 3년
action은 약 252건, entitlement는 약 1,260건이다. revision/link/component를 10배로 잡아도 typed row는
약 15,000건 수준이다. 따라서 500,000-row stop line은 예상치가 아니라 shape drift, pagination 오류 또는
중복 폭증을 잡는 30배 이상의 circuit breaker다. raw byte size는 아직 표본이 없으므로 1 GiB를 비용 예측이
아닌 fail-closed 상한으로 사용하고, activation 후 첫 30일의 실제 object/row 증가량으로 재산정한다.

## Manual fallback

- statement/CSV/PDF evidence는 owner-private source observation, document hash, account/period/currency, parser or
  manual-entry version, imported/knowledge/recorded time을 가진다.
- raw document는 private object storage에 두고 MCP/Telegram에 반환하지 않는다.
- apply 전에 dry-run row count, duplicate candidates, totals by native currency와 redacted preview를 검토한다.
- manual receipt는 broker event를 overwrite하지 않는다. 이후 broker evidence가 도착하면 duplicate candidate와
  reconciliation revision을 만들고 owner confirmation 없이는 자동 merge하지 않는다.
- exact import format과 parser는 실제 statement sample이 제공된 뒤 별도 bounded sub-item에서 결정한다.

## Shared implementation constraint

논리적 filing/dividend 분리는 동일한 application image, managed runner, KIS/source adapters, Bronze landing,
repository primitives, MotherDuck/GCS, Secret Manager profile와 release artifact를 재사용한다. 별도 service,
repository, always-on worker 또는 duplicated scheduler framework를 만들지 않는다. 분리 때문에 공통 코드나
운영 구성이 실질적으로 중복되면 구현을 중단하고 ADR-026을 재검토한다.

## Quality and verification gate

- synthetic/redistribution-safe fixtures: KR action, domestic account right, U.S. schedule, multi-cash receipt,
  reversal, correction, manual duplicate, pagination/cursor loop, source gap.
- uniqueness: every identity/revision key; no current-view duplicate.
- PIT: later action, entitlement, cash classification와 link revision이 earlier `system_as_of`에 나타나지 않음.
- arithmetic: source-confirmed gross/tax/net only; sign and currency-specific rounding; unknown remains null.
- reconciliation: exact/reconciled/candidate/partial/unmatched/source_gap paths and many-to-many allocation.
- restore: private object + Parquet restore, row/hash/current-view/monthly native totals reconciliation.
- redaction: account identifiers, source payload, raw document와 absolute portfolio amounts are absent from MCP/log.
- full Project OS/DGH/warehouse gate; production source/DB smoke is later release evidence, not S02 evidence.

## Owner decision package

다음 일곱 항목을 한 묶음으로 승인 또는 수정한다.

1. ADR-026의 action/entitlement/receipt-link 분리와 cash monetary SSOT.
2. 8-contract DGH delta와 umbrella inactive 유지.
3. additive migration 0015와 legacy empty-foundation fail-closed preflight.
4. system-as-of 기본, source-effective/retrospective label과 append-only correction/reversal 의미.
5. KRX bounded candidate, IRP/U.S. `source_gap` 및 manual fallback coverage 정책.
6. KIS 64/320 call cap, 10-page cap, 1 GiB/500,000-row stop line.
7. shared modular-monolith implementation, no separate service/repository/always-on worker.

승인 뒤 `WI-038-S03`에서 ADR·요구 clarification·DGH contracts를 canonical SSOT에 채택한다. MS-002가
닫히고 MS-003 formal gate가 열린 뒤에만 migration/repository/fixture 구현 sub-item을 시작한다.

## Evidence and limits

- Repository schema, cash revision ledger, approved requirements, ADR-025, DGH contracts와 official reference
  metadata를 읽기 전용으로 검토했다.
- source credential과 account data를 사용하지 않았고 KIS/OpenDART API를 호출하지 않았다.
- endpoint의 존재·pagination shape는 official reference에서 재확인했지만 KIS allocation/tax semantics,
  retention depth와 account coverage는 fresh live fact로 주장하지 않는다.
- contract status/version, DDL, data, infrastructure, schedule, source activation과 MCP surface를 바꾸지 않았다.
