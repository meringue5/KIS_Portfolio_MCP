# KIS API Capability Map

이 문서는 한국투자 공식 Open API 문서와 공식 예제 저장소를 기준으로, 이 프로젝트가 어떤 기능을
core service, MCP adapter, 데이터 파이프라인으로 승격할지 정리한다.

MCP tool 이름은 외부 인터페이스일 뿐이다. 신규 기능은 먼저 아래 capability 중 어디에 속하는지 정한 뒤,
core service 함수와 저장 정책을 설계한다.

## Source Of Truth

- 한국투자 Open API 문서: https://apiportal.koreainvestment.com/apiservice-summary
- 한국투자 공식 예제 저장소: https://github.com/koreainvestment/open-trading-api
- 종목정보 예제: https://github.com/koreainvestment/open-trading-api/tree/main/stocks_info

## Capability Groups

| Group | Scope | Current Status | Direction |
|-------|-------|----------------|-----------|
| Auth | 접근토큰, 토큰 폐기, Hashkey, websocket key | 토큰 발급/캐시/상태 조회 구현 | token audit event 추가 |
| Account | 국내 잔고, 퇴직연금 잔고, 예수금, 매수가능, 기간 손익 | 일부 구현, 오케스트레이터 v1 구현 | 포트폴리오 서비스의 우선순위 1 |
| Overseas Account | 해외 잔고, 해외 예수금, 해외 기간 손익 | legacy MCP tool 구현 | 서비스 계층으로 분리 |
| Order | 국내/해외 주문, 정정취소, 주문조회 | 조회 일부 구현, 주문은 safety gate | 기본 비활성, 별도 confirmation/audit 전까지 확장 금지 |
| Market Data | 국내/해외 현재가, 호가, 일/분봉 | 일부 구현 및 가격 이력 저장 | 가격 서비스와 DB cache 분리 |
| Master Data | 국내/해외 종목코드, 업종, 테마, 회원사, 상품 메타데이터 | 미구현 | 공식 `stocks_info` 예제를 ingestion 후보로 사용 |
| Analytics | 최신 합산, 일별 변화, 추세, 이상치, 볼린저 밴드 | 일부 구현 | raw/curated 분리 유지 |
| Realtime | websocket 실시간 시세/체결통보 | 미구현 | 원격 배포와 auth 설계 이후 검토 |
| Remote Access | Streamable HTTP MCP, web/backend hosting | bearer baseline 구현 | read-only remote와 OAuth/OIDC 검토 |

## Near-Term API Priorities

1. Account
   - `get-account-balance`
   - `refresh-all-account-snapshots`
   - 투자계좌자산현황조회 후보 검토
   - 기간별손익/매매손익 API의 국내/해외 응답 정규화

2. Auth
   - token audit event schema
   - 계좌별 token refresh reason 기록
   - 토큰 원문 비저장 원칙 유지

3. Master Data
   - KOSPI/KOSDAQ/KONEX/overseas master file ingestion 설계
   - 보유종목 enrichment용 symbol dimension table 설계

4. Analytics
   - portfolio aggregate service 분리
   - daily/minute curated view 확장
   - 계좌별/자산군별/통화별 요약

## Adapter Policy

Core service는 MCP를 몰라야 한다.

```text
KIS API docs/examples
        ↓
kis_portfolio.services / kis_portfolio.clients
        ↓
repositories / warehouse / analytics
        ↓
adapters: local MCP, remote MCP, batch jobs, future web API
```

현재 public MCP adapter는 `src/kis_portfolio/adapters/mcp/server.py`이며, KIS 호출 로직은
`services/` 아래로 이동하는 중이다.

## Repository Identity

이 저장소는 `migusdn/KIS_MCP_Server` fork에서 출발했지만, 신규 설계 기준은 KIS 공식 API와 개인
포트폴리오 서비스 요구사항이다.

권장 단계:

1. 현재 저장소와 history를 유지하며 구조 전환을 진행한다.
2. README/SPEC에서 fork attribution은 유지하고, 프로젝트 설명은 포트폴리오 서비스 중심으로 변경한다.
3. Python package는 `kis_portfolio`, public MCP는 `kis-portfolio-mcp`로 사용한다.
4. upstream 병합 가치가 낮아진 시점에 GitHub repository rename을 검토한다.
