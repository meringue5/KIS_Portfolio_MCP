# KIS API Resilience

이 문서는 KIS Portfolio Service의 REST 장애 대응 계약을 정의한다. 호출 유량 자체의 공식 한도와 기본
간격은 [KIS Open API Rate Limits](./kis-api-rate-limits.md)가 관리한다.

## Request Path

OAuth token 발급을 제외한 모든 KIS 업무 REST 호출은 `kis_portfolio.clients.kis.request_kis`를 통과한다.
token 발급은 keyed refresh lock과 1초 pacing, 별도 bounded retry를 가진 auth 전용 경로를 유지한다.

```text
service request policy
  -> total deadline
  -> endpoint circuit breaker
  -> bounded process queue / in-flight bulkhead
  -> rate interval and shared adaptive cooldown
  -> HTTP attempt timeout
  -> response classification and bounded retry
  -> service-owned fresh, partial, or stale response
```

MCP adapter는 이 정책을 재구현하지 않는다. endpoint, auth header, HTTP 동작은 `clients/`, 저장과 stale
fallback의 업무 의미는 `services/`, 공개 wrapper metadata는 `adapters/mcp`가 소유한다.

## Request Policies

| Policy | Attempts | Attempt timeout | Total deadline | Use |
|---|---:|---:|---:|---|
| `quote` | 2 | 5s | 8s | 현재가, 호가 |
| `account` | 2 | 10s | 15s | 잔고, 예수금 |
| `history` | 3 | 20s | 60s | 가격, 주문, 손익, pagination |
| `batch` | 4 | 30s | 120s | 명시적인 batch/backfill 호출 |

GET/HEAD/OPTIONS만 기본적으로 재시도한다. hash-key처럼 안전성이 확인된 POST는 호출부가
`retry_safe=True`를 명시한다. 국내/해외 주문 POST는 자동 재시도하지 않으며 public 주문 tool은 계속
disabled stub이다.

일시 장애는 connection/transport timeout과 HTTP 500/502/503/504다. full-jitter exponential backoff를
사용하며 total deadline을 넘겨 재시도하지 않는다. KIS 업무 오류와 일반 4xx는 service가 처리하고 자동
재시도하지 않는다.

## Load Shedding

실전 REST는 기본 3개, 모의 REST는 기본 1개의 in-flight 요청만 허용한다. 대기자는 기본 50개로 제한하고
policy별 queue timeout을 넘으면 `KISBulkheadRejectedError`로 종료한다. rate limit 거부는 같은 process의
REST scope 전체에 cooldown으로 전파한다.

endpoint path별 transient failure가 기본 30초 안에 5회 누적되면 circuit을 20초 연다. cooldown 이후에는
probe 하나만 허용하고 성공하면 닫는다. rate limit, 잘못된 파라미터와 인증 만료는 circuit failure에
포함하지 않는다.

## Freshness Contract

캐시는 upstream 장애를 숨기는 용도가 아니다.

- live balance는 기본적으로 실패를 반환한다.
- 호출자가 `allow_stale_on_error=true`를 명시한 경우에만 최신 저장 잔고를 반환한다.
- stale 응답에는 `status=stale`, `source=motherduck_cache`, `as_of`, `stale_age_seconds`, upstream error type을 포함한다.
- 전체 계좌 refresh는 계좌별 성공/실패를 보존하며 transient 실패 계좌에 저장 snapshot metadata가 있으면
  `fallback`으로 알린다.
- 총자산 overview는 일부 feeder 실패 시 `partial_error`를 유지하며 저장 데이터를 최신 조회처럼 표시하지 않는다.

## Configuration

| Variable | Default |
|---|---:|
| `KIS_REAL_API_MAX_IN_FLIGHT` | `3` |
| `KIS_VIRTUAL_API_MAX_IN_FLIGHT` | `1` |
| `KIS_API_MAX_QUEUE_SIZE` | `50` |
| `KIS_RATE_LIMIT_MAX_COOLDOWN_SECONDS` | `10.0` |
| `KIS_CIRCUIT_FAILURE_THRESHOLD` | `5` |
| `KIS_CIRCUIT_WINDOW_SECONDS` | `30.0` |
| `KIS_CIRCUIT_OPEN_SECONDS` | `20.0` |

모든 값은 양수여야 하며 remote service와 batch Job에 함께 주입한다. 상태는 process-local이다. 현재
remote `max-instances=1`과 batch schedule 분리로 운영하고, 실제 process 간 충돌이 반복 관측될 때 전용
KIS gateway나 external token bucket을 도입한다. MotherDuck을 매 요청 distributed lock으로 사용하지 않는다.

## Observability

요청 로그에는 endpoint path, policy, attempt count, queue wait, 전체 latency, HTTP status, KIS message code,
cooldown, circuit 전환과 fallback 여부를 남긴다. token, app secret과 원문 계좌번호는 남기지 않는다.
