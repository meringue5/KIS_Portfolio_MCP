# KIS Open API Rate Limits

이 문서는 KIS Portfolio Service가 준수하는 한국투자증권 Open API 호출 유량 정책의 canonical 운영 문서다.

## Official Limits

한국투자증권 개발자센터의 `API 호출 유량 안내 (REST, 웹소켓) (2026.04.20 기준)`에 따르면:

| API class | Official limit |
|---|---:|
| REST, 실전투자 | 계좌(앱키)당 초당 18건 |
| REST, 모의투자 | 초당 1건 |
| 접근토큰 발급 `/oauth2/tokenP` | 초당 1건 |
| WebSocket | 계좌(앱키)당 1세션, 실시간 등록 합산 41건 |

공식 공지는 동시 호출에 100~150ms 간격을 권장한다. 서버 분산 정책에 따라 제한 이내에서도 일부 호출이
거부될 수 있으므로 재호출도 권고한다.

Sources:

- https://apiportal.koreainvestment.com/community/10000000-0000-0011-0000-000000000001/post/d0d1a83f-6f8d-4437-9700-6d26702fd989
- https://github.com/koreainvestment/open-trading-api/blob/main/examples_user/kis_auth.py

## Service Policy

모든 KIS REST 호출은 `kis_portfolio.clients.kis.request_kis`를 통과한다.

| Runtime mode | Default minimum start interval | Effective process maximum |
|---|---:|---:|
| 실전투자 | 150ms | 약 6.7건/초 |
| 모의투자 | 1초 | 1건/초 |
| 접근토큰 발급 | 1초 | 1건/초 |

실전 기본값은 공식 18건/초보다 낮고, 공식 동시 호출 권고의 상단인 150ms를 적용한다. limiter는 앱키별
최대한도를 소진하기보다 한 프로세스의 모든 KIS REST 요청을 직렬화하는 보수적인 정책이다. 아침 브리핑처럼
여러 MCP tool 요청이 동시에 들어와도 KIS 요청 시작 시각은 이 간격으로 정렬된다.

다음 응답은 rate limit으로 취급한다.

- HTTP `429`
- `EGW00201`: 공식 예제에 명시된 초당 거래건수 초과
- `EGW00215`: 2026-08-27 운영에서 확인된 원장 초당 거래건수 초과
- 오류 메시지에 `초당 거래건수` 또는 `지정 시간 내 API 호출` 포함

rate limit 응답은 1초 대기 후 한 번만 재시도한다. 두 번째도 거부되면 `KISRateLimitError`로 종료해 무한
재시도와 briefing 전체 지연을 막는다.

## Configuration

| Environment variable | Default | Purpose |
|---|---:|---|
| `KIS_REAL_API_MIN_INTERVAL_SECONDS` | `0.15` | 실전 REST 요청 시작 최소 간격 |
| `KIS_VIRTUAL_API_MIN_INTERVAL_SECONDS` | `1.0` | 모의 REST 요청 시작 최소 간격 |
| `KIS_TOKEN_MIN_INTERVAL_SECONDS` | `1.0` | 접근토큰 발급 요청 시작 최소 간격 |
| `KIS_RATE_LIMIT_RETRY_DELAY_SECONDS` | `1.0` | 유량 거부 후 단일 재시도 대기시간 |

값은 모두 0보다 큰 초 단위 숫자여야 한다. 공식 정책이 변경되면 먼저 이 문서와 기본값, 테스트를 같은
변경에서 갱신한다.

## Runtime Boundary

limiter는 Python 프로세스 단위다. Cloud Run remote는 `max-instances=1`이라 서비스 내부 요청은 함께
조절되지만, 별도 Cloud Run Job인 batch와 remote 사이에는 분산 limiter가 없다. 현재 스케줄은 주요 batch와
아침 briefing이 겹치지 않게 운영한다. 실제 중첩이 반복되면 MotherDuck lease 또는 별도 분산 rate limiter를
도입한다.
