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
- `pipeline.alert-evaluation-v2`

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

WI-021-S05는 같은 pipeline에 실제 KIS page adapter를 연결한다. 공통 pagination engine은 각 business HTTP
직전에 durable reservation hook을 호출하고, 승인된 page 한도에서 continuation이 남으면 partial page를
Bronze에 보존한 뒤 publish를 차단한다. 운영 명령은 기본 preflight이며 exact date·plan hash·budget hash,
MotherDuck mode, 영향 테이블을 포함한 pre-backup manifest와 `--apply`가 모두 맞아야 source/DB를 연다.

WI-017의 instrument 분류는 `silver.instruments`의 current compatibility 값과 별도로
`silver.instrument_versions`에 knowledge/effective 시점별 version을 남긴다. 분류 precedence는 reason과
유효기간이 있는 owner override, KIS master group code, exact ETF route, unknown 순서다. 경제적 노출은
구성종목 없이 이름만으로 canonical 값이 되지 않는다. ETF provider 선택은
`governance/catalog/etf-instrument-routes.toml`의 exact route만 허용한다.

DEC-049 이후 ETF constituent pipeline은 초기 V2의 `later` 범위다. fixture parser와 exact route는 보존하지만
production source call, schedule, Silver publish와 look-through consumer는 비활성이다. 초기 V2는 ETF를
자체 상장상품으로만 분석하며 내부 노출을 이름이나 KIS partial 구성으로 추정하지 않는다.

WI-019의 trend metric evaluator는 `silver.price_bar_revisions_daily`의 adjusted 일봉을 evaluation cutoff로
point-in-time 선택해 SMA20/50/120, volume SMA/ratio20, Wilder RSI14, population-standard-deviation Bollinger
20/2 context와 Wilder ATR20을 `gold.metric_values`에 저장한다. 장중 slot은 마지막 완료 일봉까지만 사용한다.
필요 이력이 없으면 `insufficient_history`, 필드가 없으면 `missing_price_field`로 null을 기록한다. 오늘
수집한 과거 일봉의 `retrospective_reconstructed` 상태는 그대로 보존하며 strict metric 값으로 승격하지 않는다.

WI-036의 `pipeline.corporate-actions-v2`는 승인된 KIS 원천의 국내 예탁원 합병·분할/액면교체 일정과 해외
기간별 권리조회를 보유상품 범위의 immutable observation과 `silver.corporate_action_revisions`로 정규화한다.
같은 source identity의 동일 content는 no-op이고 예정→확정·조건 변경은 knowledge time이 증가하는 새 revision이다.
확정되고 positive pre/post units가 있는 분할만 reciprocal quantity/price effect를 만들며, 종목변경은 결과
instrument가 확인된 경우에만 identity effect를 만든다. action이 없다는 관측 coverage와 action 조건을 모른다는
상태를 구분하고, unknown·provisional·incomplete terms는 lot/return 계산 가능 판정을 fail-closed로 유지한다.
action이 없다는 판정도 `control.quality_results`의 종목·기간 coverage가 `pass`일 때만 허용하며, 생성한
price·quantity·instrument effect는 공통 `control.lineage_edges`에서 원 action revision을 인용한다.
WI-036은 offline fixture와 local backup/restore까지만 수행하며 production source call과 schedule은 별도 gate다.

WI-022-S02의 migration `0010`은 기존 WI-010 `silver.purchase_lots`와
`silver.sell_allocation_revisions` row를 수정하지 않는다. 새 canonical path는 position episode identity/revision,
actual·manual·inferred-opening lot identity/state revision, sell allocation whole-revision header와 기존 lot slice,
Control exception identity/revision을 additive object로 둔다. current view는 knowledge time과 revision으로 최신
whole revision을 선택하며, 기존 compatibility lot view와 새 reconstructed lot-state view를 혼합하지 않는다.
이 단계는 구조와 local recovery만 검증하고 trade replay, FIFO persistence와 production migration은 수행하지 않는다.

WI-022-S03의 pure replay는 passing canonical trade revision과 governed corporate-action effect를 stable effective
order로 재생한다. 현재 broker quantity에서 역산한 시작 잔량은 complete action coverage와 source gap 부재가
확인된 경우에만 `inferred_opening` candidate가 되며 execution price/cost를 만들지 않는다. 전량 청산은 position
episode를 닫고 후속 매수는 새 episode를 연다. 동일시각 tie, lineage 불일치, 수량 불일치와 evidence blocker는
derived fact 없이 fail closed한다. 이 단계의 결과는 memory-only plan이며 S02 객체 저장은 S04까지 금지한다.
상세 계약은 [WI-022-S03 deterministic replay](./design/wi-022-s03-deterministic-replay.md)에 둔다.

WI-022-S04는 S03의 input `replay_hash`와 candidate-fact `projection_hash`를 모두 검증한 뒤 migration `0010`의
episode, lot-state, whole sell-allocation, exception revision을 단일 transaction으로 publish한다. 같은 hash는
revision/slice를 추가하지 않고, 변경된 input은 knowledge time이 증가할 때만 append한다. blocked plan은 Silver
fact 없이 Control exception만 열며 같은 partition의 후속 reconciled plan이 이를 append-only로 resolve한다.
commit 전 current view와 plan의 episode/lot/allocation 수량을 다시 대조하고 실패하면 전체 rollback한다.
fresh DuckDB complete V2 Parquet restore까지 S04에서 검증하지만 production DB 적용은 S06까지 금지한다. 상세
계약은 [WI-022-S04 append-only persistence](./design/wi-022-s04-append-only-persistence.md)에 둔다.

WI-022-S05의 production planner는 passing current-position snapshot과 canonical trade current view를 read-only로
읽고 account/instrument identity를 노출하지 않는 aggregate impact report만 만든다. 해시 입력의 timestamp는 UTC
`Z`, Decimal은 scale-independent canonical string으로 정규화한다. 같은 logical input, replay 및 projection은
runtime timezone과 additive schema migration 여부와 무관하게 같은 execution hash를 갖는다. 2026-08-28 cutoff의 실제
검사에서는 corporate-action date-range coverage가 0건이므로 57개 partition 전부가 `not_assessed`다. 따라서 S06은
Silver episode/lot/allocation을 생성할 수 없고 append-only Control exception만 발행할 수 있다. 상세 근거는
[WI-022-S05 production dry-run](./design/wi-022-s05-production-dry-run.md)에 둔다.

WI-022-S06은 `all`에 포함되지 않는 one-off managed release다. tested `master`의 같은 immutable image로 migration
`0010`과 apply Job을 배포하고, S05의 exact hash/count가 맞을 때만 pre-backup upload/download/fresh restore를
완료한 뒤 append-only repository를 호출한다. 같은 plan을 두 번 적용해 두 번째 revision 증가가 0임을 확인하고,
post-backup을 별도 fresh DuckDB로 복원해 live와 같은 aggregate reconciliation을 요구한다. 현재 승인 입력에서는
Control exception 57건만 publish할 수 있고 Silver reconstruction row와 V1 row는 쓰지 않는다. 상세 계약은
[WI-022-S06 production execution](./design/wi-022-s06-production-execution.md)에 둔다.

WI-023의 W0502 evaluator는 인접한 pass `gold.portfolio_daily_state`와 평가 cutoff 이전에 알려진 canonical
cash classification만 읽는다. `main.market_calendar`의 KRX 날짜 coverage, 양일 필수 계좌와 state 품질,
`control.quality_results`의 exact cash-flow coverage scope가 모두 맞아야 Modified Dietz 수익률과 구성요소
기여도를 발행한다. 기여도 합계와 수익률의 차이는 별도 residual metric으로 보존하고, wealth index는 최초
기준값 1에서 pass 기간수익률만 chain-link한다. 한 기간이라도 unavailable이면 wealth/drawdown chain을
재시작하지 않는다. non-KRW 외부 현금흐름은 point-in-time FX revision 계약이 생기기 전까지 fail closed한다.
이 단계는 기존 `gold.metric_values`와 `control.metric_definitions`만 사용하며 source call, schema migration,
public MCP 또는 production schedule을 추가하지 않는다. 상세 계약은
[WI-023 portfolio performance](./design/wi-023-portfolio-performance-contract.md)에 둔다.

WI-024의 owner-review workflow는 새 source call 없이 기존 thread, journal과 sell-allocation projection을
읽어 누락 항목의 stable review identity와 `open` revision만 만든다. Typed reference/stop/risk budget은 owner
actor가 optimistic revision으로 별도 Silver plan revision에 기록할 때만 권위 입력이 된다. system 또는 LLM
제안은 `advice_metadata`로만 남고, review 답변은 authoritative revision reference를 가리킨다. 운영 migration,
public MCP write와 자동 review schedule은 이번 단계에서 활성화하지 않는다. 상세 계약은
[WI-024 thread risk review](./design/wi-024-thread-risk-review-contract.md)에 둔다.

WI-025의 W0504 evaluator는 reconstructed episode/lot revision, operational-strict adjusted price path, 동일 slot의
canonical Gold quantity와 owner-authoritative risk plan만 point-in-time으로 읽는다. lot MFE/MAE와 episode
high/drawdown은 zero-quantity episode 경계를 넘지 않으며, thread planned loss는 open quantity에 owner
reference-stop과 cutoff FX를 적용한다. 모든 open lot이 정확히 한 thread에 연결되고 instrument 합계까지
reconcile될 때만 숫자를 발행한다. 누락 plan, partial reconstruction, 미래 revision, canonical quantity mismatch는
0이 아니라 명시적 non-pass `NULL` metric으로 보존한다. 이 evaluator는 source call, 신규 schema, public MCP,
Telegram 또는 주문 권한을 추가하지 않는다. 상세 계약은
[WI-025 lot/thread risk metrics](./design/wi-025-lot-thread-risk-contract.md)에 둔다.

WI-028의 `pipeline.alert-evaluation-v2`는 승인 rule version과 point-in-time metric만 읽어
`gold.alert_candidates`와 append-only state revision을 만든다. alert identity는 rule/version과 opaque subject에
안정적이며 slot을 가로질러 같은 fingerprint를 중복 전송하지 않는다. candidate identity는
`kr-1000`·`kr-1430`·`kr-1600` 또는 exact `us-close` session/slot을 포함해 scheduler retry에는 같고 다른
평가 기회에는 다르다. non-pass quality는 candidate로 감사 가능하게 남지만 이전 active state를 회복시키거나
dispatch claim을 만들지 않는다. 진입·상향·회복·재진입만 exact numeric watch floor에서 claim 가능하며 WI-028의 유일한
mode/channel은 DB `shadow`다. claim lease token은 digest만 저장하고 `unknown` post-send outcome은 자동 재시도하지
않는다. ETF는 자체 상장상품 metric만 사용하고 constituent exposure는 missing으로 유지한다. 실제 threshold
calibration과 2주 shadow는 WI-029, Telegram API와 external mode는 WI-030이 담당한다. 상세 계약은
[WI-028 alert state and delivery ledger](./design/wi-028-alert-state-delivery-ledger-contract.md)에 둔다.

`pipeline.telegram-delivery-v2:1.1.0`은 기존 scale-to-zero monitoring Job 뒤에서만 합성되는 outbound-only
consumer다. `KIS_TELEGRAM_DELIVERY_ENABLED`의 기본값은 `false`이며, 이 상태에서는 candidate 조회, dispatch
claim과 network request를 모두 만들지 않는다. 활성 상태에서도 `active external` rule, 최신 owner approval,
`pass` quality와 delivery-required transition이 모두 있어야 Telegram 후보가 된다.

DEC-050 bounded canary에서는 `bootstrap-1.0.0` shadow rule을 그대로 실행한 뒤 별도
`canary-2026-09-01.1` external rule로 같은 point-in-time 입력을 평가한다. 두 rule의 candidate와 state identity는
분리되며, external rule은 2026-09-01 00:00부터 2026-09-08 00:00 KST 전까지만 유효하다. eligibility와 claim
양쪽이 dispatch time의 유효기간을 검사하므로 만료 뒤 retry나 새 전송은 fail closed한다. `주의` 이상
상태전이는 false alarm 후보를 포함해 보내고, normal·non-pass·no-change는 DB 증거로만 남긴다.

메시지는 `public_context` allowlist에서 plain text로 다시 렌더링하고 전체 계좌번호, 총자산 절대액,
credential, raw source와 chat identifier를 거부한다. Telegram message ID는 원문 대신 hash로 delivery ledger에
남긴다. 명시적인 429/5xx만 다음 scheduled run에서 retryable이고, post-send timeout과 transport ambiguity는
terminal `unknown`이라 자동 재전송하지 않는다. WI-030-S01은 이 경로를 code와 offline test로 준비했고,
DEC-050이 destination test와 7일 canary external flag를 WI-030-S02에 승인했다. permanent rule은 WI-029 인수
뒤에만 가능하다.
전체 payload, outcome과 activation 계약은
[WI-030 Telegram delivery contract](./design/wi-030-telegram-delivery-contract.md)에 둔다.

WI-029-S04는 기존 V2 scale-to-zero Job을 새 서비스 없이 확장한다. 각 Job은 raw와 adjusted 일봉을 동일한
고정 보유범위에서 operational-strict revision으로 landing한 뒤, 승인된 일간수익률·vol20·SMA·거래량·RSI·
Bollinger 계약을 메모리에서 평가하고 candidate lineage hash를 보존한다. 최신 bar만 live strict를 요구하며,
cutoff 전에 알려진 3년 reconstructed adjusted history는 지표 window 입력으로 사용할 수 있지만 과거 live
alert로 표시하지 않는다. `kr-1000`은 국내 10시와 전일 미국 close session을 함께 평가하고 다른 두 Job은
각 국내 slot만 평가한다. transport는 `shadow` claim과 DB 내부 완료 기록뿐이며 Telegram adapter나 secret은
이 실행 이미지·환경에 없다.

WI-029-S05는 KRX calendar와 고정 10:00, 14:30, 16:00 schedule(10:00의 prior U.S. close 포함)에서
**due evaluation-date/slot**을 먼저 만들고, 그 뒤 후보의 evaluation date/slot과 대조한다. 따라서 후보가
전혀 생성되지 않은 scheduled slot도 자기참조로 정상 처리되지 않는다. 이 refresh는 existing scale-to-zero
Job 완료 후와 `kis-portfolio-batch review-wi029-s05`에서 실행하는 MotherDuck-only operation이며 provider
또는 Telegram 호출을 하지 않는다.

같은 오전 Job은 현재 보유 해외 `unknown`만 최대 8개 골라 KIS 상품정보와 SEC exact ticker/CIK/SIC가 모두
일치할 때 append-only instrument version을 추가한다. 최초 최대 17 calls 뒤 정상상태는 0 calls이며 이름
heuristic, 임의 symbol, 기존 version rewrite는 금지한다.

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

## 원화 평가액 변화 기여도

WI-033은 양일 canonical daily state를 동일한 계산 계약으로 비교한다. V1은
`asset_overview_daily_snapshots`와 `asset_holding_snapshots`를 읽어 기존
`get-total-asset-daily-change`에 additive diagnostic field를 반환하며 DB에는 쓰지 않는다. V2는
`gold.portfolio_daily_state`를 읽고 승인된
`metric.total-asset-valuation-change-contribution-krw`를 기존 `gold.metric_values`에 저장한다.

양일 완전성, 필수 계좌 coverage, holdings/cash reconciliation 중 하나라도 실패하면 신규 편입·전량 매도
판정을 억제한다. 응답에는 조사용 change와 blocker를 남길 수 있지만 V2의 공식 numeric metric은 `NULL`로
저장한다. 따라서 부분 수집이 급락이나 전량 매도로 승격되지 않는다. 해외 보유분은 가격과 환율 효과를
분리하지 않고 `KRW valuation change including FX`로 표시한다.

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
