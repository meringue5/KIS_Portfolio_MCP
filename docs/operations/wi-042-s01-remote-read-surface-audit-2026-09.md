# WI-042-S01 Remote MCP V2 read-surface audit — 2026-09-02

> Work Item: `WI-042-S01`
> 상태: closed research-only
> 변경 분류: architecture evidence and implementation-boundary clarification
> 범위: repository, installed MCP SDK and local tests
> 제외: DTO/handler implementation, public catalog change, OAuth grant change, deployment and live client smoke

## 결론

현재 V1 35-tool server를 in-place로 축소하거나 그대로 감싸지 않는다. WI-042는 **별도의 V2 18-tool
builder와 parallel endpoint/revision**으로 구현해야 한다. V1은 WI-046 cutover 전까지 rollback target으로
보존한다. V2 handler는 raw KIS/DB payload를 반환하지 않고 application query가 만든 versioned DTO만 얇게
등록한다.

WI-042-S01은 MS-002가 닫히기 전에 가치 있게 수행할 수 있는 마지막 계획된 MS-003 선행조사다. 이후
WI-043~046은 각각 WI-042 구현, 실제 client compatibility, dual-run evidence와 owner cutover approval을
선행조건으로 가지므로 지금 조사하면 가정이 빠르게 낡는다. MS-002 운영 증적 수집·closeout과 장애 발생 시
증거 보존은 계속되지만, 그것은 새 MS-003 선행조사가 아니다.

## 현재 V1 surface evidence

MCP surface checker는 정확히 35 tools와 disabled order stubs를 확인했다. 현재 remote는 같은
`build_mcp_server()`를 사용하므로 OAuth `mcp:read` token으로 아래 전체 catalog에 접근한다.

| V1 group | Count | Current tools | V2 destination |
| --- | ---: | --- | --- |
| account/runtime metadata | 2 | `get-configured-accounts`, `get-all-token-statuses` | `get-portfolio-overview`, `get-data-quality`; token 전용 public tool 제거 |
| live portfolio/account | 6 | `get-account-balance`, `refresh-all-account-snapshots`, `get-total-asset-overview`, `get-overseas-balance`, `get-overseas-deposit`, `get-overseas-settlement-balance` | overview read와 async managed collection/run status 분리 |
| current market | 3 | `get-stock-price`, `get-stock-ask`, `get-overseas-stock-price` | `get-market-snapshot` |
| history/cache/indicator | 7 | `get-stock-info`, `get-stock-history`, `get-overseas-stock-history`, `get-exchange-rate-history`, `get-price-from-db`, `get-exchange-rate-from-db`, `get-bollinger-bands` | `get-market-history`; 큰 수집은 managed pipeline |
| trade/profit evidence | 6 | `get-period-trade-profit`, `get-overseas-period-profit`, `get-overseas-transaction-history`, `get-overseas-order-history`, `get-order-list`, `get-order-detail` | `get-trade-ledger`, `get-performance-history`; 큰 수집은 managed pipeline |
| saved portfolio analytics | 9 | `get-portfolio-history`, `get-latest-portfolio-summary`, `get-portfolio-daily-change`, `get-portfolio-anomalies`, `get-portfolio-trend`, `get-total-asset-history`, `get-total-asset-daily-change`, `get-total-asset-trend`, `get-total-asset-allocation-history` | overview/performance/signal outcome DTOs |
| order stubs | 2 | `submit-stock-order`, `submit-overseas-stock-order` | V2에서 제거; unsupported capability |

현재 annotation 기준 21 tools는 read-only, 12 tools는 KIS 호출·cache/snapshot write가 가능한 local write,
2 tools는 non-destructive disabled stub다. 그러나 remote OAuth middleware는 endpoint 전체에 `mcp:read`만
검사하고 handler는 현재 OAuth actor/scope를 소비하지 않는다. 따라서 V2 read catalog를 기존 builder에
섞으면 read token과 side-effect 경계를 증명할 수 없다.

## Approved V2 budget and readiness

V2 catalog는 15 read + 1 collect + 2 journal tools로 정확히 18개다.

| Package | Tools | Implementation dependency |
| --- | --- | --- |
| current portfolio/market/trade consolidation | `get-portfolio-overview`, `get-performance-history`, `get-market-snapshot`, `get-market-history`, `get-trade-ledger` | existing V1 services와 V2 canonical query를 typed DTO로 결합 |
| V2 analytic/review foundation | `get-position-analysis`, `get-trade-thread`, `get-signal-status`, `get-journal-review-queue` | WI-022~025/028~030/033 결과와 MS-002 acceptance |
| governance read models | `get-data-catalog`, `get-data-quality`, `get-pipeline-run` | WI-040의 three approved-inactive contracts를 구현·활성화 |
| enrichment | `get-dividend-summary`, `get-fundamental-outlook`, `get-exposure-analysis` | WI-037~041 filing/dividend/macro/consensus implementation; ETF look-through는 unsupported coverage |
| commands | `run-managed-pipeline`, `upsert-trade-journal`, `revise-trade-thread` | WI-043; WI-042 public read scope에서 제외 |

이 분석은 이름만 있는 placeholder tool을 허용하지 않는다. 각 read tool은 필요한 upstream application
contract가 구현되고 quality/missing coverage를 설명할 수 있을 때만 V2 parallel catalog에 등록한다.

## OAuth boundary

- 현재 auth server 기본 allowed scopes는 `mcp:read offline_access`이고 resource server는 `/mcp`에
  `mcp:read`를 요구한다. token은 resource binding, expiry, revoke와 scope subset을 이미 검증한다.
- WI-042에서는 allowed scope를 확대하지 않는다. `mcp:read` access token에서 raw bearer를 제외한
  `actor_id`, `client_id`, normalized scopes, resource와 request ID를 request-scoped application context로
  변환한다.
- read handler와 application query 모두 `mcp:read`를 fail-closed로 확인해 adapter 우회 test를 가능하게
  한다. packaged read-model contract의 `consumer_scope=mcp-read`는 OAuth `mcp:read`에 명시적으로 매핑한다.
- `mcp:collect`와 `mcp:journal.write` 광고, consent와 per-tool authorization은 WI-043에서 별도 추가한다.
  기존 grant는 자동 확장하지 않는다. read-only token이 command를 실행하지 못하는 negative test가 필수다.
- bearer fallback과 auth-disabled mode는 V1 실험/로컬 test 경계다. V2 production contract는 OAuth다.

## Transport boundary

설치된 MCP SDK는 `streamable_http_app(json_response, stateless_http, max_request_body_size,
transport_security)`를 공식 지원한다. 현재 remote는 반환된 official ASGI app을 사용하지 않고 private
`server.session_manager.handle_request`를 직접 호출하며 두 flag가 기본 `false`이고 request body는 SDK 기본
4 MiB다.

WI-042 구현은 official app/lifespan으로 전환하고 다음 승인값을 그대로 적용한다.

- `stateless_http=true`, `json_response=true`
- exact resource Host와 `claude.ai`/`claude.com` Origin policy; ChatGPT Origin은 실제 connector 증거 없이는
  추측해 추가하지 않음
- request body maximum 4 MiB, application serialized response maximum 256 KiB
- warm request maximum 300 seconds; 60 seconds를 넘을 수 있는 collection은 synchronous read가 아니라 Job
- initial min instances 0, max instances 1; two-replica test는 WI-044 compatibility evidence이며 자동 증설 아님
- sampling, push elicitation, roots, subscription과 in-call progress는 사용하지 않음

## Application and adapter boundary

현재 `platform.GovernanceReadModel`은 raw manifest dict, arbitrary quality `details`, raw lineage refs와
`pipeline_run_summary SELECT *`를 반환하므로 WI-040 계약의 구현이 아니다. 그대로 MCP에 연결하지 않는다.

권고 implementation seam은 다음과 같다.

```text
OAuth middleware
  -> request-scoped actor/scope context
  -> V2 MCP tool: input validation and DTO serialization only
  -> application query/consumer policy
  -> fixed manifest reader or parameterized repository
  -> governed MotherDuck/KIS source policy
```

V2 builder는 V1의 global `mcp`와 `register_tools()`를 import해 복사하지 않는다. 공통 domain/service 함수는
재사용하지만 tool declaration, input bounds, response envelope와 authorization metadata는 V2가 별도로 소유한다.
Read-through가 허용된 portfolio/market query도 source policy, freshness와 observation write를 application
layer가 결정하며 adapter가 KIS retry나 fallback을 구현하지 않는다.

## Implementation gate package

MS-003 formal gate가 열린 뒤 WI-042의 다음 설계/구현은 아래 순서가 적절하다. 아직 sub-item ID는 발급하지
않는다.

1. 15 read-tool별 input DTO, output schema ref, required upstream contract와 sync/read-through policy를 동결한다.
2. request actor/scope context와 application query ports를 구현한다.
3. capability별 typed query와 256 KiB response enforcement를 구현하며 unavailable/partial을 보존한다.
4. 별도 V2 15-read catalog와 official stateless JSON transport를 구성한다.
5. local modern/legacy protocol, Host/Origin, 4 MiB body, expired/resource/wrong-scope와 raw-field leakage를 검증한다.
6. WI-043 command surface와 WI-044 actual clients가 준비되기 전 production catalog/cutover는 하지 않는다.

## Verification

- MCP surface audit: current compatibility catalog `35 tools`, order stubs disabled
- focused OAuth/MCP/package tests: `44 passed`, existing Authlib deprecation warning one
- `bash scripts/check.sh quick`: passed
- `bash scripts/check.sh full`: `443 passed`, existing Authlib deprecation warning one
- repository and installed MCP SDK read-only inspection only; no live endpoint, token, DB or provider call

## Remaining risk

- 15 read DTO의 exact field-level schemas는 upstream WI-037~041 application implementation과 함께 동결해야 한다.
- ChatGPT의 actual Origin과 stateless JSON behavior는 repository 추측이 아니라 WI-044 client smoke가 소유한다.
- current V1 read scope의 write-through behavior는 cutover 전 compatibility surface로 보존되며 V2에 상속하지 않는다.
