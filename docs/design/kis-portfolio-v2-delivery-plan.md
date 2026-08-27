# KIS Portfolio V2 구현 설계와 전환 계획

> 상태: 승인 architecture 구현 계획 v0.3 — 승인 범위 내 Work Item은 턴키 실행, 외부·운영 gate는 별도 승인
> 기준일: 2026-08-28
> 상위 설계: `docs/design/kis-portfolio-v2-system-design.md`
> 원칙: 각 Wave는 산출물·자동검증·운영증거·rollback gate가 모두 충족돼야 완료된다.

## 0. 선행 조건 — Package F Project Operating System

V2 제품 구현에 앞서 `docs/governance/project-operating-system.md`의 변경 분류, Work Item, traceability,
공통 check harness와 CI gate를 활성화한다. 각 V2 Work Item은 이 운영체계를 사용하며, 제품 구현을 위해
Project OS gate를 임시 우회하지 않는다. Package F의 bootstrap 작업은 `WI-000`이 소유한다.
source catalog, collection basket, dataset, metric과 pipeline 작업은
`docs/governance/data-governance-harness.md`의 contract-first gate를 선행한다. `WI-003`은 하네스 정의만
소유하며 실제 source 선정·수집·migration은 각 Wave Work Item이 소유한다.

2026-08-28 DEC-044에 따라 승인된 requirements·ADR·DGH contract 안의 repository-local 구현, fixture,
test와 migration dry-run은 Work Item별 사용자 재승인 없이 진행한다. 유료 provider, credential·계정 발급,
infrastructure provisioning, production 배포·cutover, live migration, 대량 backfill, 삭제와 외부 알림은
각 절의 release/operation gate와 별도 사용자 권한을 계속 요구한다.

## 1. 계획 운영 방식

V2는 장기 branch에서 한 번에 교체하지 않는다. 작은 vertical release를 mainline에 통합하되 V1 제품표면과
운영 데이터를 보존한다. 각 작업은 다음 trace를 가져야 한다.

```text
requirement / ADR
    → work item
    → code + migration + catalog
    → automated evidence
    → shadow/live evidence
    → acceptance record
```

코드가 완성돼도 migration·restore·remote smoke·비용 근거가 없으면 해당 Wave는 완료가 아니다.

## 2. 전체 Wave

| Wave | 목적 | 사용자-visible 변화 | 필수 선행 |
| --- | --- | --- | --- |
| 0 | 비용·운영·설계 기준선 고정 | 없음 | Package F + 이 설계 승인 |
| 1 | V2 코드 골격과 release foundation | 없음 | Wave 0 |
| 2 | Firestore state plane과 explicit migration | OAuth 재연결 준비 | Wave 1 |
| 3 | V2 warehouse와 canonical ledger | DB-only 비교 결과 | Wave 2 |
| 4 | source pipeline과 3년 backfill | catalog·quality 조회 | Wave 3 |
| 5 | metric·signal·Telegram shadow | 전송 전 shadow report | Wave 4 |
| 6 | stateless Remote MCP V2 | 새 tool catalog와 write scope | Wave 3~5 |
| 7 | dual-run cutover | Remote MCP V2가 SSOT | Wave 6 |
| 8 | V1 retirement와 운영 안정화 | local 제품표면 제거 | Wave 7 관찰기간 |

## 3. Wave 0 — 비용·현황·계약 기준선

### Work items

- `V2-W0001` **완료 (`WI-002`, 2026-08-28)** — GCP SKU별 최근 3개월 actual/credit/forecast와
  scale-to-zero 이후 정상월 baseline을 `docs/operations/cost-baseline-2026-08.md`에 기록했다. 현재는 월간
  Console snapshot을 사용하고 project/복잡도 증가 시 detailed billing export를 재검토한다.
- `V2-W0002` Cloud Run service/Job/Scheduler, service account, Secret Manager, GCS, Artifact Registry와
  MotherDuck usage inventory를 machine-readable snapshot으로 만든다.
- `V2-W0003` 현재 7,500원 budget을 일반월 early warning으로 유지하고 35,000·42,500·50,000원 hard-envelope
  alert/gate 설계를 확정한다.
- `V2-W0004` unmanaged DB objects와 quality column drift의 provenance, row count, consumer를 확정한다.
- `V2-W0005` V2 ADR-005 Firestore와 V2 public tool catalog의 2026-08-28 승인 기록을 canonical owner
  문서와 traceability에 반영한다.

### Acceptance gate

- 정상월·배포월·backfill월 cost model에 Cloud Run, Scheduler, Artifact Registry, GCS, Firestore,
  MotherDuck과 provider 비용이 모두 있다.
- actual cost와 추정 cost를 구분한다.
- 현재 운영 resource snapshot이 secret 없이 재현 가능하다.
- live drift 3객체와 3컬럼에 `adopt/recreate/archive/reject` 판정이 있다.
- 설계 문서와 SPEC의 결정 상태가 일치한다.

### Rollback

읽기 전용 조사와 문서 변경뿐이므로 배포 rollback은 없다. provisioning은 Wave 1 이후다.

## 4. Wave 1 — 코드 골격과 단일 release image

### Work items

- `V2-W0101` `modules/application/ports/adapters/platform/bootstrap` package skeleton과 import contract test.
- `V2-W0102` clock, ID, money, timezone, quality status, provenance의 shared value object.
- `V2-W0103` V1 KIS client를 `SourcePort` 뒤에 감싸고 recorded fixture contract test를 만든다.
- `V2-W0104` V2 command/query bus 없이 명시적 handler registry를 구현한다. 범용 DI framework는 도입하지 않는다.
- `V2-W0105` 한 image를 SHA tag와 digest로 build하고 auth·remote·Job에 같은 digest를 배포하는 workflow.
- `V2-W0106` Artifact Registry cleanup policy를 먼저 dry-run하고 production/rollback digest keep rule을 검증한다.
- `V2-W0107` service account와 secret access matrix를 IaC 또는 versioned deployment manifest로 표현한다.

### Acceptance gate

- domain/application test가 DuckDB, MCP, HTTP, GCP SDK 없이 실행된다.
- architecture checker가 adapter→application→port 방향을 강제한다.
- 한 commit의 모든 target이 같은 image digest를 사용한다.
- cleanup dry-run은 active revision과 최근 rollback digest를 삭제 대상으로 잡지 않는다.
- V1 runtime behavior와 188개 이상 기존 test가 유지된다.

### Rollback

기존 deploy workflow와 image digest를 유지한다. V2 image workflow는 production target을 바꾸지 않고 검증
환경에서 먼저 실행한다.

## 5. Wave 2 — Operational state와 migration runner

### Work items

- `V2-W0201` Seoul의 Firestore Standard database 하나에 대한 region, free quota, IAM, application collection
  allowlist, index, TTL schema 설계·provisioning plan.
- `V2-W0202` `StateStorePort`와 local in-memory/emulator adapter, Firestore adapter.
- `V2-W0203` OAuth client/grant/code/token repository를 port로 전환하고 atomic refresh rotation을 test한다.
- `V2-W0204` KIS token ciphertext, refresh lease와 fencing token을 Firestore로 이전한다.
- `V2-W0205` pipeline run request, idempotency claim과 active lease collection을 추가한다.
- `V2-W0206` MotherDuck explicit migration CLI와 checksum, schema version gate, single migration identity.
- `V2-W0207` runtime `init_schema()`를 제거하고 startup은 read-only version check만 수행한다.
- `V2-W0208` OAuth reconnect, KIS token reissue와 Firestore rollback runbook.

### Firestore minimum collections

| Collection | Key | Retention |
| --- | --- | --- |
| `auth_users` | user id | owner lifetime |
| `auth_identities` | provider + subject digest | owner lifetime |
| `oauth_clients` | client id | revoke까지 |
| `oauth_grants` | user + client + scope hash | revoke까지 |
| `oauth_codes` | code digest | 10분 + TTL |
| `oauth_tokens` | token digest | expiry/revoke + TTL |
| `kis_token_cache` | account/app fingerprint hash | expiry 후 grace |
| `leases` | resource key | 짧은 expiry |
| `run_requests` | request id | terminal 후 30일 |

### Acceptance gate

- concurrent refresh-token exchange에서 하나만 성공하고 재사용은 거부된다.
- KIS token refresh race가 process가 달라도 하나의 lease owner만 upstream 발급을 수행한다.
- expired state는 TTL 지연과 무관하게 application에서 즉시 거부된다.
- MotherDuck runtime identity에는 DDL 권한이 없다.
- migration을 두 번 실행해도 두 번째는 no-op이며 checksum mismatch는 실패한다.
- auth/remote smoke와 실제 connector reconnect rehearsal이 성공한다.

### Rollback

- OAuth는 V1 endpoint로 되돌리고 V2 token은 revoke한다.
- KIS token은 V1 MotherDuck cache에서 새로 발급한다.
- Firestore data를 MotherDuck Security로 역복사하지 않는다.

## 6. Wave 3 — V2 warehouse와 canonical ledger

### Work items

- `V2-W0301` `bronze/silver/gold/control` schema와 object registry를 migration으로 생성한다.
- `V2-W0302` raw object manifest와 source observation envelope.
- `V2-W0303` account, instrument, position/cash snapshot과 canonical total asset.
- `V2-W0304` order, execution, transaction, cash flow와 reconciliation.
- `V2-W0305` purchase lot, trade thread, sell allocation revision과 inferred/manual quality.
- `V2-W0306` journal revision과 review queue.
- `V2-W0307` price bar dual basis, FX와 corporate action identity.
- `V2-W0308` V1→V2 historical copy/rebuild migration과 reconciliation report.

### Acceptance gate

- 모든 object가 catalog, registry, migration, repository test와 backup policy를 가진다.
- V1 raw row count와 V2 observation mapping이 설명 가능하다.
- 계좌·종목별 V2 position 수량이 canonical balance와 맞거나 명시적 exception을 가진다.
- purchase lot 합계와 position 차이를 숨기지 않는다.
- global total asset 합계가 V1 canonical snapshot과 허용오차 내 일치한다.
- raw 수정 없이 재처리해 같은 Silver key와 hash를 만든다.
- isolated local DuckDB와 temporary MotherDuck database에서 migration/restore가 통과한다.

### Rollback

V1 `main` writer와 reader를 유지한다. V2 schema를 consumer가 사용하지 않는 동안 drop하지 않고 실패
version으로 표시한 뒤 새 migration으로 교정한다.

## 7. Wave 4 — Source pipeline과 backfill

Wave 4에 들어가기 전에 source inventory와 collection basket을 DGH manifest로 검토·승인한다. 승인되지
않은 source나 dataset을 adapter, schedule 또는 backfill 대상으로 만들지 않는다.

### Work items

- `V2-W0401` pipeline manifest schema, registry, runner, stage result와 structured logging.
- `V2-W0402` fixed-argument Cloud Run Job definitions와 Scheduler manifest generator.
- `V2-W0403` 국내·해외 ledger pipeline을 V2 runner로 전환.
- `V2-W0404` 국내·미국 adjusted/raw 3년 price backfill과 incremental daily pipeline.
- `V2-W0405` KRX/issuer ETF constituent daily snapshot과 nested expansion input.
- `V2-W0406` OpenDART/SEC actual fact, KIS experimental estimate adapter.
- `V2-W0407` dividend declared/entitled/received와 manual import port.
- `V2-W0408` ECOS/FRED/ALFRED/Cboe macro profile v1.
- `V2-W0409` quality, watermark, lineage와 managed backfill queue.
- `V2-W0410` Remote MCP catalog/quality read model의 DB-only preview.

### Acceptance gate

- 같은 logical key를 두 번 실행해 canonical row나 alert candidate가 중복되지 않는다.
- failure injection 후 성공 stage를 재수행하지 않고 실패 stage부터 이어갈 수 있다.
- source rate limit과 daily call budget을 넘기기 전에 runner가 중지한다.
- 3년 backfill의 row/object/compute 증가량이 cost model 안에 있다.
- KIS 100-row pagination, ETF partial source, consensus source gap을 quality result가 표시한다.
- LLM 없이 Scheduler만으로 5거래일 연속 모든 필수 pipeline이 terminal state가 된다.

### Rollback

pipeline별 feature flag로 V2 writer를 멈추고 V1 schedule을 재활성화한다. GCS raw와 V2 schema는 보존해
원인 분석과 재처리에 사용한다.

## 8. Wave 5 — Metric, signal과 Telegram shadow

### Work items

- `V2-W0501` metric definition registry와 point-in-time evaluation engine.
- `V2-W0502` cash-flow-adjusted portfolio return, contribution, drawdown.
- `V2-W0503` SMA20/50/120, volume ratio, RSI14, Bollinger context, ATR20.
- `V2-W0504` position/lot/thread MFE·MAE·episode high와 2% risk cap.
- `V2-W0505` ETF look-through와 residual/confidence.
- `V2-W0506` actual/consensus surprise, guidance cut, NTM revision.
- `V2-W0507` alert state machine, de-duplication, recovery와 delivery ledger.
- `V2-W0508` Telegram payload redaction·test destination·retry.
- `V2-W0509` 3년 replay, asset-class calibration과 2주 shadow report.

### Acceptance gate

- metric golden fixtures가 SQL과 Python reference 계산에 일치한다.
- point-in-time replay가 미래 consensus, future price, later journal revision을 읽지 않는다.
- bootstrap threshold의 일별 alert 예산과 최대 누락 사례가 문서화된다.
- shadow 2주 동안 Telegram 전송 없이 message candidate와 de-duplication이 검증된다.
- 전체 계좌번호·총자산 절대액·credential이 payload와 log에 없다.
- 사용자가 threshold version과 test message를 승인하기 전 delivery flag가 켜지지 않는다.

### Rollback

delivery feature flag를 끄고 signal evaluation은 DB-only로 유지한다. signal rule을 in-place 수정하지 않고
이전 approved version을 활성화한다.

## 9. Wave 6 — Stateless Remote MCP V2

### Work items

- `V2-W0601` 18개 이하 public tool DTO와 scope matrix.
- `V2-W0602` thin MCP handler와 application query/command mapping.
- `V2-W0603` `stateless_http=true`, JSON response, timeout·body-size·host/origin policy.
- `V2-W0604` `mcp:collect` managed Job invocation과 run status polling.
- `V2-W0605` `mcp:journal.write` expected revision·actor·idempotency.
- `V2-W0606` Claude/ChatGPT/iPhone connector discovery, auth, tool call compatibility suite.
- `V2-W0607` V1 tool→V2 tool migration guide와 unsupported capability response.

### Acceptance gate

- 두 replica에 요청을 분산해도 session error가 없다.
- legacy client compatibility 또는 명시적 client minimum version이 검증된다.
- scope별 positive/negative test가 있고 read token으로 collect/journal이 거부된다.
- 장기 pipeline tool은 request 안에서 수행하지 않고 run id를 반환한다.
- catalog tool만으로 LLM이 grain, freshness, quality, metric version과 unsupported interpretation을 설명할 수 있다.
- 실제 Claude와 ChatGPT에서 최소 portfolio, market, catalog, pipeline status, journal write smoke가 성공한다.

### Rollback

기존 Remote MCP revision으로 traffic을 되돌린다. OAuth issuer와 V1 tool catalog는 cutover 전까지 유지한다.

## 10. Wave 7 — Dual-run, cutover와 Remote SSOT

### Work items

- `V2-W0701` V1/V2 daily comparison report: total asset, holdings, orders, prices, signals, freshness.
- `V2-W0702` 최소 10거래일 dual-run과 차이 triage.
- `V2-W0703` backup/restore rehearsal과 RPO/RTO evidence.
- `V2-W0704` production connector를 V2 revision/tool catalog로 refresh.
- `V2-W0705` Scheduler를 V2 jobs로 전환하고 V1 jobs를 paused 상태로 보존.
- `V2-W0706` cost actual·forecast와 error budget review.
- `V2-W0707` cutover approval record와 rollback window.

### Acceptance gate

- unexplained monetary/quantity difference가 0이다.
- `partial` 차이는 source coverage와 quality reason으로 설명된다.
- 10거래일 필수 schedule SLO와 Telegram de-duplication이 충족된다.
- restore rehearsal이 RPO 24시간/RTO 4시간 안에 끝난다.
- 정상월 forecast가 7,500원 목표 또는 승인된 예외 안이고 hard ceiling 50,000원보다 낮다.
- iPhone을 포함한 사용자-facing 문서가 Remote MCP URL 하나만 가리킨다.

### Rollback

- connector를 V1 revision으로 되돌린다.
- V1 Scheduler를 resume하고 V2 Scheduler를 pause한다.
- V2 write는 멈추되 data는 보존한다.
- rollback 후 생성된 V1/V2 gap을 다음 cutover 전 재처리한다.

## 11. Wave 8 — V1 retirement와 안정화

### Work items

- `V2-W0801` local stdio의 사용자 setup·문서·connector 등록 제거.
- `V2-W0802` V1 MCP tool과 disabled order stub을 public catalog에서 제거.
- `V2-W0803` `main` consumer log 0 확인, compatibility view 또는 archive 전환.
- `V2-W0804` target별 과거 image와 V1 Job/Scheduler cleanup plan 승인.
- `V2-W0805` quarterly restore, monthly capacity/cost, source contract review runbook.
- `V2-W0806` obsolete package/shim 제거와 final architecture audit.

### Acceptance gate

- 새 clone/setup이 local MCP를 제품표면으로 등록하지 않는다.
- V1 service/job/image 삭제 대상과 복구 가능성을 사용자가 승인한다.
- `main`에 V2 writer가 없고 external consumer도 없다.
- catalog/DDL/repository/backup/live inventory drift가 0이다.
- architecture, warehouse, MCP surface, security, deployment audit가 모두 통과한다.

### Rollback

retirement 전 최종 V1 image digest, config manifest와 database backup을 보존한다. 삭제는 별도 파괴적 작업
승인 뒤 수행한다.

## 12. 공통 검증 matrix

| Test level | 검증 대상 | 필수 evidence |
| --- | --- | --- |
| unit | domain calculation, value object, rule | deterministic fixture |
| contract | KIS/DART/SEC/ECOS response mapping | anonymized recorded response + schema |
| repository | SQL key, idempotency, revision | local DuckDB + MotherDuck integration |
| migration | apply/idempotency/verify/rollback metadata | isolated database report |
| pipeline | stage resume, watermark, lease, quality | failure injection run |
| security | scope, token rotation, redaction, IAM | negative tests + audit log |
| MCP | discovery, schema, tool response | in-process + remote connector smoke |
| replay | point-in-time and signal calibration | 3년 result summary |
| shadow | schedule, alert candidate, de-dup | 2주 production-like run |
| restore | raw/Parquet to serving views | quarterly timestamped evidence |
| cost | actual/forecast/resource growth | monthly cost report |

## 13. Definition of Done

V2 전체 설계의 구현 완료는 다음이 모두 참일 때만 선언한다.

1. Remote MCP가 유일한 사용자-facing MCP이며 local 안내가 없다.
2. 인증·KIS token·lease는 Firestore/Secret Manager에 있고 MotherDuck Security table을 runtime이 사용하지 않는다.
3. MotherDuck `bronze/silver/gold/control`이 versioned migration과 catalog로 관리된다.
4. 필수 pipeline은 LLM 없이 정기 실행되고 LLM trigger는 같은 managed Job을 사용한다.
5. 승인된 source basket의 backfill·incremental 수집·quality·lineage가 동작한다.
6. 평단가, lot/thread, 배당, ETF, fundamentals, macro와 signal 데이터 제품이 point-in-time으로 재현된다.
7. Telegram은 승인된 rule version의 `주의` 이상만 보내고 중복·민감정보를 억제한다.
8. 직접 SQL과 MCP가 같은 metric version에서 일치한다.
9. dual-run, remote smoke, restore rehearsal과 rollback rehearsal evidence가 있다.
10. 정상월 비용 목표와 월 50,000원 ceiling을 충족하고 비용 gate가 실제 구성에 반영돼 있다.
11. unmanaged live drift와 V1 retirement 대상이 승인된 방식으로 처리됐다.
12. 전체 automated suite와 architecture/warehouse/MCP/security contract check가 통과한다.

이 중 하나라도 간접 증거나 계획만 있으면 V2 완료가 아니다.

## 14. 다음 설계 검토 묶음

구현 전 다음 세 묶음을 순서대로 승인한다. 필드별로 승인을 반복하지 않는다.

1. **Architecture delta**: Firestore state plane, stateless MCP, build-once image, V2 public tool catalog
2. **Logical data model**: Silver event/lot/thread/fundamental/dividend와 Gold metric grain
3. **Execution baseline**: actual cost, schedule manifest, Wave 0~2 migration·rollback 계획
