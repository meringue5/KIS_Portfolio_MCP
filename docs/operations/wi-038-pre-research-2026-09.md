# WI-038 dividend event ledger pre-research — 2026-09-01

> Work Item: `WI-038-S01`
> 범위: repository, approved requirements/contracts and official KIS/OpenDART reference metadata에 대한 read-only research
> 변경 경계: source API call, credential use, contract lifecycle, DDL, DB write, pipeline, schedule와 MCP 변경 없음

## 결론

승인된 `declared → entitled → received → corrected` 방향은 유효하지만, 현재 `silver.dividend_events`에
producer를 붙여서는 안 된다. 논리 계약은 issuer 수준의 선언, 계좌 수준의 권리, 실제 현금 수령과 정정을
한 grain으로 표현하고 있고, 물리 테이블은 상태별 날짜·권리수량·지식시점·정정 계보·현금 대사 링크를
담지 못한다.

- 국내 KIS 기간별계좌권리는 계좌·기준일·잔고수량·최종배정금액·세금·현금지급일 후보를 제공하지만,
  선행 live 조사에서 IRP는 0행이었다. 0행은 0원 수령이 아니라 `source_gap`이다.
- 해외 KIS 기간별권리는 주당 외화배당과 확정 여부를 제공하지만 계좌별 실제 입금 identity가 아니다.
- WI-021의 해외 일별거래내역 adapter는 매매 정산·수수료·세금만 정규화한다. 이미 적재된 49개 cash
  event를 배당 실수령으로 재해석할 수 없다.
- OpenDART·KSD·ICE 일정은 선언/예정 근거이고, ex-date 보유수량에서 계산한 금액은 `estimated entitlement`다.
  둘 다 broker cash evidence가 없는 `received`를 만들 수 없다.
- 과거 entitlement는 당시의 완전한 position/trade/corporate-action 상태로만 계산한다. 현재 보유수량을
  과거 기준일에 소급하거나 `주당배당 × 현재수량`을 실수령으로 기록하지 않는다.

따라서 parent `WI-038` 구현 전에 issuer action과 account entitlement identity를 분리하고, 상태별 immutable
fact와 correction/reconciliation relation을 versioned contract로 승인해야 한다. `WI-037`의 filing identity와
point-in-time hardening도 선행 dependency로 유지한다.

## 승인 요구와 현재 기반

| Area | Existing input | Gap before implementation |
| --- | --- | --- |
| requirement | DEC-023은 declared, entitled, received, corrected와 manual fallback을 승인 | `reversed`와 `corrected`의 의미, 상태 전이 대신 독립 fact를 쓰는 방식 미확정 |
| source | OpenDART, KIS KSD/account rights/ICE/period rights, portfolio owner가 승인됨 | endpoint별 identity, revision, retention window와 account/product coverage manifest 없음 |
| filing | `dataset.filing-event`, `silver.filing_events` 기반 존재 | WI-037-S01의 Bronze/Silver, issuer mapping, correction/PIT hardening이 미완료 |
| positions/trades | canonical snapshots와 3년 trade history 존재 | ex/record-date 시점 수량의 완전성 및 corporate-action-adjusted reconstruction 증거 필요 |
| cash | immutable `cash_flow_events`와 PIT classification revisions 존재 | 국내 배당 receipt producer 없음; 해외/IRP actual receipt source 없음; dividend-to-cash link 없음 |
| dividend dataset | approved `dataset.dividend-event`, empty physical table과 backup catalog 존재 | grain, key, state-specific time, quantity/rate, provenance, correction and reconciliation fields 부족 |
| pipeline | approved `pipeline.fundamentals-dividends-v2` 존재 | producer repository, source budgets, watermarks, fixtures, quality and schedule 없음 |
| read model | monthly gross/net history 요구 존재 | received-only cash aggregation, native/converted currency 및 coverage projection 계약 없음 |

Foundation DDL은 production readiness 증거가 아니다. Repository search에서 dividend producer, state repository,
current/as-of view와 reconciliation service는 확인되지 않았다.

## 권고 identity와 grain

현재 한 테이블의 natural key
`instrument_id, account_label, event_type, event_date, source_fact_id`는 issuer declaration과 account receipt를
동시에 표현하기 어렵다. 권고 방향은 두 경제적 identity와 연결 fact를 분리하는 것이다.

### 1. Dividend action

Issuer/security 수준의 한 배당 선언 또는 corporate action이다.

- identity 후보: `issuer_id + instrument_id + action_type + source_action_id`;
- declared, ex, record, payable date를 각각 보존;
- cash/stock/special/option distribution 유형, 주당금액·통화·확정여부와 source revision 보존;
- source filing/right ID, URL/object observation, announcement/accepted/knowledge/fetched time 보존;
- OpenDART/KSD/ICE facts가 같은 action을 가리키는지는 deterministic match와 link quality로 표현하고 원천
  identity를 병합하거나 덮어쓰지 않음.

### 2. Account entitlement

한 action에 대해 한 계좌가 가진 권리 또는 계산된 권리 후보다.

- identity 후보: `dividend_action_id + account_id + entitlement_revision`;
- eligibility date, eligible quantity, quantity source, per-share rate, expected gross/currency 보존;
- broker account-right row는 `source-confirmed`, PIT position 계산은 `estimated`로 구분;
- `not_observed`, `insufficient_position_history`, `ambiguous_action`, `source_confirmed` 같은 coverage를 값과
  별도로 보존;
- position 수량은 split, merger, stock dividend 등 WI-036 corporate-action lineage와 reconcile된 경우에만
  과거 entitlement 근거가 됨.

### 3. Receipt and reconciliation link

실수령은 별도 금전 fact인 `cash_flow_event_id`가 canonical monetary identity다. Dividend ledger는 이를
복제하거나 수정하지 않고 action/entitlement와 link한다.

- receipt identity: immutable `cash_flow_event_id`;
- gross, tax, net을 source가 실제로 제공하는 범위에서 보존하고 `gross - tax = net`의 부호·반올림 규칙을
  통화별로 검증;
- source가 net만 제공하면 gross/tax를 0으로 채우지 않고 unknown으로 유지;
- 하나의 action에 여러 receipt/tax row가 있거나 여러 action이 한 cash row로 합쳐진 경우 many-to-many
  link와 allocation quality를 허용;
- manual statement/CSV는 별도 owner source observation과 actor, document hash 또는 note reference, imported,
  knowledge, recorded time을 가진다. Broker event가 나중에 들어오면 manual row를 overwrite하지 않고
  중복 후보로 reconcile한다.

## 상태와 정정 의미

상태를 한 mutable lifecycle column으로 갱신하기보다 서로 다른 provenance의 append-only fact로 보존한다.

| Fact/state | 확정 근거 | 허용 값 | 금지 해석 |
| --- | --- | --- | --- |
| `declared` | issuer filing, KSD/ICE official right fact | dates, rate, currency, declared/final indicator | 계좌 권리 또는 수령 확정 |
| `entitled` | KIS account right 또는 complete PIT position calculation | account, eligible quantity, expected amount, evidence quality | 현재 보유수량의 과거 소급 |
| `received` | broker cash event 또는 explicit manual statement import | account, cash date, native amount/currency, gross/tax/net when sourced | 일정×수량으로 만든 실수령 |
| `corrected` | later source revision, broker reversal, owner correction | supersedes/reverses relation, reason, knowledge time | 원본 row update/delete |

`reversed`는 현금 반대거래나 source 취소라는 경제적 사건이고, `corrected`는 지식/분류 revision이다. 둘을
하나의 event type으로 합치지 않는다. Current projection은 최신 지식시점의 유효 fact를 보여주되 as-of query는
당시 알 수 있었던 revision만 선택해야 한다.

## Reconciliation 계약 후보

### Matching order

1. exact broker/source action or receipt reference;
2. account + instrument + currency + declared payable window;
3. account + action + amount tolerance candidate;
4. otherwise unmatched or ambiguous.

날짜와 금액 proximity만으로 자동 `reconciled`하지 않는다. 매칭 결과는 다음 중 하나를 갖는다.

- `exact`: stable source identity로 1:1 연결;
- `reconciled`: deterministic multi-field rule과 허용오차 통과;
- `candidate`: 하나 이상의 plausible link가 있으나 확정 불가;
- `partial`: 일부 cash/tax row만 연결되거나 예상액 일부만 수령;
- `unmatched`: 근거가 없음;
- `source_gap`: 해당 계좌/시장에 receipt source가 없음.

통화가 다르면 먼저 native currency 원장을 닫는다. KRW 월별 보기는 governed FX observation과 conversion
metric version, rate date를 가진 파생 결과로만 제공하고 native amount를 항상 함께 노출한다. 환율 변환액을
broker gross/net으로 표시하지 않는다.

### Quality and completeness

- `received` monthly income은 received cash event만 합산한다. declared/entitled 예상액은 별도 열과 coverage로
  비교한다.
- 계좌·시장·기간별 source coverage manifest가 `pass`가 아니면 “미수령”이 아니라 “확인 불가”로 표시한다.
- duplicate source facts, inconsistent dates, negative non-reversal amounts, missing currency, impossible tax/net,
  ambiguous instrument/issuer와 future-known revision은 quarantine 또는 non-pass다.
- cash ledger와 dividend ledger의 gross/net 복제값이 있다면 cash event가 monetary SSOT이며 link projection은
  불일치를 fail closed한다.
- monthly history/change는 `account + native currency + received month` grain에서 먼저 재현되고, total view는
  명시된 account coverage와 FX coverage를 함께 반환한다.

## Source/account coverage matrix

| Market/account scope | Declared/scheduled | Entitled | Received | Current disposition |
| --- | --- | --- | --- | --- |
| KRX 일반/RIA/ISA/연금저축 | OpenDART/KSD | KIS account rights candidate; prior live rows observed | final allocation/tax fields require bounded semantic fixture | implementation gate; not yet canonical |
| KRX IRP | OpenDART/KSD | prior KIS probe returned zero rows | no verified receipt source | explicit `source_gap`; manual import candidate |
| U.S. brokerage | KIS ICE/period rights; SEC filing may cross-check issuer event | PIT position estimate only unless account-level source found | no verified KIS receipt identity | explicit `source_gap`; statement/manual import candidate |
| other overseas/product | no approved complete coverage claim | no approved complete coverage claim | no verified receipt source | unsupported until source contract revision |

KIS 국내 계좌권리의 `last_alct_amt`, `tax_amt`, `cash_dfrm_dt`가 실제 입금 원장과 같은 의미인지는 bounded
fixture에서 계좌 명세와 대조하기 전까지 candidate다. 해외 기간별권리의 주당배당과 `dfnt_yn`은 entitlement
estimate를 개선할 수 있지만 receipt 증거로 승격하지 않는다.

## Current contract/schema hardening gate

Formal `WI-038` 계획은 구현 전에 아래를 함께 결정해야 한다.

1. `dataset.dividend-event`를 action, entitlement, reconciliation dataset으로 분리할지, 하나의 typed event
   ledger와 별도 link table로 version-up할지 승인한다.
2. `account_label` logical key와 physical `account_id` 불일치를 해소하고 계좌·issuer·instrument effective
   identity를 참조한다.
3. 상태별 dates, eligible quantity, per-share rate, amount certainty, source status, publication/accepted/knowledge/
   fetched/recorded time을 추가한다.
4. source observation, filing/right fact, position evidence, cash event, manual evidence를 ID로 연결하고 link rule,
   allocation, confidence가 아니라 discrete quality와 reason을 보존한다.
5. correction/supersession/reversal relation과 current/as-of projection을 정의한다.
6. `received`의 monetary SSOT를 `cash_flow_events`로 고정하고 dividend classification이 필요한 cash event는
   기존 append-only revision을 사용한다.
7. account/market/period coverage와 missing-source reason을 Control quality evidence로 모델링한다.
8. native-currency monthly received view와 versioned FX-converted read model을 분리한다.
9. backup/restore allowlist, confidentiality, row-level redaction과 MCP aggregate response를 함께 검토한다.

이 변경은 grain, natural key, dataset boundary와 PIT semantics에 영향을 준다. Parent의
`architecture_impact: none`은 formal contract decision에서 재검토해야 한다.

## Backfill and routine collection constraints

- 첫 backfill 목표는 세 계층을 분리한다: issuer action history, account-right history, actual cash receipt history.
- OpenDART/KSD/ICE action backfill은 직접 보유 issuer/instrument allowlist와 source-specific cap을 사용한다.
- account-right backfill은 provider retention window를 먼저 측정하고, page/call budget과 resumable partition을
  WI-021 패턴으로 별도 승인한다.
- received history는 실제 source가 제공하는 범위만 적재한다. 3년 목표를 채우기 위해 balance delta, 오늘의
  position 또는 estimated entitlement를 합성하지 않는다.
- manual statement import는 source gap을 메울 수 있지만 exact document period, account, currency, row count,
  hash와 duplicate policy를 가진 dry-run 뒤에만 apply한다.
- routine run은 filing/right publication cadence와 account-history 완료 뒤 reconciliation으로 나눈다. 하나의
  실패가 다른 상태를 삭제하거나 watermarks를 건너뛰게 하지 않는다.

## Suggested implementation sequence

1. WI-037 filing identity/PIT contract와 직접보유 issuer mapping gate를 먼저 닫는다.
2. Dividend action/entitlement/receipt-link dataset version과 architecture impact를 승인한다.
3. Additive migration, repository, current/as-of view와 synthetic/redistribution-safe fixtures를 구현한다.
4. KIS 국내 KSD/account-right, 해외 ICE/period-right adapter를 bounded fixtures로 검증한다.
5. 국내 account-right의 allocation/tax semantics를 actual statement와 대조하고 계좌별 coverage manifest를
   만든다.
6. Receipt importer는 broker evidence 우선, manual statement fallback, immutable dedup/reconciliation 순서로
   구현한다.
7. Three-year backfill planner와 per-source budget/resume/watermark를 추가하고 dry-run한다.
8. Private backup/restore와 aggregate reconciliation을 통과한 뒤 received-only monthly read model을 만든다.
9. Scheduler와 MCP는 별도 activation gate에서 coverage와 redaction을 검증한 후 연다.

## Official references reviewed

- [OpenDART 배당에 관한 사항 개발가이드](https://opendart.fss.or.kr/guide/detail.do?apiGrpCd=DE002&apiId=AE00006)
- [KIS 공식 Open Trading API repository](https://github.com/koreainvestment/open-trading-api)
- [KIS 국내 기간별계좌권리현황 예제](https://github.com/koreainvestment/open-trading-api/tree/main/examples_llm/domestic_stock/period_rights)
- [KIS 국내 예탁원 배당일정 예제](https://github.com/koreainvestment/open-trading-api/tree/main/examples_llm/domestic_stock/ksdinfo_dividend)
- [KIS 해외 기간별권리조회 예제](https://github.com/koreainvestment/open-trading-api/tree/main/examples_llm/overseas_stock/period_rights)
- [KIS 해외 권리종합 예제](https://github.com/koreainvestment/open-trading-api/tree/main/examples_llm/overseas_stock/rights_by_ice)

## Limits of this research

- No KIS/OpenDART source API was called, and no account row, statement, secret or live dividend value was read.
- Previous live coverage counts are requirements research evidence, not a fresh completeness claim for 2026-09-01.
- KIS domestic allocation/tax fields and retention windows still require bounded semantic fixtures.
- No live MotherDuck row count or freshness claim is made; repository code and prior aggregate WI-021 evidence were used.
- No contract status/version, schema, data, pipeline, schedule, infrastructure or MCP surface was changed.

`WI-038-S01` is closed as implementation input. Parent `WI-038` remains `proposed`; formal implementation remains
blocked by WI-037 and the dividend dataset/identity/PIT contract-hardening decision.
