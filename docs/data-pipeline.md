# Data Pipeline Direction

이 프로젝트의 현재 쓰기 경로는 MCP tool이 KIS API에서 데이터를 받아 MotherDuck에 저장하는
OLTP 성격이 강하다. 하지만 장기 목표는 포트폴리오 분석, 시계열 비교, 이상치 탐지 같은 OLAP
워크로드다. 따라서 저장 계층과 분석 계층을 섞지 않는 방향으로 설계한다.

2026-08-28 승인된 V2 목표에서는 Scheduler와 LLM 요청이 동일한 allowlisted managed pipeline registry를
호출하고, fixed Job args와 Firestore의 run request·lease·idempotency claim을 사용한다. MotherDuck은
`bronze/silver/gold/control` 데이터 plane을 맡는다. 이 문서 아래의 현재 V1 쓰기 경로는 별도 pipeline
Work Item과 dual-run 전까지 그대로 유효하다.

## 원칙

1. Raw 데이터는 가능한 한 보존한다.
2. 중복 제거와 대표값 선택은 raw write path에서 하지 않는다.
3. 분석용 정제 데이터는 view, table, 또는 별도 pipeline 단계에서 만든다.
4. 로컬 DuckDB는 운영 중심 DB가 아니라 백업/검증/개발용이다.

## V2 Managed Runtime 구현 기준선

`src/kis_portfolio/platform/pipeline.py`는 `(pipeline_id, version, logical_date, slot, partition)`을 hash한
logical idempotency key, run/stage ledger, source-call budget과 stage resume를 구현한다. 성공 stage는 재시도
때 건너뛰고 실패 stage부터 이어가며, 이미 성공한 logical run은 같은 `run_id`를 반환한다. quality와
lineage는 `control.quality_results`, `control.lineage_edges`에 저장하고 DB-only read model로 조회한다.

승인된 initial registry는 다음과 같다.

- `pipeline.owned-portfolio-core-v2`
- `pipeline.etf-lookthrough-v2`
- `pipeline.fundamentals-dividends-v2`
- `pipeline.macro-profile-v2`
- `pipeline.owner-research-pdf-v1`

WI-012의 첫 production adapter는 `kis-portfolio-batch collect-owned-portfolio-v2`다. 허용 slot은
`kr-1000`, `kr-1430`, `kr-1600`, partition은 `all-accounts` 하나뿐이다. 각 slot은 별도 fixed-argument
Cloud Run Job이며 build-once image digest를 공유한다. 10:00 slot은 미국 최근 마감 입력도 함께 읽고,
최근 7일의 source history에서 latest applicable session을 선택해 주말·한국 휴일 gap을 메운다. 모든 raw
bundle은 recursive secret redaction과 account masking 후 private GCS에 content hash로 랜딩한다.

WI-015의 `pipeline.price-history-v2`는 계좌 snapshot 수집과 분리된 held-instrument price partition을 사용한다.
국내와 해외 endpoint의 수정주가 option 의미를 따로 고정하고, page raw observation과 normalized content
revision을 함께 남긴다. 오늘 수집한 과거 일봉은 `retrospective_reconstructed`이며 strict historical alert
input으로 승격하지 않는다. backfill은 instrument/basis당 최대 10 page, 전체 최대 400 physical call을 호출
전에 예약하며 반복 cursor·continuation은 partial 성공이 아니라 실패다.

WI-016부터 국내 주문 이력은 조회일 기준 recent/old TR을 분할하고 각 구간의 FK/NK continuation을 끝까지
소비한다. 해외 기간거래는 거래행이 있는 `output1`을 정규화하며 체결가·수수료·적용환율·결제일의 원천
필드를 보존한다. 국내 side code는 `01=sell`, `02=buy`만 승인하고 그 밖의 값은 lot을 만들지 않는다.
V1의 all-buy 오염은 원행을 수정하거나 삭제하지 않고 `silver.trade_event_revisions`에 append한다.
분석 소비자는 최신 revision인 `silver.trade_events_current`와 buy만 남긴
`silver.purchase_lots_current`를 사용한다. 신규 canonical identity는 account, market, product code,
instrument, broker order, executed time, execution sequence를 포함한다.

WI-021-S01은 이 원천 경계를 3년 backfill의 결정적 60일 partition으로 투영한다. 국내 shard는 조회일 기준
90일 old/recent 경계를 넘지 않고, IRP recent와 승인된 국내 cash-history source 부재는 호출 대상이 아닌
`known_gap`으로 보존한다. 해외 주문과 기간거래는 별도 partition이며 기간거래만 trade/cash 후보를 함께
낸다. `plan-trade-cash-backfill-v2`는 공개 manifest만 출력하고 source call, DB write, 호출 예산 강제나
resume을 수행하지 않는다. 상세 계약은
[WI-021-S01 backfill partition plan](./design/wi-021-s01-backfill-partition-plan.md)에 둔다.

WI-021-S02는 S01 partition을 바꾸지 않고 별도 budget hash로 source별 page와 전체 physical-call ceiling을
적용한다. 기본값은 국내 주문 3 page, 해외 주문 3 page, 해외 기간거래 2 page, 전체 400 call이다. 전체
partition의 최악 page 합계를 실행 전에 예약하지 못하면 call gate를 만들지 않으며, 각 실제 source
request도 `run_budgeted_physical_call`이 partition/global quota를 먼저 원자적으로 예약한 뒤에만 수행한다.
한도 소진, unknown partition과 known gap은 외부 호출 전에 실패한다. 상세 계약은
[WI-021-S02 call budget](./design/wi-021-s02-call-budget.md)에 둔다.

WI-021-S03은 `pipeline.trade-cash-backfill-v2`를 기존 Control runner에 별도 등록한다. logical identity는
pipeline/version/end-date/backfill slot/partition key이며, 완료 partition은 재사용하고 실패 partition은 같은
run id에서 재개한다. 각 physical-call reservation은 I/O 전에 stage row에 기록되어 process restart 뒤에도
page/global budget에서 차감된다. source stream watermark는 quality 이후 publish에서만 연속·단조 증가한다.

WI-021-S04는 guarded fixture page를 content-based immutable row observation으로 landing하고, 주문 source의
official side·체결수량·가격만 Silver trade fact로 만든다. 해외 period transaction은 주문 fact와 병합하지
않는 trade candidate observation으로 남기며, 원천에 명시된 settlement·fee·tax만 별도 cash fact로 만든다.
pagination이 불완전하면 Bronze observation은 보존하지만 Silver publish와 watermark를 차단한다. 이 단계는
purchase lot을 만들지 않으며 lot/position replay는 WI-022가 담당한다.

WI-017의 instrument 분류는 `silver.instruments`의 current compatibility 값과 별도로
`silver.instrument_versions`에 knowledge/effective 시점별 version을 남긴다. 분류 precedence는 reason과
유효기간이 있는 owner override, KIS master group code, exact ETF route, unknown 순서다. 경제적 노출은
구성종목 없이 이름만으로 canonical 값이 되지 않는다. ETF provider 선택은
`governance/catalog/etf-instrument-routes.toml`의 exact route만 허용한다.

WI-019의 trend metric evaluator는 `silver.price_bar_revisions_daily`의 adjusted 일봉을 evaluation cutoff로
point-in-time 선택해 SMA20/50/120, volume SMA/ratio20, Wilder RSI14, population-standard-deviation Bollinger
20/2 context와 Wilder ATR20을 `gold.metric_values`에 저장한다. 장중 slot은 마지막 완료 일봉까지만 사용한다.
필요 이력이 없으면 `insufficient_history`, 필드가 없으면 `missing_price_field`로 null을 기록한다. 오늘
수집한 과거 일봉의 `retrospective_reconstructed` 상태는 그대로 보존하며 strict metric 값으로 승격하지 않는다.

TIME·KoAct·RISE·PLUS parser는 합성 fixture bytes만 처리하는 offline pipeline으로 먼저 검증한다. 현재 네
profile의 rights와 activation은 `fixture_only`라 source call count는 항상 0이며 HTTP client, Cloud Run Job과
Scheduler가 없다. 동일 source date의 다른 file hash는 quarantine하고, missing weight나 incomplete page는
Silver publish를 차단한다. 실제 issuer 수집은 provider별 rights가 모두 allowed가 되는 별도 Work Item이다.

`tests/fixtures/v2/`의 합성 KIS·공식 reference fixture는 credential과 실제 계좌번호를 포함하지 않는다.
`src/kis_portfolio/platform/rehearsal.py`는 이 fixture를 Bronze→Silver→quality→Gold로 실행해 idempotency,
lineage와 daily state를 검증한다. 이 rehearsal은 production source 호출이나 실제 3년 backfill이 아니다.

## 계층

논리 계층은 Bronze/Silver/Gold와 별도 Control/Security 영역으로 고정한다. 현재 물리 객체는 모두
`kis_portfolio.main`에 있지만, 객체마다 목표 schema가 지정되어 있다.

```text
KIS API observations -> Bronze -> Silver -> Gold -> MCP / analytics / dashboard
                                  ^
                                  |
                               Control

Security -> auth/token repositories only
```

- Bronze: append-only KIS 관측과 replay 가능한 raw JSON
- Silver: 정규화 시계열, deduplicated order/transaction, canonical total assets
- Gold: 일별 대표값과 재생성 가능한 분석 view/table
- Control: migration, 시장 달력, 종목마스터, classification override
- Security: 현재 V1은 암호화/해시된 token과 OAuth state를 MotherDuck에서 격리한다. 승인된 V2는 이를
  Firestore와 Secret Manager로 이동한다.

전체 객체 목록, grain, key, 민감도, 백업 정책과 물리 schema 전환 계획은
[Data Store Governance and Catalog](./data-catalog.md)가 관리한다. 이 문서에서는 객체 목록을
중복 관리하지 않고 데이터가 계층 사이를 이동하는 방식만 설명한다.

## 스냅샷 중복 처리

`portfolio_snapshots`는 append-only raw table이다. 같은 계좌를 같은 날 여러 번 조회해도 raw row는
보존한다. 이는 다음 이유 때문이다.

- LLM/MCP 호출 이력을 감사할 수 있다.
- API 응답 구조 변경이나 파싱 오류를 나중에 재처리할 수 있다.
- 분 단위/일 단위 대표값 정책을 나중에 바꿔도 raw를 잃지 않는다.

분석에서는 Bronze table을 직접 쓰지 않고 Silver canonical table 또는 Gold view를 먼저 사용한다.

`order_history`도 같은 원칙을 따른다. 같은 계좌와 같은 기간을 같은 날 여러 번 조회하거나,
오전 수동 조회 뒤 장마감 배치가 다시 적재하더라도 raw row는 보존한다. 이 테이블은 이제
주문조회 coverage와 raw audit 목적의 snapshot 저장소로 본다.

중복집계 방지를 위한 Silver serving 기준 저장소는 `domestic_orders`다. 이 테이블은 append-only가 아니라
KIS 주문 식별자 기준 upsert를 사용한다. 현재 국내주식 주문의 canonical key는 다음과 같다.

- 계좌 식별: `(account_id, account_product_code)`
- 주문 식별: `(order_date, order_branch_no, order_no)`

즉 전체 primary key는 `(account_id, account_product_code, order_date, order_branch_no, order_no)`이다.
여기서 `order_no`와 `order_branch_no`는 KIS `주식일별주문체결조회(inquire-daily-ccld)` 응답의
`odno`, `ord_gno_brno`를 사용한다. `pdno`와 `ord_tmd`는 속성으로 저장하되 key에는 포함하지 않는다.

`get-order-list`와 `collect-domestic-order-history` 배치는 모두 같은 canonical upsert 경로를 탄다.
장중 수동 조회와 장마감 배치가 같은 주문을 다시 가져와도 기존 row를 최신 상태로 갱신하고, 통계는
`domestic_orders`만 읽도록 한다.

해외주식은 같은 원칙을 따르되 조회 성격별 raw 저장소를 분리한다.

- `overseas_order_history`: 해외주식 주문체결내역 raw snapshot
- `overseas_orders`: 주문번호/주문일/거래소 기준 canonical upsert
- `overseas_transaction_history`: 해외주식 일별거래내역 raw snapshot
- `overseas_transactions`: raw row hash 기준 canonical upsert
- `overseas_settlement_balance_snapshots`: 해외주식 결제기준잔고 raw snapshot

현재 제공하는 Gold view:

```sql
portfolio_daily_snapshots
asset_overview_daily_snapshots
```

이 view들은 계좌별 또는 canonical snapshot별 일자 마지막 스냅샷을 대표값으로 사용한다.

## 향후 정제 작업 후보

- `portfolio_minute_snapshots`: 같은 계좌의 같은 분 내 마지막 스냅샷
- `account_nav_daily`: 계좌별 일별 평가금액, 현금, 보유 평가금액, 환산 금액
- `fx_daily`: 환율 데이터를 분석용 currency/date grain으로 표준화
- `trade_profit_normalized`: 손익 JSON을 종목/기간 단위로 정규화
- `domestic_order_fills_normalized`: 필요해지면 주문/체결 JSON을 체결 단위로 더 세분화
- `market_session_calendar`: 시장별 거래일/휴장일/마감시간 계약

이 작업들은 `scripts/`의 일회성/배치 스크립트나 향후 `pipelines/` 패키지로 분리할 수 있다.

## 구현 위치

- object governance registry: `src/kis_portfolio/db/catalog.py`
- source/dataset/collection/metric/pipeline registry: `governance/catalog/`
- data governance policy and gates: `docs/governance/data-governance-harness.md`
- current physical DDL and Gold view SQL: `src/kis_portfolio/db/schema.py`
- Bronze/Silver/Control repositories: `src/kis_portfolio/db/repository.py`
- analytics SQL: `src/kis_portfolio/analytics/`
- backup: `scripts/backup_motherduck.py`

새 수집·dataset·metric·pipeline은 DGH manifest를 proposed로 먼저 등록한다. 새 물리 객체는 data catalog에
layer/grain/key/backup/sensitivity를 선언한다. 물리 schema 분리 전까지도 이 논리 계약은 즉시 적용되며,
`main`에 코드 밖 객체를 임의 생성하지 않는다.
