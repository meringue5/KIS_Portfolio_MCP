# 검토 패키지 E — 데이터 플랫폼과 운영

> 상태: 사용자 승인 완료, 구현 미승인
> 기준일: 2026-08-27
> 범위: 논리·물리 경계, orchestration, 저장·보존, governance, backup·recovery 설계
> 비범위: migration 실행, bucket 생성, Flights 구독, 배포, 기존 local MCP 제거

## 1. 한눈에 보는 권고안

| ID | 승인할 권고 | 핵심 이유 |
| --- | --- | --- |
| E-1 | Remote MCP·공통 core·batch/pipeline·warehouse를 유지하고 별도 내부 REST microservice는 필요가 생길 때만 추가 | 현재 adapter가 core를 직접 공유하므로 불필요한 network tier를 만들 이유가 없음 |
| E-2 | 사용자-facing MCP는 Remote만 남기고 local stdio는 제품 설정·문서에서 퇴역 | iPhone/원격 사용자에게 local 실행 혼선을 주지 않음 |
| E-3 | Cloud Run Jobs + Scheduler를 primary orchestrator로 유지하고 MotherDuck Flights는 보류 | Flights는 Business 기능이고 현재 월 기본비용 대비 이점이 작음 |
| E-4 | Bronze/Silver/Gold/Control/Security를 versioned migration으로 물리 분리 | 현재 runtime auto-DDL과 live drift 상태에서 즉시 이동하면 동시 writer 위험이 있음 |
| E-5 | typed row는 MotherDuck, 원본 문서는 content-addressed object storage에 저장 | 분석 성능·비용과 원문 재현성을 함께 확보 |
| E-6 | source·object·metric catalog, run ledger, watermark와 quality result를 Remote MCP에 제공 | 대화형 분석이 table 의미와 freshness를 추측하지 않게 함 |
| E-7 | 3년을 초기 적재·최소 hot history로 보고 canonical 사실은 삭제 기한 없이 누적 | 3년이 지나면 오래된 투자기억을 지우는 결과를 피함 |
| E-8 | 매일 off-site Parquet backup, 월별 장기본, 분기 복원 rehearsal과 RPO 24h/RTO 4h를 사용 | Lite snapshot 1일에만 의존하지 않고 실제 복원 가능성을 검증 |
| E-9 | 월 총비용 5만원을 상한으로 scale-to-zero 서비스와 실행 후 종료하는 batch job만 기본 채택 | 상시 실행 인프라 비용을 피하고 자산관리 서비스의 지속 가능성을 보장 |

## 2. 확인된 현황

### 2.1 실제 구성요소

현재 코드는 다섯 개의 **별도 배포 서비스**가 아니라 다음 경계를 가진 하나의 코드베이스다.

```text
KIS/OpenDART/SEC/통계 API
          │
          ▼
clients → services/analytics → db repositories → MotherDuck
             ▲        ▲
             │        │
      Remote MCP     batch CLI / Cloud Run Jobs
       + OAuth
```

- KIS API backend는 우리가 별도로 운영하는 REST microservice가 아니라 `clients/`와 `services/`가 외부 KIS
  REST API를 호출하는 내부 core다.
- Remote Streamable HTTP MCP와 OAuth auth server는 Cloud Run service로 배포된다.
- batch CLI와 Cloud Run Jobs는 같은 core service를 재사용한다.
- 별도 일반 HTTP/Web API는 architecture에 미래 adapter로만 기록돼 있고 현재 일급 배포 구성요소가 아니다.
- 데이터베이스는 MotherDuck이며 local DuckDB는 개발·검증·복구 보조다.

따라서 사용자가 본 다섯 관심사는 맞지만, `공통서비스 백엔드`를 즉시 별도 network service로 분리할
필요는 없다. 코드 의존성 경계와 배포 경계는 같은 개념이 아니다.

### 2.2 warehouse와 drift

2026-08-27 live inventory는 `kis_portfolio.main`에 27 tables와 3 views가 있음을 확인했다.

- 현재 checkout의 관리 계약: 25 tables + 2 views
- live 추가 객체: `cash_flow`, `trade_journal`, `asset_return_daily`
- live 추가 컬럼: `asset_overview_snapshots.quality_status`, `quality_flags`, `is_complete`
- `asset_return_daily`는 upstream view가 quality 컬럼을 투영하지 않아 broken 상태
- `schema_migrations`는 존재하지만 runtime `init_schema()`와 분리된 실제 migration runner는 없음

이 객체들은 출처가 확인된 다른 branch의 결과지만 현 branch의 registry·repository·test에 없으므로
자동 채택하거나 삭제하지 않는다. 구현 첫 단계에서 계약 단위로 통합해야 한다.

### 2.3 용량과 MotherDuck 기능

- 현재 `kis_portfolio` database 크기: 49.0 MiB
- MotherDuck Lite: 10 GB storage와 월 10시간 Pulse compute 포함, queryable snapshot retention 최대 1일
- MotherDuck Business: 2026-08-27 기준 월 $250/organization + usage, Flights와 90일 snapshot retention 제공
- Flights: Python runner, cron, secret, version과 run history를 관리하지만 Business/Enterprise 기능이며
  runner와 load compute가 별도 사용량으로 과금됨

승인된 보유범위의 3년 price/ETF typed data는 약 1 GB 안쪽 목표다. Package C의 재무 fact, 배당, 매크로와
Package D의 signal/run row는 같은 범위에서 수십~수백 MB 수준으로 예상한다. 원본 보고서 binary를
MotherDuck BLOB으로 중복 저장하지 않으면 10 GB의 즉각적인 제약은 아니다.

### 2.4 현재 비용 구조 적합성

- 현재 배포 문서는 auth·remote Cloud Run service를 `min-instances=0`, `max-instances=1`로 두고 request가
  없을 때 scale-to-zero하도록 정의한다.
- Cloud Run Jobs는 실행 중인 instance 시간에만 과금되고, Scheduler는 job 수 기반의 소액 과금 구조다.
- Google Cloud budget은 경보이지 지출 차단장치가 아니므로 budget alert만으로 5만원 상한을 보장할 수 없다.
- MotherDuck Business의 월 $250 기본료는 환율·부가세를 고려하기 전에도 월 5만원 상한을 넘는다. 따라서
  Flights는 현 예산에서 선택할 수 없다.

현재 구성은 비용 목표와 가까우며, 검증된 KIS·OAuth·Remote MCP 경계를 버리고 다시 만들 근거는 없다.
권고는 **기존 shared-core 구조를 점진적으로 고치는 것**이다. 새 platform 또는 상시 worker를 추가하는
재작성은 비용뿐 아니라 이미 검증한 인증·토큰·계좌 API 동작의 회귀 위험을 키운다.

## 3. 권고 계약

### E-1. 런타임·코드 경계

목표 구성은 다음 다섯 책임으로 정리한다.

1. **Source clients**: KIS, OpenDART, SEC, ECOS, FRED, Cboe, KRX/issuer adapter
2. **Core services and analytics**: identity, portfolio, ledger, pipeline, metric과 signal use case
3. **Remote MCP + OAuth**: 유일한 사용자-facing 대화 인터페이스와 권한 경계
4. **Batch/pipeline runners**: Cloud Run Jobs에서 같은 core use case를 실행
5. **Data plane**: MotherDuck typed data, private object storage raw documents, Parquet backup

새 일반 REST backend는 dashboard, mobile app 또는 제3의 consumer가 MCP와 다른 안정 API 계약을 요구할
때 별도 결정으로 추가한다. 단순히 `services/`를 분리했다는 이유로 network hop을 만들지 않는다.

### E-2. Remote MCP SSOT와 local 퇴역

- 제품 설치·연결 문서, Claude Desktop 기본 설정과 `setup.sh`에서 local stdio MCP 등록을 제거한다.
- iPhone·Claude·ChatGPT 등 모든 사용자 안내는 OAuth Remote MCP URL 하나를 가리킨다.
- `kis-portfolio-mcp`, `server.py` 같은 local entrypoint는 구현·test harness로 잠시 남길 수 있지만
  지원되는 사용자 제품 표면이나 데이터 SSOT로 부르지 않는다.
- local adapter 제거 여부는 remote parity, smoke test와 운영 복구경로 확인 뒤 별도 코드 cleanup으로 한다.
- 데이터·schema·metric의 SSOT는 MCP process가 아니라 governed data contracts와 MotherDuck이다.

### E-3. Orchestration

Cloud Run Jobs + Cloud Scheduler를 primary로 유지한다.

- job은 관리된 pipeline ID와 logical date/slot을 받는다.
- 수집, 정제, 품질, signal, Telegram delivery를 독립 stage로 실행하고 run dependency를 기록한다.
- retry는 stage idempotency와 원천 rate limit을 고려한다. 같은 logical run이 canonical row나 알림을 중복
  생성하지 않는다.
- source별 backfill은 bounded date shard와 watermark를 사용한다.
- MotherDuck Flights는 Lite에서 사용할 수 없고 현재 Business base fee를 정당화하지 못하므로 보류한다.
  운영 job 수, 유지보수 시간 또는 중앙 run UI의 가치가 월 비용을 넘을 때 재평가한다.

LLM 예약 작업은 D-5에 따라 이 orchestrator의 allowlisted run을 추가로 요청할 수 있지만 cron과 run
ledger를 대체하지 않는다.

### E-4. 물리 schema migration

다음 순서를 바꾸지 않는다.

1. live drift 객체의 provenance와 계약을 검토해 현 branch로 통합 또는 명시적 폐기한다.
2. runtime auto-DDL과 분리된 versioned migration runner, 단일 writer lock과 schema version gate를 만든다.
3. `bronze`, `silver`, `gold`, `control`, `security` namespace를 만들고 copy/reconcile한다.
4. 모든 repository·analytics·backup SQL을 schema-qualified name으로 전환한다.
5. `main`에는 한시적 read-only compatibility view만 두고 사용 로그가 0인지 확인한다.
6. backup·restore rehearsal, row count·PK·합계 reconciliation과 remote/batch smoke가 통과한 뒤 `main`을
   별도 승인으로 퇴역한다.

### E-5. 저장 위치와 raw 계약

| 데이터 | 기본 저장 | 이유 |
| --- | --- | --- |
| API raw JSON·request metadata | Bronze MotherDuck, 큰 payload는 object storage + hash | 재처리와 query를 함께 지원 |
| 정규화 fact·canonical state | Silver MotherDuck | identity·dedup·reconciliation |
| 지표·signal·serving product | Gold view/table | 재현 가능한 분석 제공 |
| PDF/XLSX/XML/ZIP 원문 | private object storage, content hash key | BLOB 중복과 warehouse 용량 억제 |
| secret·token | Secret Manager 또는 Security schema의 암호화/해시 state | 분석 계층과 격리 |
| 복구본 | private off-site Parquet | warehouse vendor와 독립적인 복원 |

raw object metadata는 provider, source URL, fetched-at, effective/published-at, content hash, media type, size,
license class, parser version과 parse status를 가진다. 같은 hash의 binary는 한 번만 저장한다.

### E-6. Governance와 대화형 카탈로그

Control 영역에 최소 다음 계약이 필요하다.

- `source_dataset_registry`: provider·dataset·endpoint·coverage·license·retention·owner
- `pipeline_definition`: managed job과 input/output contract version
- `pipeline_run`: logical run, trigger, start/end, status, row counts, error class
- `pipeline_watermark`: source·partition별 완료 범위
- `data_quality_result`: completeness, freshness, uniqueness, reconciliation, referential integrity
- `metric_definition`: 공식 이름, grain, formula, unit, input, version, valid-from
- `lineage_edge`: source observation부터 Silver, Gold, MCP result와 Telegram delivery까지의 관계

Remote MCP는 raw SQL을 대신 추측하지 않고 catalog, metric, freshness, quality, known gap과 lineage를
조회하는 read tool을 제공한다. 직접 MotherDuck SQL과 MCP가 같은 metric version을 사용해야 한다.

### E-7. Retention과 capacity contract

`3년`은 삭제기한이 아니라 초기 backfill과 최소 hot history다.

| 데이터 | 권고 retention |
| --- | --- |
| 주문·체결·lot·thread·journal·cash flow·received dividend | 시스템 수명 동안 보존 |
| price·ETF 구성·actual fundamentals·forward snapshot·macro·signal | 3년 최초 적재 후 계속 누적; 자동 삭제 없음 |
| Bronze API raw | 3년 hot, 이후 Parquet/object archive 가능; canonical lineage와 hash는 계속 보존 |
| 원본 filing·ETF 문서 | content-addressed archive 계속 보존, license가 더 짧은 기간을 요구하면 예외 적용 |
| pipeline·quality·delivery ledger | 상세 1년, 집계·실패·Telegram delivery identity는 계속 보존 |
| auth/token state | security policy와 만료·revoke 계약에 따르며 analytics retention에 포함하지 않음 |

매월 다음 capacity contract를 기록한다.

- schema별 compressed storage와 월 증가량
- dataset별 row·object 수와 평균 row/object 크기
- 12개월 예상치와 Lite 10 GB 대비 headroom
- 70% 도달 시 change-only ETF canonical, raw archive와 plan 재검토
- 85% 도달 시 신규 고용량 source 적재 중지와 사용자 승인 gate

### E-8. Backup·restore와 운영 목표

1. Security schema를 제외한 governed tables를 매일 암호화된 private off-site Parquet로 full export한다.
   현재 규모에서는 incremental보다 full backup이 단순하고 검증하기 쉽다.
2. 최근 30개 daily와 12개 month-end backup을 보존하고, year-end는 삭제 승인 전까지 유지한다.
3. manifest에는 schema version, object list, row count, file hash, min/max business date와 export result를 둔다.
4. OAuth·KIS token은 백업하지 않는다. 복구 후 재인증·재발급한다.
5. 분기마다 격리된 local DuckDB 또는 새 MotherDuck database에 restore rehearsal을 수행한다.
6. 목표는 **RPO 24시간, RTO 4시간**이다. restore rehearsal이 이 목표를 못 맞추면 capacity·runbook을
   조정한다.
7. MotherDuck snapshot retention은 편의 기능이며 Parquet backup을 대체하지 않는다.

### E-9. 비용 상한과 scale-to-zero 계약

1. 운영 인프라·데이터·네트워크·저장·외부 데이터 provider를 합친 **월 실제 지출 상한은 한화
   50,000원**이다. 원화 청구액이 있으면 이를 우선하고, 외화 비용은 결제 환율·세금·수수료를 포함한다.
2. Remote MCP와 OAuth는 request-based billing, `min-instances=0`을 유지한다. 비용·DB 연결 보호를 위해
   `max-instances`도 명시하며, cold start는 허용되는 제품 특성이다.
3. 필수 수집·정제·경보는 예약 또는 on-demand Cloud Run Job으로 실행하고 완료 즉시 종료한다. 상시 worker,
   항상 켜진 ETL server, dedicated warehouse compute는 기본 아키텍처로 채택하지 않는다.
4. MotherDuck은 Lite grant와 capacity contract 안에서 사용한다. Flights·Business 또는 다른 유료 데이터
   플랫폼은 월간 총비용 추정과 대체안 비교 뒤 별도 사용자 승인이 없으면 도입하지 않는다.
5. 신규 구성요소·provider·수집주기를 제안할 때 정상월, backfill 월, 장애 재시도 월의 원화 비용 추정과
   5만원 내 잔여 예산을 함께 제시한다.
6. 비용 관측은 월 5만원의 70%(35,000원)에서 예측 주의, 85%(42,500원)에서 경고·신규 고비용 작업 gate,
   100%에서 비필수 수집·backfill 중지 후보로 둔다. 필수 보안·백업·복구를 무조건 중단하거나 데이터를
   삭제하지 않으며 사용자에게 우선순위를 요청한다.
7. Google Cloud budget alert는 비용을 자동 차단하지 않는다는 제약을 문서화한다. 실제 보호는 service별
   max instances, job timeout·retry 제한, source call budget, MotherDuck compute/storage 관측과 관리된
   kill switch를 함께 사용한다.
8. 예산을 맞추기 위해 데이터 품질 실패를 숨기거나 canonical history를 삭제하지 않는다. 품질·보존 목표를
   낮춰야 한다면 비용 추정과 영향을 제시하고 별도 승인을 받는다.

## 4. 구현 순서 권고

승인 후에도 다음 구현계획을 별도로 검토한다.

1. 현재 월 청구 baseline, service별 비용 attribution과 5만원 budget guardrail 확인
2. auth·remote의 scale-to-zero/max instance와 모든 job의 timeout·retry·동시성 상한 검증
3. drift 통합과 broken view 복구
4. migration runner·schema version gate
5. source registry·pipeline run/watermark·quality contracts
6. price/ETF 3년 backfill과 dual price basis
7. transaction/lot/cash flow/journal canonical model
8. Package C의 filing·dividend·macro adapters
9. Package D signal engine·shadow mode·Telegram
10. Remote MCP catalog와 fine-grained scope
11. physical schema 이동과 restore rehearsal

이 순서는 “분석 기능부터 빠르게 보이게 하기”보다 원천·identity·quality·복구 근거를 먼저 갖추도록 한다.

## 5. 대안과 영향

| 선택 | 장점 | 단점 | 판정 |
| --- | --- | --- | --- |
| MotherDuck Flights 즉시 전환 | cron·secret·run UI 통합 | Business 월 기본비용과 이중 migration | 현재 보류 |
| 별도 내부 REST microservice | consumer 독립 API | 배포·인증·network failure 추가 | 필요 발생 전 보류 |
| 모든 BLOB을 MotherDuck 저장 | 한곳에서 조회 | 용량·중복·backup 비용 증가 | 비권고 |
| 3년 후 자동 삭제 | 용량 예측이 쉬움 | 장기 투자기억·수정공시 비교 손실 | 비권고 |
| snapshot만 backup으로 사용 | 운영이 단순 | Lite는 1일, vendor 독립 복구 불가 | 금지 |
| 기존 구조를 버리고 플랫폼 재작성 | 구조를 처음부터 정리 가능 | 인증·KIS 회귀, migration, 개발·운영비 증가 | 비권고 |
| shared core를 비용 gate와 함께 점진 개선 | 검증 자산과 scale-to-zero 구조 재사용 | drift·migration 부채를 순서대로 해결해야 함 | **권고** |

## 6. 승인할 결정

| ID | 결정 | 승인 상태 |
| --- | --- | --- |
| E-1 | 현재 shared-core architecture와 필요 기반 HTTP adapter | 승인 (`DEC-033`) |
| E-2 | Remote MCP user-facing SSOT와 local 제품표면 퇴역 | 승인 (`DEC-034`) |
| E-3 | Cloud Run Jobs/Scheduler 유지, Flights 보류 | 승인 (`DEC-035`) |
| E-4 | drift-first versioned physical schema migration | 승인 (`DEC-036`) |
| E-5 | MotherDuck typed rows + content-addressed object storage | 승인 (`DEC-037`) |
| E-6 | catalog·run·watermark·quality·metric·lineage 계약 | 승인 (`DEC-038`) |
| E-7 | 3년 minimum hot history와 canonical indefinite accumulation | 승인 (`DEC-039`) |
| E-8 | off-site Parquet, 분기 restore, RPO 24h/RTO 4h | 승인 (`DEC-040`) |
| E-9 | 월 5만원 총비용 상한, scale-to-zero·batch-first와 비용 guardrail | 승인 (`DEC-041`) |

2026-08-27 사용자 피드백을 포함해 모두 승인했다. 코드·DB·Cloud Run·MotherDuck plan·bucket·Telegram은
아직 변경하지 않는다.

## 7. 공식 근거

- [MotherDuck pricing](https://motherduck.com/product/pricing/)
- [MotherDuck Flights](https://motherduck.com/product/flights/)
- [Cloud Run Jobs](https://cloud.google.com/run/docs/create-jobs)
- [Cloud Run pricing](https://cloud.google.com/run/pricing)
- [Cloud Scheduler pricing](https://cloud.google.com/scheduler/pricing)
- [Google Cloud budget alerts](https://cloud.google.com/billing/docs/how-to/budgets)
- [Google Cloud Storage pricing](https://cloud.google.com/storage/pricing)
