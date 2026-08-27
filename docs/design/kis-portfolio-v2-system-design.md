# KIS Portfolio V2 시스템 설계

> 상태: 차세대 설계 기준선 v0.1 — 구현 미승인
> 기준일: 2026-08-27
> 소유 문서: 목표 구조, 배포 topology, 모듈 경계, 운영·데이터·보안 architecture와 V2 ADR
> 연계 요구사항: `docs/requirements/kis-portfolio-data-platform-requirements.md`
> 구현 순서: `docs/design/kis-portfolio-v2-delivery-plan.md`

## 1. 설계 결론

KIS Portfolio V2는 기존 코드를 조금씩 옮기는 리팩터링으로 한정하지 않는다. 검증된 KIS 호출,
OAuth 호환성, REST resilience와 포트폴리오 계산은 재사용하되, 애플리케이션 내부 구조와 데이터 plane은
새 계약을 기준으로 재개발한다.

핵심 선택은 다음과 같다.

1. 제품은 **serverless modular monolith**다. 기능별 microservice를 만들지 않고 하나의 versioned core와
   여러 inbound/outbound adapter를 둔다.
2. 사용자-facing 표면은 **stateless OAuth Remote MCP** 하나다. local stdio는 개발 harness로만 남긴다.
3. OAuth authorization server와 MCP resource server는 secret·IAM 경계를 위해 두 Cloud Run service로
   유지하지만, **같은 immutable image digest**를 서로 다른 command와 service account로 실행한다.
4. 수집·정제·품질·신호·전송은 pipeline registry를 실행하는 **Cloud Run Jobs**다. Scheduler가 필수
   실행의 SSOT이며 LLM 예약 작업은 같은 관리 Job을 추가로 호출한다.
5. 분석 사실과 장기 이력은 MotherDuck, 원문과 복구본은 private GCS, 짧은 수명의 인증·lease·run request는
   Firestore에 둔다. MotherDuck을 OAuth·lease의 OLTP 저장소로 사용하지 않는다.
6. 기존 `main`은 그대로 보존한 채 새 `bronze/silver/gold/control` schema를 구축하고, dual-run 검증 뒤
   소비자를 전환한다. V2의 Security plane은 MotherDuck schema가 아니라 Firestore + Secret Manager다.
7. 일반 월 운영 목표는 현재 설정된 7,500원 예산 안쪽, 절대 상한은 50,000원이다. cold start를 허용하고
   항상 켜진 worker·warehouse·Flights·Cloud SQL을 두지 않는다.

이 설계는 현재 기능의 무조건적인 호환보다 승인된 데이터 계약, 재현성, 비용 안전성과 원격 사용성을
우선한다. 다만 사용자 데이터는 preservation-first로 전환하며, 검증 없이 기존 table이나 원천 row를
삭제하지 않는다.

## 2. 현재 상태의 근거

### 2.1 코드와 배포

2026-08-27 checkout과 운영 GCP를 읽기 전용으로 확인한 결과다.

| 영역 | 확인된 현재 상태 | V2 판단 |
| --- | --- | --- |
| Python package | 단일 `kis_portfolio`; MCP adapter 1,202행, repository 1,442행, KIS service 약 1,560행 | 기능은 있으나 adapter·application·persistence 경계가 너무 굵다 |
| DB startup | `get_connection()` 최초 호출마다 `init_schema()` 실행, 충돌 시 process-local retry | runtime DDL을 금지하고 migration command로 분리해야 함 |
| MCP | adapter에서 직접 DB connection을 얻는 경로가 있고 tool별 orchestration이 큼 | tool은 DTO 변환과 application command/query 호출만 담당해야 함 |
| Auth | OAuth code/token/client와 KIS token cache가 MotherDuck table 사용 | 짧은 수명·transactional state를 analytics warehouse에서 분리 |
| Batch | 국내 주문, 해외 거래, token warm-up, calendar의 개별 CLI command | 관리 pipeline registry와 공통 run/stage/quality 계약 필요 |
| Cloud Run service | `auth` 512 MiB/1 CPU, `remote` 1 GiB/1 CPU; 둘 다 max 1, min 미지정=0 | scale-to-zero는 재사용; remote는 stateless 전환 뒤 timeout 축소 |
| Cloud Run Job | 3개, 512 MiB/1 CPU, timeout 1,800초, retry 0 | 동일 image의 fixed-argument managed jobs로 확장 |
| Scheduler | 07:35 해외, 08:30 warm-up, 15:35 국내; 모두 enabled | monitoring slot과 source schedule을 versioned manifest로 확대 |
| 최근 실행 | 세 Job 모두 성공, 대략 30~50초 | 작은 batch-first topology가 적합함 |

현재 remote MCP는 process memory의 session manager를 사용해 max instance 1과 3,600초 timeout에 의존한다.
V2 tool은 server-to-client sampling·elicitation·push notification을 사용하지 않으므로 stateless
Streamable HTTP와 JSON response로 전환할 수 있다. 이 전환은 Claude·ChatGPT connector compatibility test를
통과해야 한다.

### 2.2 데이터 plane

| 항목 | 확인 결과 | 판단 |
| --- | --- | --- |
| MotherDuck 크기 | 약 49 MiB | 현재 용량은 Lite 10 GB의 병목이 아님 |
| 현재 계약 | 25 tables + 2 views | V2 논리 모델에 필요한 객체가 대부분 없음 |
| live 상태 | 27 tables + 3 views | branch/live drift가 존재함 |
| unmanaged | `cash_flow`, `trade_journal`, `asset_return_daily` | 자동 채택·삭제 금지; V2 계약으로 재설계 |
| column drift | `asset_overview_snapshots` quality 3컬럼 | migration 전에 소유권과 의미를 확정 |
| broken view | `asset_return_daily` | 현재 view를 V2 기준으로 승격하지 않음 |
| 물리 schema | 모든 객체가 `main` | parallel schema 구축과 검증이 필요함 |
| migration | ledger table만 있고 runner 없음 | V2 첫 기반 기능으로 구현해야 함 |

### 2.3 비용 control

| 항목 | 확인 결과 | V2 조치 |
| --- | --- | --- |
| GCP budget | 월 7,500원, actual 50%·90%·100%, forecast 100% | 일반월 early-warning budget으로 유지 |
| 요구 hard ceiling | 월 50,000원 | 35,000·42,500·50,000원 단계의 비필수 작업 gate 추가 |
| Artifact Registry | 약 2.53 GB, 과거 image 다수 | build-once와 cleanup policy 도입 |
| cleanup policy | 없음 | 최근 release·rollback digest 보존 규칙 필요 |
| Scheduler | 현재 3개 | billing account free quota와 별개로 추가 job 비용은 작지만 월 비용표에 포함 |
| 실제 월 비용 export | repository나 CLI에서 확인 가능한 billing export 없음 | 구현 Wave 0에서 billing baseline과 표준 export 결정 |

현재 7,500원 budget은 **실제 비용이 7,500원이라는 증거가 아니다**. alert도 지출을 차단하지 않는다.
V2는 실제 청구자료와 resource label을 연결해 정상월·backfill월·장애월을 따로 추정한다.

## 3. 설계 목표와 비목표

### 3.1 목표

- 사용자가 대화하지 않아도 국내·미국 보유자산 데이터가 정기적으로 쌓인다.
- Remote MCP와 직접 SQL이 같은 canonical fact와 metric version을 사용한다.
- 모든 결과가 source observation, pipeline run, quality result와 계산 version까지 추적된다.
- 평단가 포지션과 purchase lot·trade thread 분석을 동시에 제공한다.
- 가격·ETF·실적·consensus·배당·매크로·신호를 point-in-time으로 재생할 수 있다.
- 필수 schedule과 LLM trigger가 같은 idempotent application use case를 실행한다.
- cold start와 부분 장애를 감수하되 월 50,000원 상한 안에서 운영된다.
- V1 데이터를 잃지 않고 dual-run, reconciliation, cutover, rollback이 가능하다.

### 3.2 비목표

- 자동 주문 또는 주문 권한
- 전 종목·tick 실시간 market data warehouse
- Kafka, Airflow, dbt Cloud, MotherDuck Flights 같은 상시·유료 orchestration
- 여러 사용자를 위한 SaaS multi-tenancy
- 대화 요청마다 자유 SQL이나 임의 shell command 실행
- 리서치 저작물의 무제한 원문 수집
- V2 초기 릴리스의 WebSocket 실시간 시세

## 4. 목표 시스템 topology

```text
Claude / ChatGPT / iPhone
            │ OAuth + stateless Streamable HTTP
            ▼
  ┌───────────────────────┐       ┌────────────────────────┐
  │ Remote MCP resource   │──────▶│ Application core       │
  │ Cloud Run, min=0      │       │ commands / queries     │
  └──────────┬────────────┘       └──────────┬─────────────┘
             │ token verify                   │ ports
             ▼                                ▼
  ┌───────────────────────┐       ┌────────────────────────┐
  │ Firestore state plane │       │ Source adapters        │
  │ OAuth/token/lease/run │       │ KIS/DART/SEC/ECOS/...  │
  └──────────▲────────────┘       └──────────┬─────────────┘
             │                               │
  ┌──────────┴────────────┐                  │
  │ OAuth auth service    │                  │
  │ Cloud Run, min=0      │                  │
  └───────────────────────┘                  │
                                             ▼
Cloud Scheduler ──▶ Cloud Run managed Jobs ───────────────┐
                         │ collect/normalize/quality       │
                         │ reconcile/publish/evaluate      │
                         ▼                                ▼
                ┌─────────────────┐             ┌──────────────────┐
                │ Private GCS     │             │ MotherDuck       │
                │ raw + backup    │             │ bronze/silver/   │
                │ content hash    │             │ gold/control     │
                └─────────────────┘             └────────┬─────────┘
                                                        │
                                                        ▼
                                                   Telegram
```

별도 `common service backend`를 network service로 만들지 않는다. application core는 Python package 경계다.
향후 dashboard가 필요하면 동일 query handler를 사용하는 REST/GraphQL inbound adapter를 추가한다.

## 5. 코드 architecture

### 5.1 목표 package

```text
src/kis_portfolio/
├── bootstrap/                  # entrypoint별 dependency wiring
├── modules/
│   ├── portfolio/              # account, holding, total asset
│   ├── ledger/                 # execution, transaction, cash flow, lot
│   ├── journal/                # trade thread, journal revision, review queue
│   ├── market/                 # price, FX, corporate action
│   ├── exposure/               # instrument, ETF constituent, look-through
│   ├── fundamentals/           # filing, fact, consensus, dividend, macro event
│   ├── monitoring/             # metric, risk, signal, alert state
│   └── catalog/                # dataset, metric, quality, lineage query
├── application/
│   ├── commands/               # side-effecting use cases
│   ├── queries/                # read models and analysis queries
│   ├── pipeline/               # registry, runner, stage protocol
│   └── dto/                    # versioned input/output contracts
├── ports/
│   ├── sources.py              # KIS/DART/SEC/... interfaces
│   ├── warehouse.py
│   ├── state_store.py
│   ├── object_store.py
│   ├── notifier.py
│   └── clock.py
├── adapters/
│   ├── inbound/
│   │   ├── mcp/
│   │   ├── oauth/
│   │   └── pipeline_cli/
│   └── outbound/
│       ├── kis/
│       ├── dart/
│       ├── sec/
│       ├── macro/
│       ├── motherduck/
│       ├── firestore/
│       ├── gcs/
│       └── telegram/
└── platform/
    ├── migrations/
    ├── observability/
    ├── resilience/
    └── security/
```

### 5.2 의존성 규칙

- `modules`는 MCP, HTTP, DuckDB, Firestore, GCS SDK를 import하지 않는다.
- `application`은 domain object와 port만 사용한다.
- inbound adapter는 command/query DTO만 호출하고 DB connection을 얻지 않는다.
- outbound adapter끼리 직접 호출하지 않는다.
- cross-module 변경은 application use case 또는 명시적 domain event로만 연결한다.
- JSON-safe 변환, timezone, money 같은 shared kernel은 작고 순수하게 유지한다.
- provider raw field name은 outbound adapter와 Bronze mapping 밖으로 새지 않는다.

### 5.3 재사용과 재개발 판정

| 현재 자산 | 판정 | 처리 |
| --- | --- | --- |
| KIS endpoint/TR_ID와 pagination | 재사용 | source adapter contract test로 감쌈 |
| REST resilience | 재사용·보강 | port 밖 platform policy로 이동, distributed quota는 관측 후 |
| 계좌 registry와 IRP 분기 | 재사용 | domain config로 이전 |
| OAuth protocol·client compatibility | 재사용 | repository port를 Firestore adapter로 교체 |
| 토큰 암호화와 redaction | 재사용 | Security plane에 유지 |
| 포트폴리오 overview 계산 | 부분 재사용 | pure domain calculation과 source orchestration 분리 |
| monolithic MCP adapter | 재개발 | thin tool catalog로 교체 |
| `services/kis_api.py` | 해체 | source별 adapter와 use case로 이동 |
| `db/repository.py` | 해체 | module별 repository와 schema-qualified SQL로 이동 |
| runtime `init_schema()` | 폐기 | explicit migration + startup version gate |
| 기존 analytics SQL | 검증 후 재작성 | dual price, cash-flow adjustment, quality-aware input 적용 |
| unmanaged live objects | 직접 재사용 금지 | export·provenance 확인 후 V2 contract로 재생성 |

## 6. 데이터 architecture

### 6.1 저장소 역할

| 저장소 | SSOT 책임 | 넣지 않는 것 |
| --- | --- | --- |
| Firestore | OAuth current state, encrypted KIS token cache, refresh lease, run request, idempotency claim | 장기 분석 fact, 대량 raw payload |
| GCS raw | immutable source bundle, filing/PDF/XLSX/ZIP, content hash object | credential, 평문 token |
| MotherDuck Bronze | observation envelope, raw object reference, 작은 replay metadata | OAuth·KIS token |
| MotherDuck Silver | normalized canonical facts, identity, reconciliation | LLM이 추측한 사실 |
| MotherDuck Gold | 재생성 가능한 metric·signal·serving table/view | source가 불명확한 수동 계산 |
| MotherDuck Control | dataset/metric/pipeline version, immutable run summary, watermark mirror, quality, lineage | active lease와 bearer token |
| Secret Manager | long-lived provider credentials와 encryption key | 분석 데이터와 runtime event |

Firestore 도입은 기존 DEC-036의 `security` MotherDuck physical schema 부분을 V2에서 대체한다. 이 변경은
OAuth/KIS operational state의 atomic update와 expiry 처리, least-privilege IAM을 얻기 위한 것이다.
Firestore API는 현재 프로젝트에서 활성화돼 있지 않으므로 설계 승인 뒤 별도 provisioning으로 다룬다.

### 6.2 Raw landing

- 외부 호출 한 번의 응답 묶음은 `dataset/partition/run_id` 단위 압축 object로 저장한다.
- object는 `sha256`, byte size, media type, source URL, request fingerprint, fetched-at, effective-at,
  license class와 parser version을 가진다.
- credential, Authorization header, raw token은 landing 전 redaction한다.
- 동일 content hash는 중복 저장하지 않는다.
- API가 반환한 빈 결과도 `empty_success`, `not_available`, `source_error`를 구분한 observation으로 남긴다.
- small payload를 Bronze JSON에 중복 보존할지는 dataset contract가 결정하며 원본의 canonical 위치는 하나다.

### 6.3 목표 logical objects

아래는 물리 DDL 전에 `docs/data-catalog.md`와 machine registry에 등록할 최소 객체군이다.

| Layer | 객체군 | 핵심 grain |
| --- | --- | --- |
| Bronze | `source_observation`, `raw_object_manifest` | dataset·request·fetch 또는 content hash |
| Silver | `account`, `instrument`, `position_snapshot`, `cash_snapshot` | account/instrument/as-of |
| Silver | `order`, `execution`, `transaction`, `cash_flow` | 원천 identity event |
| Silver | `purchase_lot`, `trade_thread`, `lot_thread_link`, `sell_allocation_revision` | lot/thread/revision |
| Silver | `journal_revision`, `journal_review_item` | trade/thread revision·queue item |
| Silver | `price_bar`, `fx_rate`, `corporate_action` | basis·instrument·date |
| Silver | `etf_constituent_snapshot`, `etf_constituent` | ETF·effective date·component |
| Silver | `filing`, `financial_fact`, `consensus_snapshot`, `guidance_event` | issuer·period·as-of·metric |
| Silver | `dividend_event`, `dividend_entitlement`, `dividend_receipt` | event/account/payment state |
| Silver | `macro_observation`, `market_event`, `event_exposure_link` | series/event/effective time |
| Gold | `portfolio_daily`, `position_performance_daily`, `lot_performance_daily` | day·portfolio/position/lot |
| Gold | `thread_performance_daily`, `exposure_snapshot`, `dividend_monthly` | day/month·thread/exposure |
| Gold | `metric_value`, `signal_evaluation`, `alert_state`, `delivery_ledger` | subject·metric/rule·as-of |
| Control | `schema_migration`, `dataset_definition`, `pipeline_definition` | versioned definition |
| Control | `pipeline_run`, `pipeline_stage_run`, `watermark`, `quality_result`, `lineage_edge` | run/stage/source·partition |

`price_bar` natural key에는 `price_basis`를 포함해 adjusted/raw를 병렬 보존한다. consensus와 signal은
계산 당시 보였던 snapshot을 사용하며 최신 값으로 과거를 덮어쓰지 않는다.

### 6.4 Migration contract

1. migration 파일은 immutable version, checksum, apply/verify/rollback metadata를 가진다.
2. application runtime은 DDL을 실행하지 않고 required schema version을 검사한다.
3. migration Job 하나만 schema write 권한을 가진다.
4. 각 migration은 row count, PK uniqueness, null, sum, foreign key equivalent와 view compile을 검증한다.
5. `main`은 V2 구축 중 write/read를 유지한다. V2 writer는 새 schema에만 쓴다.
6. dual-write가 필요하면 application command에서 명시적으로 실행하고 각 결과를 비교한다. DB trigger는
   사용하지 않는다.
7. cutover 뒤 `main`은 compatibility view 또는 archive로 남기고 별도 삭제 승인 전에는 제거하지 않는다.

## 7. Pipeline architecture

### 7.1 Pipeline specification

각 pipeline은 code-reviewed manifest와 application registry를 함께 가진다.

```text
pipeline_id
version
schedule / market calendar gate
source datasets
ordered stages
input/output contract versions
logical date/slot key
idempotency key template
timeout / retry / source call budget
freshness and quality gates
required secret and IAM profile
cost class: routine | backfill | exceptional
```

stage protocol은 `collect → land → normalize → reconcile → quality → publish → evaluate → deliver`다. 모든
pipeline이 모든 stage를 가질 필요는 없지만 생략 이유를 manifest에 기록한다.

### 7.2 실행 의미

- exactly-once 실행을 약속하지 않는다. **at-least-once execution + idempotent effect**를 계약으로 한다.
- idempotency key는 `(pipeline_id, version, logical_date, slot, partition)`이다.
- Firestore transaction으로 active lease와 duplicate claim을 확인한다.
- 각 stage는 입력 watermark와 output row/object count를 남긴다.
- 실패한 stage부터 재실행할 수 있지만 이전 성공 output의 hash가 달라지면 새 revision으로 기록한다.
- partial source는 성공으로 숨기지 않는다. downstream publish/signal gate가 quality status를 본다.
- backfill은 bounded shard, checkpoint, rate budget와 일일 비용 한도를 가진다.

### 7.3 Cloud Run Job topology

- release마다 image를 한 번 build하고 digest를 모든 service/job에 배포한다.
- pipeline별 Job definition은 fixed `pipeline_id`와 resource profile을 가진다.
- Scheduler와 Remote MCP는 allowlist의 Job을 `roles/run.invoker`로 실행한다.
- LLM이 container args, env, task count 또는 timeout을 임의 override하지 못하게 한다.
- parameter가 필요한 backfill은 Firestore `run_request`에 검증된 범위를 쓰고 전용 queue-consuming Job이
  claim한다.
- retry 0을 기본으로 유지하되 application stage가 안전한 retry만 bounded하게 수행한다.

### 7.4 초기 managed pipeline catalog

| Pipeline | 기본 trigger | 핵심 결과 |
| --- | --- | --- |
| `token-readiness` | 평일 08:30 KST | KIS token validity·refresh audit |
| `ledger-overseas-close` | 평일 07:35 | 해외 주문·거래·cash-flow 후보 |
| `ledger-domestic-close` | KRX 거래일 15:35 | 국내 주문·execution·lot 후보 |
| `monitor-morning` | 거래일 10:00 | 미국 마감 + 국내 오전 snapshot·signal·Telegram |
| `monitor-preclose` | KRX 거래일 14:30 | 국내 마감 전 risk·signal |
| `monitor-close` | KRX 거래일 16:00 | 국내 종가·총자산·일일 signal |
| `reference-daily` | 일 1회 | calendar, instrument, ETF constituent, FX |
| `fundamental-daily` | 일 1회 | new filing, dividend, guidance, macro release |
| `quality-daily` | monitor-close 후 | freshness·reconciliation·gap report |
| `backup-daily` | 일 1회 | governed Parquet + manifest |
| `backfill-managed` | 승인된 on-demand request | 3년 shard, checkpoint, cost budget |

실제 시각은 source availability와 replay 결과로 조정할 수 있다. Telegram 평가 시각 10:00·14:30·16:00은
제품 계약으로 유지한다.

## 8. Remote MCP V2

### 8.1 Transport와 권한

- Streamable HTTP는 `stateless_http=true`, `json_response=true`를 목표로 한다.
- V2는 server-to-client sampling, elicitation, resource subscription을 사용하지 않는다.
- warm request timeout은 300초 이하, 장기 수집은 async managed Job으로 전환한다.
- 초기 `max-instances=1`; compatibility와 Firestore lease 검증 뒤 필요하면 2까지 허용한다.
- scope는 `mcp:read`, `mcp:collect`, `mcp:journal.write`로 분리한다.
- tool handler는 scope, input schema, idempotency, audit actor를 application layer에 전달한다.

### 8.2 V2 public tool budget

V2는 raw KIS endpoint마다 tool을 만들지 않고 질문의 결과 단위로 18개 이내를 목표로 한다.

| Scope | Tool candidate | 책임 |
| --- | --- | --- |
| read | `get-portfolio-overview` | canonical total asset·allocation·quality |
| read | `get-position-analysis` | position/lot/thread 손익·drawdown·risk |
| read | `get-performance-history` | cash-flow-adjusted portfolio history |
| read | `get-market-snapshot` | current/cached price·FX·freshness |
| read | `get-market-history` | governed bars·trend·volume·RSI·Bollinger context |
| read | `get-trade-ledger` | order/execution/transaction/cash flow |
| read | `get-trade-thread` | thread·lot·journal revisions |
| read | `get-dividend-summary` | declared/entitled/received reconciliation |
| read | `get-fundamental-outlook` | actual·consensus·scenario·valuation |
| read | `get-exposure-analysis` | direct·ETF look-through·macro exposure |
| read | `get-signal-status` | signal state·rule·inputs·quality |
| read | `get-data-catalog` | dataset/object/metric/lineage 설명 |
| read | `get-data-quality` | freshness·completeness·known gap |
| read | `get-pipeline-run` | run/stage 결과와 실패 원인 |
| read | `get-journal-review-queue` | 다음 사용자 질문 후보 |
| collect | `run-managed-pipeline` | allowlisted Job trigger |
| journal.write | `upsert-trade-journal` | expected revision 기반 작성·수정 |
| journal.write | `revise-trade-thread` | lot/thread/sell allocation revision |

주문 tool은 V2 public catalog에서 제거한다. V1 disabled stub은 connector cutover 동안에만 호환 표면에 남긴다.

## 9. 분석과 신호

### 9.1 계산 원칙

- 모든 metric은 name, version, grain, unit, input dataset/version, price basis, valid-from을 가진다.
- Gold는 승인된 Silver + Control만 읽는다.
- quality가 `partial`, `stale`, `reconstructed`, `insufficient_history`이면 결과와 Telegram에 노출한다.
- 평단가 포지션과 lot/thread 손익은 서로 대체하지 않는다.
- consensus surprise는 발표 직전 snapshot, revision은 발표 뒤 point-in-time snapshot을 사용한다.
- Bollinger는 adjusted close의 SMA20 ± 2σ, `%B`, bandwidth이고 단독 매매 신호가 아니다.

### 9.2 신호 평가

1. 3년 replay 결과와 bootstrap rule을 비교한다.
2. asset class별 발생 빈도, precision proxy, 최대 누락 사례를 검토한다.
3. 2주 shadow mode에서 Telegram payload를 DB에만 만든다.
4. 사용자가 rule version을 승인하면 delivery를 활성화한다.
5. 활성화 뒤에도 threshold revision은 새 version으로만 반영한다.

alert state와 delivery idempotency는 signal evaluation과 분리한다. Telegram 실패는 signal을 무효화하지
않으며 별도 retry와 delivery ledger를 가진다.

## 10. 보안 architecture

### 10.1 Runtime identity

| Identity | 허용 권한 | 금지 권한 |
| --- | --- | --- |
| auth service account | OAuth provider secret, Firestore auth collections | KIS account secret, MotherDuck analytics write |
| MCP service account | OAuth token verify, MotherDuck governed query/write, allowlisted Job invoke, 필요한 KIS secret | OAuth provider client secret, migration DDL |
| pipeline service account | source secrets, Firestore lease/run request, MotherDuck data write, raw/backup bucket | OAuth provider secret, auth user mutation |
| migration service account | MotherDuck schema DDL, migration ledger | KIS source secret, Telegram secret |
| deploy service account | image deploy, service account impersonation, manifest apply | runtime 데이터 read |

실제 GCP role은 필요한 API method 목록에서 custom role 또는 최소 predefined role로 확정한다.

### 10.2 Token과 state migration

- 기존 OAuth access/refresh token은 Firestore로 복사하지 않고 V2 cutover 시 revoke/reconnect한다.
- static client는 Secret Manager/config에서 bootstrap하고 dynamic client는 재등록을 허용한다.
- KIS access token은 cutover 시 새로 발급하는 것을 기본으로 한다. 꼭 필요할 때만 encrypted ciphertext를
  일회성 migration한다.
- Firestore에는 raw OAuth bearer를 저장하지 않고 digest만 저장한다.
- KIS token ciphertext는 application-level encryption을 유지하며 key는 Secret Manager에 둔다.
- authorization code, access token, lease, run request는 expiry field를 가진다. TTL 삭제 지연을 인증
  유효성으로 신뢰하지 않고 application이 `expires_at`을 먼저 검사한다.

### 10.3 개인정보와 audit

- account 원문 ID는 confidential key로 저장하되 MCP·Telegram·로그에서는 alias만 노출한다.
- source raw landing 전 header와 secret field를 redaction한다.
- journal write, thread revision, pipeline trigger는 actor, client, scope, request id와 prior revision을 남긴다.
- Cloud Audit Logs와 application audit event를 구분한다.

## 11. Reliability와 운영 SLO

| 항목 | 목표 | 실패 시 동작 |
| --- | --- | --- |
| schedule delivery | due run의 99%가 slot + 10분 내 terminal state | 지연·실패 Telegram/운영 event, 다음 run에서 gap repair |
| data freshness | monitoring input은 slot별 contract 이내 | stale 표시, 위험 신호 억제 또는 제한 평가 |
| MCP governed read | warm P95 3초 이내, cold P95 15초 목표 | source 호출 없이 cached read 우선 |
| on-demand external read | 60초를 넘는 작업은 async Job | run id 반환 후 polling |
| canonical completeness | 계좌·source partial을 완전으로 표시하지 않음 | `partial/unknown`과 missing coverage 반환 |
| backup | RPO 24시간 | 마지막 verified manifest로 restore |
| restore | RTO 4시간 | local/new database rehearsal 분기 1회 |
| 비용 | 일반월 7,500원 목표, 50,000원 hard ceiling | optional/backfill gate와 사용자 승인 |

SLO는 고가의 always-on HA를 뜻하지 않는다. cold start와 일시적 지연은 비용 계약 안에서 허용하고,
데이터 유실·거짓 완전성·중복 경보를 더 심각한 실패로 본다.

## 12. 비용 architecture

### 12.1 비용 단계

| 단계 | 조건 | 기본 동작 |
| --- | --- | --- |
| Early | 기존 7,500원 budget의 50/90/100% | 원인 확인, image/storage 증가와 retry 점검 |
| Guard | hard ceiling의 70% = 35,000원 forecast/actual | 신규 backfill·고빈도 source 중지 |
| Approval | 42,500원 | 비필수 pipeline 실행에 owner 승인 필요 |
| Ceiling | 50,000원 | 필수 auth/backup 외 선택 pipeline circuit open 후보 |

Cloud Billing budget은 차단장치가 아니다. 실제 보호는 아래를 함께 사용한다.

- Cloud Run min 0, max instance와 request/job timeout
- Job application retry·source call·row/object byte budget
- pipeline cost class와 backfill 일일 shard limit
- MotherDuck storage/compute 월 usage 관측
- Artifact Registry build-once, 최근 production/rollback digest keep, untagged age cleanup
- GCS lifecycle와 content deduplication
- billing export 또는 월별 수동 report를 통한 서비스·SKU별 actual baseline

Firestore는 현재 예상 규모에서 free quota보다 훨씬 작은 auth·lease 문서만 사용한다. TTL delete와
BigQuery billing export에는 free quota 밖 비용 가능성이 있으므로 정상월 비용표에 포함한다.

### 12.2 기본적으로 도입하지 않는 구성

- MotherDuck Business/Flights
- Cloud SQL 또는 always-on VM
- GKE, Kafka, Airflow
- 상시 WebSocket collector
- 무제한 원문 BLOB의 MotherDuck 저장
- deploy target마다 별도 image build

## 13. V2 Architecture Decision Records

| ID | 결정 | 상태 | 주요 결과 |
| --- | --- | --- | --- |
| V2-ADR-001 | serverless modular monolith | 설계 채택 | microservice network tier 없이 내부를 재개발 |
| V2-ADR-002 | Remote MCP만 제품표면 | 기존 승인 재확인 | local stdio는 harness로만 유지 |
| V2-ADR-003 | auth/resource 두 service + 한 image digest | 설계 채택 | secret 격리와 release 일관성 동시 확보 |
| V2-ADR-004 | stateless Streamable HTTP | 설계 채택, compatibility gate | session affinity와 3,600초 timeout 제거 가능 |
| V2-ADR-005 | Firestore operational state plane | 설계 채택, 신규 승인 필요 | OAuth/token/lease를 MotherDuck에서 분리 |
| V2-ADR-006 | MotherDuck은 bronze/silver/gold/control | 설계 채택 | V2 Security는 warehouse 밖으로 이동 |
| V2-ADR-007 | GCS immutable raw + off-vendor Parquet | 기존 승인 구체화 | replay·restore와 warehouse 용량 분리 |
| V2-ADR-008 | explicit migration, runtime DDL 금지 | 설계 채택 | startup conflict와 silent drift 방지 |
| V2-ADR-009 | managed pipeline registry + fixed Job args | 설계 채택 | Scheduler/LLM 동일 경로, 임의 실행 차단 |
| V2-ADR-010 | at-least-once + idempotent effect | 설계 채택 | 중복 trigger를 현실적으로 처리 |
| V2-ADR-011 | build once, deploy by digest | 설계 채택 | target drift와 image storage 감소 |
| V2-ADR-012 | point-in-time metric/signal | 기존 승인 구체화 | look-ahead bias와 과거 재작성 방지 |
| V2-ADR-013 | 7,500원 target / 50,000원 ceiling | 설계 채택 | 일반월 절약과 hard limit 동시 관리 |
| V2-ADR-014 | V2 초기 REST snapshot, WebSocket 보류 | 설계 채택 | KIS rate/resilience 자산 재사용 |
| V2-ADR-015 | 주문 기능은 V2 public surface에서 제거 | 설계 채택 | disabled stub보다 명확한 권한 경계 |
| V2-ADR-016 | parallel schema + dual-run cutover | 설계 채택 | 재개발 중에도 V1 데이터 보존과 rollback 가능 |

## 14. 선택한 대안의 비교

| 쟁점 | 선택 | 기각/보류 대안 | 이유 |
| --- | --- | --- | --- |
| 서비스 분리 | modular monolith | 기능별 microservice | 단일 사용자·저빈도에서 network/운영비가 더 큼 |
| auth 배포 | 별도 auth/resource | 완전 합체 | secret·IAM blast radius가 커짐 |
| 운영 state | Firestore | MotherDuck Security, Cloud SQL | transaction/TTL/scale-to-zero와 비용 균형 |
| orchestration | Cloud Run Jobs/Scheduler | Flights, Workflows, Airflow | 현재 stage 수와 비용에서 자체 runner가 충분 |
| job parameter | fixed args + validated queue | LLM execution override | `run.developer`와 임의 env/arg 위험 회피 |
| remote transport | stateless HTTP | stateful session | push 기능이 필요 없고 horizontal safety가 중요 |
| migration | parallel schema | in-place big bang | rollback과 reconciliation 근거가 약함 |
| raw storage | GCS bundle + Bronze manifest | 모든 JSON/BLOB MotherDuck | 비용, 재처리, large document 처리 |
| release image | one digest | target별 source build | image drift와 2.53 GB 누적 억제 |

## 15. 설계 변경이 필요한 기존 문서

이 문서가 승인되면 다음 계약을 한 변경 묶음으로 갱신한다.

- `SPEC.md`: V2 ADR 승격과 이전 ADR 상태 표시
- `ARCHITECTURE.md`: V1 현재 상태와 V2 목표 상태 분리
- `docs/data-catalog.md`: V2 object grain과 Firestore Security plane
- `docs/data-pipeline.md`: managed pipeline registry와 run/stage semantics
- `docs/security-and-secrets.md`: Firestore collections, IAM과 token cutover
- `docs/deployment.md`: stateless MCP, build-once digest, job manifest와 cleanup policy
- `docs/backup.md`: GCS raw/Parquet, restore rehearsal와 Firestore 재bootstrap
- `docs/api-capability-map.md`: V2 source adapter와 public tool boundary

이 설계 문서 자체는 Firestore API 활성화, bucket 생성, schema migration, connector 변경 또는 Cloud Run
배포를 승인하지 않는다.

## 16. 외부 플랫폼 가정과 확인 출처

아래 가정은 기준일에 공식 문서로 재확인했다. 가격과 quota는 구현 Wave 0에서 운영 region과 원화 SKU로
다시 계산한다.

- Cloud Billing의 alerts-only budget은 사용량이나 지출을 자동으로 막지 않는다. 따라서 budget alert와
  별도로 instance, timeout, retry, source-call과 backfill gate가 필요하다.
  <https://docs.cloud.google.com/billing/docs/how-to/budgets>
- Firestore 무료구간은 프로젝트당 한 database에 적용되며 storage 1 GiB, 일 50,000 reads, 20,000 writes,
  20,000 deletes와 월 10 GiB outbound를 제공한다. TTL deletes, backup, restore와 PITR은 무료구간에
  포함되지 않는다. <https://firebase.google.com/docs/firestore/pricing>
- Cloud Run Job의 고정 definition 실행에는 `roles/run.invoker`가 가능하지만 console 실행, override와
  cancel에는 `roles/run.developer`가 필요하다. 따라서 MCP에는 override 권한을 주지 않는다.
  <https://docs.cloud.google.com/run/docs/execute-jobs>
- 공식 Python MCP SDK는 `stateless_http=True`와 `json_response=True`를 지원하지만 JSON 응답은
  server-to-client sampling·elicitation과 request-scoped progress channel을 제공하지 않는다. V2가 이 기능을
  쓰지 않는 이유와 실제 Claude/ChatGPT compatibility gate를 함께 둔다.
  <https://github.com/modelcontextprotocol/python-sdk/blob/main/docs/run/index.md>
