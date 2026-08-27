# KIS Portfolio V2 Architecture Delta Review

> 상태: 2026-08-28 사용자 승인 완료 — 구현·provisioning 미착수
> 기준일: 2026-08-28
> Work Item: `WI-001`
> 대상 결정: `V2-ADR-003`, `V2-ADR-004`, `V2-ADR-005`, `V2-ADR-006`, `V2-ADR-009`,
> `V2-ADR-011`, `V2-ADR-015`
> 범위 제한: 이 문서는 architecture 승인안이다. Firestore 활성화, production 배포, DB migration,
> connector 변경이나 V1 tool 제거를 수행하지 않는다.

## 1. 결론

네 architecture delta는 모두 V2의 비용·보안·운영 목표에 맞다. 다만 원안 그대로가 아니라 아래 보완을
포함해 승인했다.

| Delta | 권고 | 승인에 포함할 보완 |
| --- | --- | --- |
| Operational state | 승인 | Firestore Standard database 하나를 사용하고 collection allowlist·암호화 key 격리로 보완; database 분리는 후속 조건부 선택 |
| Remote MCP transport | 조건부 승인 | `stateless_http=true`와 JSON response를 목표로 하되 실제 Claude·ChatGPT·iPhone compatibility와 back-channel 부재를 검증 |
| Release image | 승인 | commit당 한 번 build한 digest를 auth·remote·Job에 배포하고 release manifest로 부분 실패를 복구 |
| Public MCP catalog | 승인 | 18개 결과 중심 tool, 세 scope, 주문 tool 제거, bounded read-through와 managed pipeline 실행의 의미 분리 |

이 네 선택은 서로 관련되지만 하나의 big-bang 변경은 아니다. build-once를 먼저 도입할 수 있고, Firestore
전환과 stateless transport는 별도 rehearsal을 통과해야 하며, V2 tool catalog는 V2 read model이 준비된 뒤
parallel endpoint/revision에서 검증한다.

## 2. 검토 기준과 현재 근거

### 2.1 승인된 제품 제약

- 제품 표면의 SSOT는 OAuth Remote MCP다. local stdio MCP는 개발·검증 harness일 뿐 사용자 경로가 아니다.
- Scheduler가 필수 수집의 SSOT이며 LLM 예약 작업은 같은 managed pipeline을 추가 호출할 수 있다.
- 일반 월 목표는 7,500원, 절대 상한은 50,000원이며 always-on database·worker를 두지 않는다.
- MotherDuck은 장기 분석 사실과 catalog를 맡고, 주문 실행은 제품 범위가 아니다.
- 사용자 데이터는 preservation-first로 전환하고 V1을 지운 뒤 V2를 검증하는 순서를 금지한다.

### 2.2 2026-08-28 현재 상태

| 영역 | 확인 결과 | Delta 근거 |
| --- | --- | --- |
| MCP surface | contract 검사 통과, public tool 35개 | raw endpoint와 저장/분석 도구가 섞여 있어 질문 결과 중심 계약이 필요 |
| 코드 경계 | MCP adapter 1,202행, DB repository 1,442행, KIS service 1,560행 | V2 handler를 얇은 application adapter로 다시 구성할 근거 |
| DB access | MCP adapter가 직접 `get_connection()`을 호출하는 경로 10개 | public contract와 warehouse implementation 결합을 제거해야 함 |
| DB startup | 최초 연결 시 `init_schema()` 실행 | runtime DDL과 operational transaction을 분리해야 함 |
| Remote MCP | in-process `session_manager`, max instance 1, timeout 3,600초 | legacy session 의존을 제거할 compatibility review 필요 |
| Deploy | service/job target마다 `--source .` 실행 | 같은 commit도 target별 build 결과·storage가 달라질 수 있음 |
| Cloud Run | auth/remote min 미지정=0, max 1; 최근 3개 Job 성공 | scale-to-zero와 작은 Job topology는 재사용 가능 |
| Artifact Registry | `cloud-run-source-deploy` 약 2.65 GB, cleanup policy 없음 | build-once와 보존 정책이 필요 |
| Firestore | API 비활성 | 승인은 provisioning 권한이 아니며 별도 Work Item이 필요 |
| MotherDuck | managed 25 tables + 2 views, live drift 존재 | V1 Security table을 자동 삭제·승격하지 말고 명시적으로 cutover해야 함 |
| 비용 | 7,500원 budget은 존재하나 actual billing baseline 없음 | budget alert를 actual 비용 증거로 취급하면 안 됨 |

읽기 전용 운영 확인에서 production, database, scheduler, connector는 변경하지 않았다.

## 3. Delta A — Firestore operational state plane

### 3.1 문제와 대안

OAuth authorization code 소비, refresh token rotation, KIS token refresh lease와 pipeline idempotency claim은
현재값을 읽고 경쟁자를 배제한 뒤 원자적으로 갱신해야 한다. MotherDuck은 분석 warehouse로는 적합하지만 이
짧은 수명의 OLTP state까지 맡기면 auth/runtime과 analytics 장애·권한·migration 경계가 결합된다.

| 대안 | 장점 | 판단·trade-off |
| --- | --- | --- |
| MotherDuck Security 유지 | 신규 서비스 없음 | transaction/lease와 warehouse lifecycle이 결합되고 runtime DDL·동시성 부담을 유지 |
| Cloud SQL | 익숙한 관계형 transaction | 작은 1인 앱에 고정 운영비와 관리 부담이 큼 |
| process memory/Secret Manager | 단순함 | replica·restart 간 current state와 atomic claim을 제공하지 못함 |
| Firestore 한 database | transaction, TTL, scale-to-zero형 사용량 과금 | **선택**; collection IAM 부재를 adapter allowlist와 secret key 격리로 보완 |
| Firestore 두 database | transaction을 유지하며 database 단위 IAM 격리 | 다중 사용자·운영자 분리·security audit 요구까지 보류 |

### 3.2 승인 결정

`V2-ADR-005`를 다음 내용으로 승인한다.

1. 논리적 operational state plane은 Seoul `asia-northeast3`의 Firestore Standard database 하나로 한다.
2. `auth_*` collection은 user, identity, OAuth client/grant/code/token digest를 소유한다.
3. `ops_*` collection은 encrypted KIS token cache, refresh lease, run request와 idempotency claim을 소유한다.
4. MotherDuck V2는 `bronze/silver/gold/control`만 소유하며 active auth/token/lease를 소유하지 않는다.
5. database 분리는 다중 사용자, 별도 운영자, 외부 contributor 또는 security audit에서 collection-level
   application guard가 불충분하다고 판단될 때 새 ADR로 수행한다.

한 database 선택은 비용·운영 단순성을 우선한 의도적 trade-off다. Firestore 서버 IAM은 collection별
접근을 강제하지 못하므로 아래 adapter allowlist와 secret key 분리를 보안 계약으로 둔다.

### 3.3 IAM과 state 계약

| Identity | 허용 collection | 보완 통제 |
| --- | --- | --- |
| auth service | `auth_*` | KIS token encryption key를 주지 않음 |
| Remote MCP | bearer 검증용 `auth_oauth_tokens`, 필요한 `ops_*` | OAuth provider client secret을 주지 않음 |
| pipeline Job | `ops_*` | OAuth provider/session/digest key를 주지 않음 |
| deploy/migration | provisioning 시에만 전체 metadata | runtime identity로 사용하지 않음 |

- database-level IAM 뒤에 `StateStorePort` adapter가 identity별 collection allowlist를 강제하고 negative test를
  가진다. 이 allowlist가 IAM과 같은 강제 경계는 아니라는 잔여 위험을 숨기지 않는다.
- raw OAuth bearer는 저장하지 않고 keyed digest만 저장한다.
- KIS access token은 application-level ciphertext만 저장하고 encryption key는 Secret Manager에 둔다.
- OAuth code consume, refresh rotation, lease acquire/renew/release, idempotency claim은 Firestore transaction으로
  구현한다. transaction callback에는 외부 API 호출을 넣지 않는다.
- lease에는 `owner_id`, `expires_at`, 증가하는 `fencing_token`을 두고, lease 획득 후 늦게 끝난 worker가 최신
  결과를 덮어쓰지 못하게 한다.
- TTL은 청소 수단일 뿐 유효성 판단 수단이 아니다. 모든 read는 먼저 `expires_at`을 검사한다.

### 3.4 Migration과 rollback

1. emulator/in-memory adapter와 concurrency contract test를 먼저 만든다.
2. database와 IAM을 별도 provisioning Work Item으로 만들고 deletion protection을 켠다.
3. OAuth bearer와 refresh token은 복사하지 않는다. V2 connector에서 재인증해 새 digest state를 만든다.
4. KIS token은 V2에서 새로 발급한다. V1 ciphertext를 기본 migration 경로로 삼지 않는다.
5. V1 MotherDuck Security table은 dual-run 동안 보존하되 V2가 읽거나 dual-write하지 않는다.
6. rollback은 V1 endpoint/revision으로 traffic을 되돌리고 V2 token을 revoke한 뒤 다시 연결한다. Firestore
   state를 MotherDuck으로 역복사하지 않는다.

초기에는 PITR·유료 backup을 켜지 않는다. auth state는 client reconnect, KIS token은 reissue, run request는
MotherDuck Control의 immutable run summary와 Scheduler에서 재구성하는 recovery contract를 먼저 검증한다.

### 3.5 비용·검증 gate

Firestore 무료 할당은 프로젝트당 정확히 한 database에만 적용되고 TTL delete, PITR, backup/restore는 무료가
아니다. 한 database를 사용하더라도 TTL delete는 과금될 수 있으므로 승인과 provisioning 사이에 다음 gate를
둔다.

- 정상 7일 rehearsal의 read/write/delete/storage를 측정한다.
- TTL delete 비용을 별도로 표시하고, 예상 정상월 합계가 7,500원 목표 안인지 확인한다.
- 실제 비용을 얻기 전에는 “무료”라고 기록하지 않는다.
- concurrent refresh exchange 하나만 성공, cross-process KIS refresh 한 owner만 upstream 호출, expired document
  즉시 거부, identity별 collection allowlist negative test를 모두 통과해야 한다.

### 3.6 Secret Manager와 분석 DB 결정

장기 credential과 cryptographic key의 SSOT는 GCP Secret Manager로 확정한다. Firestore에는 동적으로 바뀌는
digest/ciphertext/lease만, MotherDuck에는 분석 사실만 둔다.

2026-08-28 운영 project에는 Secret Manager secret resource가 23개 있고 deploy code는 각각의 `latest`
version을 주입한다. 각 resource에 active version이 하나뿐이라고 가정해도 무료 6개를 제외한 17개가 과금되어
월 약 USD 1.02가 된다. disabled version도 active로 과금되므로 실제 active version이 더 많으면 비용도
증가한다. secret 값이나 version payload는 이번 조사에서 읽지 않았다.

비용과 IAM을 함께 지키기 위해 하나의 mega-secret이 아니라 다음 **신뢰경계별 최대 6개 bundle**을 목표로
한다.

| Bundle | 내용 | 주 사용 identity |
| --- | --- | --- |
| KIS provider | 계좌별 app key/secret과 confidential account config | Remote MCP, pipeline |
| OAuth providers | Google/GitHub provider credentials | auth |
| OAuth server keyring | session, token digest, request-state와 static client key | auth, 필요한 검증자 |
| Warehouse access | MotherDuck credential | Remote MCP, pipeline, migration |
| Token encryption keyring | KIS token encryption current/previous key | Remote MCP, pipeline |
| Notification | Telegram credential | pipeline |

- automatic replication을 기본으로 사용한다. 과금상 한 location으로 계산되고 별도 지역 요구가 생길 때만
  user-managed replication을 검토한다.
- `latest`가 아니라 숫자 version을 release manifest에 pin한다.
- instance/job 시작 시 필요한 bundle만 읽고 process memory에 cache하며 request마다 다시 읽지 않는다.
- rotation 시 previous version을 disable한 채 7일 rollback window를 두고, 확인 뒤 destroy한다. disabled
  version도 과금되므로 무기한 보관하지 않는다.
- 일반 config와 공개 identifier는 Secret Manager에 넣어 version 수를 늘리지 않는다.

분석 warehouse는 MotherDuck을 유지한다. BigQuery는 serverless이고 월 10 GiB storage와 1 TiB query free
tier가 있어 GCP-native 대안으로 충분히 유력하지만, 현재 약 49 MiB 규모에서 DuckDB 로컬 대칭성, 기존 schema,
ad-hoc SQL과 migration 비용을 버릴 근거가 없다. 다음 조건 중 하나가 생길 때만 비교 ADR을 다시 연다.

- MotherDuck 용량·동시성·가용성·비용이 승인 SLO를 충족하지 못함
- GCP 내부 IAM/audit 또는 다른 GCP analytics와의 결합이 핵심 요구가 됨
- 실제 query workload가 BigQuery free tier/partition cost model에서 더 유리하다는 측정 결과가 나옴

일반 Cloud SQL은 instance 실행 중 compute와 provisioned storage 비용이 있고 분석 warehouse보다 OLTP에
가깝다. Google AI Studio 전용 Developer edition에는 scale-to-zero가 있지만 이 repository에서 일반적인
Cloud SQL API로 만들 수 없고 backup/private network 같은 production 기능도 제한되므로 대안에서 제외한다.

## 4. Delta B — Stateless Remote MCP

### 4.1 정확한 의미

현재 공식 Python MCP SDK에서 최신 protocol request는 원래 sessionless다. `stateless_http=true`는 legacy
protocol 경로의 in-memory session을 request 단위로 바꾸는 option이다. 따라서 이 결정은 “모든 MCP를 새로
stateless로 만든다”기보다 legacy client도 sticky session 없이 서비스할 것인가에 대한 선택이다.

`json_response=true`는 POST를 단일 JSON body로 응답한다. 그 대신 request-scoped progress/log stream과
server-to-client sampling·push elicitation 같은 back-channel을 사용할 수 없다. V2는 이 기능을 제품 계약에
포함하지 않고, 오래 걸리는 작업은 `run_id`를 반환하는 managed Job으로 전환하므로 이 trade-off를 수용할
수 있다.

### 4.2 승인 결정과 구현 조건

`V2-ADR-004`를 compatibility gate 조건으로 승인한다.

- 목표 transport는 Streamable HTTP, `stateless_http=true`, `json_response=true`다.
- official ASGI app/lifespan을 사용하고 private `session_manager` wiring 의존을 제거한다.
- sampling, elicitation push, `roots/list`, resource subscription과 in-call progress를 V2 public contract에
  추가하지 않는다. 필요해지면 이 ADR을 다시 검토한다.
- exact Host/Origin allowlist와 request body 상한을 명시한다. body 상한은 SDK 기본 4 MiB에서 시작한다.
- warm request 300초 이하를 목표로 하되, 외부 호출이 60초를 넘을 수 있으면 동기 tool이 아니라 Job으로
  바꾼 뒤 timeout을 축소한다.
- production은 먼저 max instance 1을 유지한다. staging에서 두 replica로 legacy/modern request를 분산한 뒤
  max 2 허용 여부를 별도 운영 결정으로 남긴다.
- 최신 protocol의 multi-round-trip request를 도입하면 모든 replica가 같은 request-state key ring과 같은
  server name을 써야 한다. 현재 V2 tool에는 multi-round-trip을 넣지 않는다.

### 4.3 Compatibility gate와 rollback

다음 실제 client smoke 없이는 connector를 전환하지 않는다.

1. Claude web/desktop과 iPhone Claude에서 discovery, OAuth, list tools, portfolio/market call.
2. ChatGPT connector에서 같은 흐름과 catalog/pipeline status call.
3. legacy와 latest protocol test client를 두 replica에 교차 분산해 session error가 없는지 확인.
4. 4 MiB 초과 request 거부, invalid Host/Origin, expired/wrong-scope bearer negative test.
5. pipeline trigger는 즉시 `run_id`를 반환하고 장기 실행이 HTTP request에 매달리지 않는지 확인.

실패 시 traffic을 기존 stateful revision으로 되돌린다. OAuth issuer와 V1 catalog는 cutover 완료 전까지
유지한다.

## 5. Delta C — Build once, deploy one digest

### 5.1 승인 결정

`V2-ADR-003`의 두 service 경계와 `V2-ADR-011`의 한 image digest를 함께 승인한다.

- auth와 Remote MCP는 secret/IAM 때문에 별도 Cloud Run service로 유지한다.
- application image는 commit마다 한 번만 build하고 SHA tag를 digest로 resolve한다.
- auth, remote와 모든 managed Job은 정확히 같은 `image@sha256:...`를 사용한다.
- command, args, service account, secrets, concurrency, timeout은 target manifest가 별도로 소유한다.
- `latest` tag를 production 배포 입력으로 사용하지 않는다.

같은 image를 쓴다는 것은 같은 권한을 쓴다는 뜻이 아니다. runtime identity와 secret injection 경계는 현재보다
더 엄격하게 유지한다.

### 5.2 Release transaction

Cloud Run 여러 target 배포는 하나의 원자적 transaction이 아니므로 release manifest가 일관성 경계다.

1. test와 image vulnerability/build metadata 확인 후 한 번 push한다.
2. digest, source commit, config hash, schema minimum, target command를 immutable release manifest에 기록한다.
3. auth/remote는 no-traffic 또는 canary revision으로 smoke하고 Job은 실행하지 않은 definition으로 갱신한다.
4. target별 deploy 결과를 기록하고 모든 target이 같은 digest인지 verify한다.
5. 일부 target 실패 시 이미 바뀐 target을 previous manifest digest/config로 되돌린다.
6. Scheduler 전환은 image 배포와 분리하고, Job smoke 뒤에만 적용한다.

### 5.3 Artifact 보존

초기 cleanup 제안은 다음과 같다.

- `prod-current`, `prod-previous`, 명시적 `rollback-*` tag와 이들이 가리키는 digest는 keep한다.
- 최근 10개 version은 keep하고, 그 밖의 untagged version은 30일 이후 delete 후보로 둔다.
- 먼저 dry-run으로 active revision, active Job과 rollback manifest digest가 삭제 후보가 아님을 검증한다.
- 확인 뒤 active policy로 전환하고 registry size와 삭제량을 월별 기록한다.

Cloud Run service revision은 deploy 시 image copy를 보존하지만, 이것을 release archive 계약으로 대체하지
않는다. rollback manifest가 가리키는 registry digest를 명시적으로 keep한다.

## 6. Delta D — V2 public MCP catalog

### 6.1 Catalog 원칙

`V2-ADR-015`와 18개 tool budget을 승인한다.

- tool은 KIS endpoint 이름이 아니라 사용자의 질문 결과 단위다.
- public tool을 추가한다고 source adapter endpoint를 추가하는 것은 아니며 그 반대도 같다.
- 모든 read 응답은 `schema_version`, `as_of`, `source`, `freshness`, `quality`, `missing_coverage`,
  `lineage_ref`, `request_id` envelope를 공통으로 가진다.
- `mcp:read`는 bounded live read-through와 observation cache write를 허용한다. 계좌·시장에 대한 외부 변경은
  하지 않는다.
- `mcp:collect`는 allowlisted managed pipeline 실행 전용이다. container args/env/timeout 임의 override를
  허용하지 않고 즉시 `run_id`를 반환한다.
- `mcp:journal.write`는 expected revision과 idempotency key를 요구하고 journal/thread를 append-only revision으로
  기록한다.
- scope 추가는 기존 grant의 자동 확대가 아니다. collect/journal 사용자는 명시적으로 재동의·재연결한다.
- 주문 stub을 포함한 모든 주문 tool은 V2 public catalog에서 제거한다.

### 6.2 승인 대상 18개

| Scope | Tool | 동작 계약 |
| --- | --- | --- |
| read | `get-portfolio-overview` | canonical total asset, account/asset allocation, holdings, cash, quality; stored 또는 bounded live freshness policy |
| read | `get-position-analysis` | position·lot·thread별 손익, impact, drawdown과 risk |
| read | `get-performance-history` | cash-flow-adjusted portfolio/position/lot/thread history와 allocation trend |
| read | `get-market-snapshot` | 국내·미국 price/quote/FX의 cache 또는 bounded live read-through |
| read | `get-market-history` | governed price/FX bars와 MA20/50/120, volume, RSI, Bollinger context |
| read | `get-trade-ledger` | order, execution, transaction, settlement와 cash-flow reconciliation |
| read | `get-trade-thread` | purchase lot, trade thread, sell allocation과 journal revision |
| read | `get-dividend-summary` | declared, entitled, received와 월별 증감 |
| read | `get-fundamental-outlook` | actual, pre-release consensus, surprise, guidance, scenario와 valuation assumptions |
| read | `get-exposure-analysis` | direct holding, ETF constituent look-through와 macro exposure |
| read | `get-signal-status` | rule/version/input/quality를 포함한 현재·과거 signal 상태 |
| read | `get-data-catalog` | dataset/object/metric grain, source, schedule, owner와 lineage 설명 |
| read | `get-data-quality` | freshness, completeness, reconciliation과 known gap |
| read | `get-pipeline-run` | run/stage 상태, watermark, counts와 실패 원인 |
| read | `get-journal-review-queue` | 매매일지가 없거나 확인이 필요한 거래·thread 질문 후보 |
| collect | `run-managed-pipeline` | allowlist pipeline trigger, validated request, idempotency와 `run_id` |
| journal.write | `upsert-trade-journal` | expected revision 기반 journal 신규 revision 기록 |
| journal.write | `revise-trade-thread` | lot/thread/sell allocation의 명시적 revision 기록 |

`get-market-history`의 RSI는 관행상 “20일 RSI, 50일 RSI”처럼 각각 따로 부르는 것이 아니라 기본 RSI14와
선택 가능한 period를 제공한다. MA20/50/120과 volume, Bollinger는 같은 결과 안의 설명 가능한 context이며
각각 별도 public tool로 늘리지 않는다.

### 6.3 V1 35개 tool migration map

| V1 capability/tool | V2 owner | 처리 |
| --- | --- | --- |
| configured accounts, token statuses | `get-portfolio-overview`, `get-data-quality` | alias/마스킹 계좌와 readiness만 노출; token 전용 public tool 제거 |
| account balance, overseas balance/deposit/settlement, latest/total overview | `get-portfolio-overview` | account filter와 freshness policy로 통합 |
| refresh all snapshots | `run-managed-pipeline` + `get-pipeline-run` | `portfolio-refresh` allowlist, async status |
| domestic/overseas current price와 ask | `get-market-snapshot` | market/instrument/source policy DTO로 통합 |
| domestic/overseas price history, stock info, FX history | `get-market-history` 또는 managed collection | read와 범위가 큰 수집을 분리 |
| cached price/FX, Bollinger | `get-market-history` | metric version과 quality를 포함해 통합 |
| domestic/overseas order·transaction·detail | `get-trade-ledger` | canonical identity와 source filter로 통합 |
| domestic/overseas period profit | `get-performance-history`, `get-trade-ledger` | 계산 결과와 원장 근거를 분리 |
| portfolio/total history, daily change, trend, allocation | `get-performance-history`, `get-portfolio-overview` | canonical cash-flow-adjusted metric으로 대체 |
| portfolio anomaly | `get-signal-status` | rule/version/input을 가진 signal로 대체 |
| domestic/overseas submit-order stub | 없음 | V2에서 제거하고 unsupported capability를 명시적으로 응답 |

V1에 없던 dividend, fundamental/consensus, ETF look-through, catalog/quality/lineage, journal과 managed pipeline은
V2 data contract가 실제로 구현된 뒤에만 catalog에 노출한다. 이름만 먼저 등록해 빈 tool을 만들지 않는다.

## 7. 결정을 함께 적용하는 순서

| 순서 | 변경 | 선행 조건 | production 영향 |
| --- | --- | --- | --- |
| 1 | build-once digest workflow | 현재 test, release manifest | 기존 target behavior 유지 가능 |
| 2 | Firestore adapters와 provisioning | 비용/IAM/concurrency gate | V1과 격리해 rehearsal |
| 3 | auth/KIS state cutover | connector reconnect runbook | revision/endpoint 단위 rollback |
| 4 | stateless MCP transport | actual client compatibility | V1 revision 유지 |
| 5 | V2 18-tool catalog | V2 read model과 scope tests | parallel revision에서 검증 |
| 6 | connector/Scheduler cutover | 10거래일 dual-run·restore·cost evidence | Remote MCP SSOT 완성 |

다음 단계는 구현 일괄 승인이 아니다. 이 review를 승인한 뒤 각 행을 별도 Work Item으로 시작하고,
provisioning·deployment·connector cutover 시점에는 다시 명시적 실행 승인을 받는다.

## 8. 승인 기록

사용자는 2026-08-28 다음 네 항목을 한 묶음으로 승인했다.

1. Firestore state plane 하나를 승인하되 collection allowlist, Secret Manager key 격리, reconnect/reissue
   migration과 비용 rehearsal을 필수 조건으로 한다. database 분리는 명시된 확장 조건까지 보류한다.
2. stateless/JSON Remote MCP를 승인하되 actual Claude·ChatGPT·iPhone compatibility, no-back-channel 계약과
   V1 traffic rollback을 필수 조건으로 한다.
3. auth/resource 두 service를 유지하고 모든 service/Job을 같은 immutable digest로 배포하는 build-once
   release를 승인한다.
4. 세 scope의 18개 V2 public tool catalog와 주문 tool 제거를 승인한다.

`SPEC.md`와 V2 system design의 해당 ADR을 `approved`로 승격하고, 한 Firestore database와 신뢰경계별
Secret Manager bundle 결정을 반영한다. 구현은 새 Work Item에서만 시작한다.

## 9. 공식 근거

- Firestore transaction은 read 뒤 write를 원자적으로 적용하며 concurrent modification 시 transaction을
  재시도한다: <https://firebase.google.com/docs/firestore/manage-data/transactions>
- Firestore 무료 할당은 한 database에만 적용되고 TTL delete·PITR·backup/restore는 무료 대상이 아니다:
  <https://firebase.google.com/docs/firestore/pricing>
- TTL 삭제는 즉시가 아니며 일반적으로 만료 뒤 24시간 안에 수행된다:
  <https://firebase.google.com/docs/firestore/ttl>
- Firestore는 여러 database와 database별 IAM condition을 지원하고 Seoul region을 제공한다:
  <https://docs.cloud.google.com/firestore/native/docs/manage-databases>,
  <https://firebase.google.com/docs/firestore/locations>
- 공식 MCP Python SDK에서 최신 protocol은 sessionless이며 `stateless_http`는 legacy 경로의 session
  trade-off다. JSON response는 in-call progress와 back-channel을 제거한다:
  <https://github.com/modelcontextprotocol/python-sdk/blob/main/docs/run/deploy.md>,
  <https://github.com/modelcontextprotocol/python-sdk/blob/main/docs/run/index.md>
- Cloud Run은 exact digest를 배포할 수 있고 revision은 immutable이며, Job도 기존 container image로 만들 수
  있다: <https://docs.cloud.google.com/run/docs/deploying>,
  <https://docs.cloud.google.com/run/docs/create-jobs>
- Artifact Registry cleanup은 delete/keep policy와 dry-run을 지원하며 keep 조건이 delete보다 우선한다:
  <https://docs.cloud.google.com/artifact-registry/docs/repositories/cleanup-policy-overview>
- Secret Manager는 월 6 active versions와 10,000 access가 무료이며 disabled version도 active로 과금된다.
  automatic replication은 한 location으로 계산되고 숫자 version pin이 권고된다:
  <https://cloud.google.com/secret-manager/pricing>,
  <https://docs.cloud.google.com/secret-manager/docs/best-practices>
- BigQuery free tier는 월 10 GiB storage와 1 TiB query processing을 제공한다:
  <https://cloud.google.com/bigquery/pricing>
- 일반 Cloud SQL은 running instance compute와 provisioned storage가 과금된다. scale-to-zero Developer edition은
  Google AI Studio를 통해서만 만들 수 있고 기능 제한이 있다:
  <https://cloud.google.com/sql/pricing>,
  <https://docs.cloud.google.com/sql/docs/postgres/ai-assisted-coding-and-cloud-sql>
