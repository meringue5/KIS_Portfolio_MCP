# WI-068 retained legacy history — 1차 read-only 조사, 2026-10-13

## 결론과 조사 경계

**보존된 데이터가 존재하며, 검증한 V1 snapshot/overview/holding의 삭제·변경 증거는 없다.**
희소 수집, raw-to-V2 변환 범위, feeder 불완전성, 가격 basis/knowledge 제한이 함께 존재한다.
7월 전체 canonical 총자산·수익률·고점 회복 시점은 현재 증거로 복원할 수 없다.
관측 사실만 선별 승격하고 불완전 집계는 reference-only로 유지하는 **bounded hybrid**를 추천한다.
이는 제안이며 승인된 ADR, 계약 또는 production 실행 권한이 아니다.

- WI-068 `proposed`, type `architecture`, production effects `none` 유지. 기존 intake 변경 4개 보존.
- 필수 문서, Project OS/DGH/Warehouse 스킬, 기존 mapping code/contract와 WI-015/022 운영 증거를 읽었다.
- 저장소 Python 3.13.3으로 직접 DuckDB SELECT와 Parquet 읽기, GCS list/metadata/index/manifest GET만 수행했다.
  `get_connection()`의 local auto-DDL, migration/restore/export helper와 KIS source 호출은 사용하지 않았다.
- 조회 범위: 저장소 `var` 전체, 알려진 이전 checkout 경로와 임시 디렉터리의 DB/Parquet/manifest 후보,
  설정된 MotherDuck `kis_portfolio`, 알려진 초기 `my_db`, 기존 private GCS bucket의 **current objects**와 version/soft-deleted metadata.
  임의 사용자 홈 전체, 외부 저장매체/Drive에 있는 복사본의 내용은 조사하지 않았다. GCS version inventory 925 objects/noncurrent 0, soft-deleted 0을 추가 확인했다.
  따라서 이 조사 범위 밖에 artifact가 없다고 단정하지 않는다.
- live SELECT들은 하나의 장기 snapshot transaction이 아니며 background producer가 계속 작동할 수 있다.
  아래 건수는 2026-10-13 조사 시점 관측치다. source row·금액·계좌번호·secret·raw URI는 보고에 넣지 않았다.
- 신규 코드/API/MCP/DDL/계약 activation, production restore/backfill/publish/deployment는 **없다**.

## 증거 파일과 inventory

[aggregate inventory](../../governance/project/evidence/wi068/retained-artifact-inventory-2026-10-13.json)는
473개 로컬 Parquet의 handle/object/bytes/rows/SHA-256, 15개 backup directory,
14개 manifest fingerprint, live 기간·계좌·basis·null/duplicate 집계, 20개 GCS index와 manifest 검증을 기록한다.
[July shapes](../../governance/project/evidence/wi068/july-compatibility-shapes-2026-10-13.json)는 관측 구조와
합성 conflict 경계를 보존한다. raw payload 복제나 실행 acceptance test가 아니다.

### 로컬 artifact

| handle | capture label | Parquet 수 | manifest | 검증 |
| --- | --- | ---: | --- | --- |
| L01 | 20260802_025429 | 19 | legacy-v1 | row count 일치 |
| L02 | 20260828_020109 | 17 | legacy-v1 | row count 일치 |
| L03 | 20260827_170318 | 29 | 2 | row count 일치 |
| L04 | 20260827_215540 | 29 | 2 | row count 일치 |
| L05 | 20260827_215630 | 29 | 2 | row count 일치 |
| L06 | 20260827_232909 | 29 | 2 | row count 일치 |
| L07 | 20260827_233030 | 29 | 2 | row count 일치 |
| L08 | 20260827_233357 | 29 | 2 | row count 일치 |
| L09 | 20260828_012417 | 15 | 없음 | manifest 없는 부분 export |
| L10 | 20260828_012540 | 32 | 2 | row count 일치 |
| L11 | 20260828_013726 | 32 | 2 | row count 일치 |
| L12 | 20260828_015300 | 33 | 2 | row count 일치 |
| L13 | 20260828_020836 | 35 | 2 | row count 일치 |
| L14 | wi045-20260911-1520 | 58 | 3 | row count 일치 |
| L15 | wi045-20260911-1520-downloaded | 58 | 3 | row count 일치 |

- L01/L02 V1 백업: portfolio 227/267, overseas feeder 39/48, overview 39/48, holding 1,366/1,619,
  price 785/838, FX 100/100, domestic order 15/20, overseas raw transaction envelope 42/58,
  normalized overseas transaction 2/2, profit report 12/15.
  snapshot/holding 기간은 2026-04-19~07-24 또는 ~08-27이고 raw domestic balance는 ~07-29/~08-27까지.
  price 전체 범위 2018-03-29~07-06/~08-25, FX 2025-11-20~2026-04-17.
- V1 두 백업의 portfolio/overseas/overview/holding을 live `id`와 row SHA-256으로 대조:
  **8개 비교 모두 missing=0, changed=0**. 백업 간 같은 관측을 새로운 coverage로 합산하지 않는다.
- V2 단계별 backup은 빈 foundation → price 838 → position 1,357/cash 232/daily state 889 → trade 19 →
  dual-basis price 15,587 → WI-045 position 2,105/cash 397/trade 282/cash event 49/daily state 1,833을 기록한다.
  원본과 downloaded WI-045 manifest는 같은 hash이고 독립 source가 아니다.
- L09 partial export는 **15개 Parquet**, manifest 없음. 모든 Parquet 자체는 읽히지만 complete restore가 아니다.
  정확한 handle은 위 표와 inventory가 소유한다.
- 로컬 보조 DuckDB 798,720 bytes: read-only로 portfolio/price/FX 0행 확인;
  overview/holding/overseas table은 없음. 운영 SSOT나 역사 source가 아니다.
- 부가 JSON 23개: 14 manifest, backup migration/reconciliation evidence 3개, operational-state migration summary 1개,
  token 5개. token/env/lock은 portfolio recovery source에서 제외하고 내용을 출력하지 않았다.
  repository governance evidence와 synthetic tests는 증거/계약이며 실계좌 관측의 대체 source가 아니다.

### MotherDuck 및 private GCS

| artifact | 관측 규모/기간 | provenance/checksum | 복구/소비 상태 |
| --- | --- | --- | --- |
| `main.portfolio_snapshots` | 746행/63일, 04-19~10-13, 5계좌 | KIS raw JSON, id/snapshot_at; 두 V1 백업 row hash 동일 | 원본 관측 readable; overview 미연결 날짜는 현재 V2에서 제외 |
| `main.overseas_asset_snapshots` | 57행/36일, 04-19~09-09, brokerage | balance/deposit/fx envelope; 백업 hash 동일 | 해외 관측 존재와 feeder completeness는 별개 |
| `main.asset_overview_snapshots` | 57행/36일, 04-19~09-09 | typed aggregate/JSON; quality/is_complete 전부 NULL | reference-only; 총액 자동 pass 금지 |
| `main.asset_holding_snapshots` | 1,895행/36일, 04-19~09-09 | overview parent와 원본 fields; value_krw NULL 110행 | 보유수량/native-currency 사실 후보; 해외 KRW valuation gap |
| `main.price_history` | 1,740행/394일, 2018-03-29~2026-10-13 | exchange/symbol/date/adjusted, created_at | basis 별 판단; V1 PK는 두 basis 동시 보존을 지원하지 않음 |
| `main.exchange_rate_history` | 115행/115일, 2025-11-20~2026-09-17 | currency/date/period/created_at | 6·7월 없음; 8월은 28/31 두 날짜 |
| `main.domestic_orders` / `order_history` | 20 normalized orders/6 execution days; 161 raw envelopes/34 fetch days | broker identity + first/last_seen; query range 별도 | envelope 횟수는 execution coverage가 아님 |
| `main.overseas_transactions` / raw history | normalized 2행; raw 81 envelopes/80 fetch days | normalized raw_data는 buy/sell/fee summary keys | 2행 모두 quantity/side/fee/FX NULL; trade event로 사용 불가 |
| `main.trade_profit_history` | 15 reports/10 fetch days, 04-20~08-10 | query range/fetched_at/raw report | reference report; canonical event/return으로 매핑 금지 |
| V2 Silver/Gold | positions 3,365, cash 685, trade 298, cash events 75, price 16,787, FX 133, daily state 3,529 | source_observation_id, revision/lineage; migrations 0001~0020 확인 | native V2 우선; legacy source row quality `passed`만으로 total pass 불가 |
| `bronze.source_observations` V1 migration runs | portfolio observation 1,904 + overview 48; price 838; FX 100; master 4,440; trade-domain 149; cash-domain 2 | 각 run 내 content hash distinct=count; payload 보존 | 기존 V1→V2 mapping input/output lineage; raw 국내 balance는 landing-only |
| 알려진 `my_db.main` | 5 tables 모두 0행 | 초기 legacy catalog, 현재 직접 재검증 | 회복할 행 없음; 삭제하지 않음 |
| GCS recovery | 839 objects, 189,667,072 bytes; JSON 45 + Parquet 794 | 20 immutable recovery index, 20 manifest SHA-256 검증 | index 참조 1,140건(중복 포함), missing=0/size mismatch=0/CRC 존재; payload SHA-256 전체 재검증/restore는 이번에 안 함 |
| GCS 원문 / `bronze.raw_object_manifest` | 86 objects / 86 metadata rows, 10,937,044 bytes | content hash 64자리 86/86; confidential portfolio JSON, ingest 08-28~10-13 | metadata만 조사; source_published_at 전부 NULL, raw bytes 미검증; July historical source라고 단정 금지 |

GCS index capture는 08-28 migration/backfill 전후, 09-11 WI-045, 09-13 transition,
10-07/08 WI-066 전후를 포함한다. manifest v2에는 migration prefix가 없고 v3는 exact prefix를 가진다.
과거 restore 성공은 기존 WI-015/021/022/048/066 증거이며 이번 세션 restore 성공으로 재포장하지 않는다.
current recovery raw-byte hash와 권한·restore mechanics의 완전 검증은 선택된 ADR 이후 별도 단계다.

## 실제 날짜·계좌·종목 coverage

V2 `v1-latest`: 04-19~08-27 중 **27일**, 7월 **07-24 하루** 재확인.
6월은 05/08/14/16/20, 8월 legacy는 06/10/25/26/27.
retained main overview/holding은 추가로 08-28/31도 있지만 native V2를 대체하지 않는다.
8월 native V2는 28일 10:00, 31일 10:00/14:30/16:00 관측이 있다.

| 계좌 | 6월 raw 잔고 날짜 | 7월 raw 잔고 날짜 | 8월 raw 잔고 날짜 |
| --- | --- | --- | --- |
| ria | 04, 05, 08, 14, 16, 20 | 24 | 06, 10, 25, 26, 27, 28, 31 |
| isa | 05, 08, 14, 16, 20 | 24 | 06, 10, 25, 26, 27, 28, 31 |
| brokerage | 05, 08, 14, 16, 20 | 06, 24, 29 | 10, 25, 26, 27, 28, 31 |
| irp | 05, 08, 14, 16, 20 | 24 | 06, 10, 26, 27, 28, 31 |
| pension | 05, 08, 14, 20 | 24 | 06, 10, 26, 28, 31 |

날짜는 관측일이며 일별 종료 상태나 계좌·feeder의 동시 complete state를 의미하지 않는다.

- 7/06·7/29 brokerage raw balance에 각 국내 보유 **2종목**이 있고, 7/24 brokerage raw 두 envelope도
  각 2종목/동일 content hash다. 필수 identity/quantity/value 누락·numeric parse error·배열 내부 종목 중복 0.
  이 두 추가 날짜는 원본이 없는 문제가 아니라 **overview-driven 변환의 coverage 제한**이다.
- 7/24 normalized holding은 ria 7, isa 2, irp 6, pension 3, brokerage 6종목(국내 2+해외 4).
  종목 유니온 20개. brokerage cash row 0, 해외 4행 value_krw NULL.
  국내 4계좌에는 각 KRW cash 1행이 있다. IRP output2는 dict, 다른 계좌는 list이므로 동일 parser 금지.
- 7월 V2 dual-basis 가격 **18종목/36 partitions**, raw 396 + adjusted 396행;
  각 종목 22개 session, 시장별 날짜 유니온 23일. KRX 14종목, NAS 4종목.
  별도 KRX raw-only 1종목 22행이 더 있어 전체 814행/19종목.
  7/24 holding 20종목 중 19종목에 한 basis 이상의 당일 가격이 있고 `KRX/009150`에는 없음.
  세부 instrument/session/basis 범위는 aggregate inventory의 `july_price_symbols`에 있다.
- 6월 dual-basis 각 378행(+legacy raw 15), 8월 raw pass 373/adjusted pass 353(+legacy raw 13).
  다만 종목별 시장 calendar coverage와 historical holding universe는 별도로 판정해야 한다.
- 7월 가격 792행은 원천 가격 사실로 사용 가능한 현재 V2 rows지만 historical knowledge는 8/28 또는 10/13이다.
  22 raw-only행은 effective/knowledge/revision provenance가 NULL. 현재 price `operational_strict` 표기도
  **7월 당시 알았다는 뜻은 아니다**. 792행을 historical strict PIT input으로 사용하면 안 된다.
- 7월 V2 trade **10건**: 7/01 ria 4, 7/02 ria/isa/irp/pension 각 1, 7/29 brokerage 2.
  quantity/price/side/source observation 필수 NULL 0. 부분 날짜 source event facts이지 전체 ledger complete 증명은 아니다.
- 6월 trade pass 48건/10일, 8월 pass 4 + partial_history 3 + inferred_correction 1.
- 7월 cash event **22건 전부 7/28 brokerage fee**; 6월 12건도 fee, 8월 없음.
  6·7월 governed FX 0, 8월 USD close 28/31 두 날짜. 과거 raw observation의 적용환율은 별도 관측 사실로만 고려하고
  daily FX나 transaction-applied FX로 자동 승격하지 않는다.
- 7월 overseas raw transaction 17 envelopes는 output1 배열 항목 **0개**다.
  fetch date/요청 start/end 범위가 거래 존재나 source completeness를 보증하지 않는다.

## Batch provenance follow-up

[Follow-up report](wi-068-v1-batch-provenance-2026-10-13.md) locates the pre-V2 batch/table inspection, matches the
three documented Jobs to their order/transaction/token commands and MotherDuck destination, profiles retained
batch tables, and verifies 313 historical audit records. July domestic terminal records are all failed (23), while
18 overseas and 23 token executions have successful terminal records. These commands do not collect total assets.
The fourth total-asset command exists in a closed-unmerged PR; 37 pre-V2 deployment runs/21 source SHAs and the
exact-name audit query establish no deployment of that command within the inspected scope. The owner's report of
another total-asset collector remains unresolved if it used another name/project/external source.

## Owner clarification — daily total first, 2026-10-13

Owner prioritizes **daily total-asset history**, with account detail deferred. Missing canonical completeness must not
be described as absence of any stored total. [Total-first coverage evidence](../../governance/project/evidence/wi068/total-first-coverage-2026-10-13.json)
records this distinction without disclosing monetary values.

| month | retained overview observations | distinct observed overview days | days with five account-total rows |
| --- | ---: | ---: | ---: |
| April (from 19th) | 18 | 7 | 7 |
| May | 14 | 9 | 8 |
| June | 6 | 5 | 4 |
| July | 1 | 1 | 1 |

All these stored overview total fields and account-total fields are non-null and positive. July 24 has all five
account total observations; July 6 and 29 have brokerage account totals. These are retained amounts, not universally
unusable data. July 24 also has domestic holdings and four overseas holding observations; its overseas `fx_data` is
empty and overseas KRW valuations/cash coverage are insufficient. It is not a verified global total.

The historic account extractor chooses among `tot_evlu_amt`, `scts_evlu_amt`, `tot_asst_amt`, `evlu_amt_smtl_amt`,
`dnca_tot_amt` and `dnca_tota`. Stored `total_eval_amt` must therefore be checked against source field meaning,
especially IRP, before treating the sum as comparable portfolio totals. Fetching external July FX can support a
labelled estimated KRW valuation but does not generate missing daily account balances or overseas cash.

V1 commit `32785ed` (June 14) configures domestic-order, overseas-transaction and token/health warm-up commands;
those commands do not collect total-asset snapshots. A separate August 2 commit `9dea94c`, retained only on the
`codex/portfolio-pipeline-reliability` branch, adds `collect-asset-overview-snapshot` and a daily 16:10 scheduler target.
Its code existence is not deployment/execution proof. The exact historical total-asset batch, activation date,
execution outcome and database destination remain an operational investigation gap. Snapshot rows lack a dedicated
MCP-versus-batch writer field, so sparse July observations cannot be conclusively attributed to manual MCP calls. A read-only Cloud Logging
query for June–July KST returned 153 retained records, split 51 each among domestic-order history,
overseas-transaction history and token warm-up Jobs. These are log-record counts, not executions or successful
collections. No total-asset snapshot Job execution was established by this result; current Job listing was
unavailable. External/manual schedules or a different storage destination remain possible and must be traced
before explaining the owner's remembered daily collection as a quality or loss incident.

## Grain·시간·필드 매핑 및 품질

| 종류 | legacy grain / time | V2 field mapping 후보 | 불확실성·금지 |
| --- | --- | --- | --- |
| portfolio snapshot | 계좌/API fetch, naive snapshot_at(KST writer convention), source effective time 별도 없음 | dataset.portfolio-position-observation → immutable observation; source_request/id/hash, fetched/observed timestamp | snapshot_at을 historical execution time으로 꾸미지 않음; request/pagination 완료와 당시 writer timezone 증거 필요 |
| holding | overview/account/market/symbol/currency/row; holding snapshot이 parent보다 수초 늦음 | account_label→reviewed account_id, NASD→NAS, pdno/symbol→instrument_id, hldg_qty/quantity→quantity, pchs_avg_pric→average_cost, currency→cost_currency | parent timestamp를 독립 fetch effective time으로 바꾸지 않음; grouping 전 duplicate/revision 해석; quantity NULL 0이어도 KRW value NULL 가능 |
| cash | symbol NULL의 overview cash row 또는 raw output2 요약 필드 | native currency amount→silver.cash_snapshots.amount; observation lineage | V1 mapper가 value_krw를 currency별 amount로 합산함. 외화 cash를 native amount로 간주 금지; dnca_tot_amt/settlement/IRP summary 의미 확인 필요 |
| valuation/total | overview refresh와 latest-per-KST-date | typed component fact→approved daily-state transform 후보 | value_foreign/native-currency와 value_krw 별도; NULL→0 금지; 총액/합계 일치만으로 pass 금지; watermarks·5계좌·해외 feeder evidence 필요 |
| price | symbol/exchange/date + stored adjusted flag, created_at knowledge proxy | session_date, price_basis, OHLCV, revision_hash, endpoint/request option, effective/knowledge/reconstruction_mode | V1 PK symbol/exchange/date는 두 basis 덮어쓰기 가능; KRX stored false의 모호성은 기존 quarantine 유지; missing provenance를 추정하여 strict로 승격 금지 |
| FX | currency/date/period, created_at | base/quote_currency, rate_date/rate_type, rate, observation link | period D만으로 close/applied rate를 증명하지 않음; missing July rate forward-fill은 estimate |
| trade | filled broker order aggregate, order_date/time + first/last_seen | dataset.trade-event, executed_at, side/qty/price/currency, original order identity, source observation/revision | 개별 fill을 발명하지 않음; corrected revision/current ledger 우선; historical broker-business identity duplicate(WI-064) 판정과 legacy inferred_correction 별도 |
| transaction/profit | query envelope 또는 summary/report; start/end logical query, fetched knowledge | envelope landing/reference report; 실제 transaction row만 cash event candidate | overseas summary 2행을 trade/cash fact로 변환 금지; fee/tax/settlement/FX 미상은 NULL 유지 |

- 조사한 table PK/명시적 key 중복 0, holding parent/account/market/symbol/currency group 중복 0.
  서로 다른 fetch의 같은 payload는 정상 반복 관측이며 7/24 brokerage에서 2→1 content version 확인.
- overview 57/57과 holding sum 숫자는 일치하지만 **24 overview groups에 NULL holding value**가 있다.
  SUM의 NULL 무시는 completeness 검증을 대신할 수 없다. 모든 legacy overview quality/is_complete는 NULL.
- 7월 가격 OHLC/domain 오류 0(검사: high<low, close<=0, volume<0), required provenance NULL 22행.
  이 검사는 전체 calendar, 모든 OHLC ordering 또는 vendor adjustment correctness의 완전 검증이 아니다.
- cash quantity NULL/symbol NULL은 의도된 grain이므로 holding position NULL과 구별한다.
- corporate_actions 0행; absence-of-action coverage가 증명됐다는 뜻이 아니다.
  opening state, complete cash flow, corporate action, fees, FX가 함께 없으므로 거래 역산 canonical 인정 금지.
- migration code의 Bronze `passed`와 오래된 Silver/Gold `passed` labels는 원본 보존/과거 mapping 기록이다.
  WI-066 view-only quarantine을 우회하는 근거가 아니다.

## Canonical / reference / estimated / unavailable compatibility matrix

`canonical`은 이미 승인된 native V2 facts 또는 **향후 승인·검증 후 승격 가능한 원천 사실**을 구별한다.
이 문서는 어떠한 legacy row도 새로 canonical로 승인하지 않는다.

| 질문/입력 | 6월 | 7월 | 8월 | 판정 조건 |
| --- | --- | --- | --- | --- |
| 당시 complete portfolio total / canonical return | unavailable(legacy 5일도 미평가) | unavailable(7/24 feeder gap) | native 28/31의 passing slot만 canonical; legacy 06/10/25/26/27 reference-only | 신규 canonical legacy total 후보 0; return은 total과 별도 cash-flow 계약 필요 |
| observed domestic holdings/quantity | reference-only; raw 관측일의 source-fact promotion 후보 | 7/06·24·29 brokerage와 7/24 다른 4계좌 reference-only; 파싱 가능한 source-fact 후보 | native 우선, raw additional dates reference-only 후보 | approved mapper, identity, original timestamps, request coverage, reconciliation을 모두 검증 후 fact 단위 승격 |
| legacy overseas holdings/native value | 일부 원본 reference-only | 7/24 해외 4종목 reference-only | legacy 해외 rows reference-only | native amount/qty 보존; missing KRW/FX/cash를 complete total로 승격 금지 |
| known raw/adjusted price | V2 18종목 두 basis source facts canonical | V2 18종목 두 basis source facts canonical; raw-only 22행 reference-only | V2 지원 범위 canonical; basis gap 명시 | 현재 지식으로 재구성한 가격 사실; historical PIT/performance에는 cutoff 제한 |
| exact-date daily FX | unavailable | unavailable | 8/28·31만 canonical USD close | raw observed applied FX는 reference-only 후보; July daily FX가 있다고 간주 금지 |
| actual trade event | native V2 pass 48건 canonical facts | native V2 pass 10건 canonical facts | pass 4건 facts; partial/inferred 4건 별도 reference | complete trade history 또는 daily portfolio reconstruction 아님 |
| fee event | 12 native fee facts canonical | 7/28 native fee 22건 canonical | unavailable | 입출금·settlement·FX completeness와 구별 |
| raw legacy aggregate/report | reference-only | reference-only | reference-only | 원본 value 있으면 원본 basis를 명시; inferred completeness 없음 |
| carry-forward quantity × historical price / interpolation | estimated | estimated | estimated | 별도 scenario, 가정/오차/미관측 cash·FX 표시; 실제 observed state/return/tool 결과로 섞지 않음 |
| 거래내역 역산 full daily total | unavailable | unavailable | legacy 기간 unavailable | opening/cash/action/fee/FX의 완전 coverage 미충족 |
| historical strict PIT replay | knowledge evidence 없는 범위 unavailable | 미래 fetched price 사용시 unavailable | cutoff 이전 knowledge만 가능 | `retrospective_reconstructed`와 현재 knowledge를 당시 knowledge로 바꾸지 않음 |

**손실/조회/변환 구분:** 비교한 snapshot family에 삭제 증거 없음. July 추가 raw 날짜는 변환/읽기 경계;
가격 basis 문제는 조회/식별자 문제로 별도 defect 범위. 미관측 날짜/FX/feeder/cash/action은 실제 evidence gap이며
이 조사만으로 과거 수집 실패·삭제·업데이트 덮어쓰기 중 원인을 모두 확정하지 않는다.
V1 price PK 구조상 basis 덮어쓰기 가능성은 있지만 이번에는 실제 overwrite lineage를 증명하지 않았다.
`get-market-history` 구현 수정은 WI-068에 포함하지 않았고 현재 checkout이 request.adjusted에서 basis를
선택하는 코드도 확인했다. 원 보고의 결함 위치/실제 client 동작은 독립 defect 조사 소유다.

## 세 아키텍처 대안 비교 — 미승인 proposal

| 기준 | immutable legacy landing + V2 compatibility transformation | owner-only noncanonical reference dataset/read model/API | bounded hybrid |
| --- | --- | --- | --- |
| 정확성 | facts에는 좋음; broad legacy total promotion은 evidence gap 때문에 막힘 | 원본 관측에 충실; canonical 혼동을 envelope에서 방지해야 함 | source-grounded fact만 승격, 불완전 aggregate는 reference; 가장 명확한 경계 |
| 구현량 | 높음: parser/identity/bitemporal mapping, contracts, migrations, all types reconciliation | 낮음~중간: 별도 contract/query/envelope/권한과 API 필요; 새 API는 별도 승인 | 중간: 좁은 source-fact mapping+bounded reference projection; 중복 저장 최소화 |
| 데이터 수명 | 장기 lineage 유지, 낮은 가치의 mapper도 계속 유지 | 역사 질문 빈도가 줄면 consumer를 deprecate 가능, 원본은 보존 | historical fact 장기 유지, reference consumer는 측정된 사용에 따라 축소 |
| 보안 | confidential landing+V2 ownership, raw payload 접근 최소화 | owner-only auth/scope, canonical 소비 경로와 분리, raw URI/account suppression | 동일 원칙; fact와 reference를 혼합 응답할 때 provenance/권한 강제 |
| 비용 | 반복 copy/transform와 backup storage/query 비용 가장 큼 | bounded existing-storage reads, 상시 service 불필요; 쿼리 비용 측정 필요 | 필요한 facts만 처리, 새로운 저장소/상시 process 없이 시작 가능 |
| rollback | versioned transform 비활성화, native overwrite 금지, 원본 보존 | reference consumer 비활성화, 데이터/원본 삭제 불필요 | promotion version/reference consumer 독립 비활성화, native V2 영향 없음 |
| MCP 사용성 | 기존 tool로 잘 이어짐; partial을 canonical처럼 보일 위험 | explicit reference mode/새 tool 선택 필요; LLM 오용 경계 필요 | 기존 canonical native tools 우선 + 명시적 reference 접근; estimated는 별도 scenario |
| native V2 우선순위 | date/slot/account/instrument exact identity별 native 우선, collision no-overwrite | canonical 경로에 fallback하지 않음 | exact native precedence; absence를 legacy 자동 fallback으로 해석하지 않음 |

추천: **hybrid를 사실 승격 최소 범위로 제한**한다. 먼저 기존 immutable backup/observations를 content-addressed
provenance로 연결하고 raw balance의 미노출 관측일·account quantity/native cash facts의 계약을 검토한다.
현재 V2에서 이미 존재하는 price/trade facts는 재수입하지 않는다. uncertain aggregates, report, applied FX는
reference-only로 유지하고 canonical total/return metrics와 alert inputs가 소비하지 못하게 한다.
새 상시 API/서비스를 먼저 만들지 않고 owner longitudinal 질문의 실제 재사용을 측정한 후 reference consumer를 결정한다.
raw 자료는 유지하되 native V2가 쌓이면 reference 소비 필요가 줄어드는지 90일 후 검토하는 안을 제안한다.
90일은 **consumer 재검토 시점 제안**이지 raw retention 만료나 자동 삭제가 아니다.

## 필요한 owner 결정과 다음 gate

1. hybrid boundary를 선택할지, 별도 reference-only boundary로 시작할지 ADR/DEC 승인.
2. source fact의 범위: 국내 observed quantity/average cost/native cash까지 허용할지;
   global total/return 승격 금지와 timestamp/pagination 미확정 시 reference 유지 규칙 승인.
3. owner-only reference 소비 방식: 기존 tool의 명시적 reference option 또는 새 bounded read model/tool/API 중 선택.
   public schema/scope 변경은 별도 계약·승인과 actual Codex/Claude positive/partial/error acceptance가 필요하다.
4. native precedence/idempotency key, conflict adjudication, timezone/knowledge policy, append-only lineage/rollback 승인.
5. retention/consumer 재검토 시점, query/page/response/cost 상한과 private raw 접근 정책 승인.

승인 뒤에만 proposed DGH contracts/ADR를 등록·검토하고 mapping·restore rehearsal·implementation 계획을 구체화한다.
이 세션은 architecture decision boundary에서 멈춘다. WI-068 전체 acceptance와 실제 MCP 인수는 미완료다.

## 검증

- quick: Python 3.13.3 + 임시 UV cache로 pass. 최초 uv cache sandbox 접근 오류는 데이터 공백으로 처리하지 않았다.
- SQL profiler의 예약 alias parser 오류는 수정 후 재조회; 실패 결과를 empty coverage로 사용하지 않았다.
- GCS ADC 없음과 gcloud sandbox 인증 접근 문제는 기존 사용자 인증의 read-only 실행으로 해결했다.
- local Parquet 473/473 readable; V1 snapshot family 8개 비교 missing/changed 모두 0.
- GCS 20/20 manifest hash pass; 참조 1,140건 missing/size mismatch 0; 실제 전체 payload hash/restore는 미실행.
- full shared gate: 최종 문서·evidence를 포함해 815 tests passed, 1 warning (35.12s).
