# KIS API Capability Map

이 문서는 한국투자 공식 Open API 문서와 공식 예제 저장소를 기준으로, 이 프로젝트가 어떤 기능을
core service, MCP adapter, 데이터 파이프라인으로 승격할지 정리한다.

MCP tool 이름은 외부 인터페이스일 뿐이다. 신규 기능은 먼저 아래 capability 중 어디에 속하는지 정한 뒤,
core service 함수와 저장 정책을 설계한다.

## 승인된 V2 Public Boundary

2026-08-28 승인된 V2 public catalog는 결과 중심 18개 tool과 `mcp:read`, `mcp:collect`,
`mcp:journal.write` 세 scope를 사용한다. 주문 tool은 V2에서 제거한다. 정확한 목록, V1 35개 tool migration
mapping과 compatibility gate는 [V2 Architecture Delta Review](./design/v2-architecture-delta-review.md)가
소유한다. V1 이름은 migration mapping에서만 사용하며 현재 public catalog나 recovery target이 아니다.

## Source Of Truth

- 한국투자 Open API 문서: https://apiportal.koreainvestment.com/apiservice-summary
- 한국투자 공식 예제 저장소: https://github.com/koreainvestment/open-trading-api
- 종목정보 예제: https://github.com/koreainvestment/open-trading-api/tree/main/stocks_info
- 호출 유량 계약: [kis-api-rate-limits.md](./kis-api-rate-limits.md)
- 장애 대응 계약: [kis-api-resilience.md](./kis-api-resilience.md)

## Capability Groups

| Group | Scope | Current Status | Direction |
|-------|-------|----------------|-----------|
| Auth | MCP OAuth와 KIS access-token state | OAuth auth/Remote 분리, Firestore digest/ciphertext state | quarterly access/rotation review |
| Account | 국내·연금·해외 잔고와 예수금 | managed collection + `get-portfolio-overview` | 품질·누락을 fail closed로 유지 |
| Overseas Account | 해외 잔고·거래·현금 사실 | Silver ledger와 stored read model | source coverage를 계약 단위로 확장 |
| Order | 국내/해외 주문조회와 체결 이력 | 거래 원장 조회만 제공; live order tool 없음 | 별도 confirmation/audit 승인 전 확장 금지 |
| Market Data | 국내/해외 가격과 환율 이력 | stored snapshot/history read model | point-in-time 품질과 revision 보강 |
| Master Data | 국내/해외 종목·분류 metadata | versioned instrument/master/override 구현 | exact source evidence 유지 |
| Analytics | 총자산, 성과, 노출, 배당, 전망, 신호 | V2 Gold/Remote read model 구현 | metric별 quality/lineage 유지 |
| Realtime | websocket 실시간 시세/체결통보 | 현재 제품 baseline 아님 | 새 요구/비용/권한 intake 필요 |
| Remote Access | stateless Streamable HTTP MCP | OAuth Remote V2 production | 안정 URL과 18-tool contract 유지 |

## Future capability intake

새 endpoint, realtime, provider 또는 order capability는 이 문서의 미완료 목록이 아니다. 사용자 요구를 새
Work Item으로 접수하고 source rights, 호출예산, natural key, quality/lineage, OAuth scope와 public tool 영향을
승인받은 뒤 추가한다. 기존 18-tool 이름을 V1 alias로 다시 넓히지 않는다.

## Adapter Policy

Core service는 MCP를 몰라야 한다.

```text
KIS API docs/examples
        ↓
kis_portfolio.services / kis_portfolio.clients
        ↓
repositories / warehouse / analytics
        ↓
adapters: OAuth Remote MCP, batch jobs, compatibility diagnostics, future backend HTTP API
```

현재 production public MCP는 `src/kis_portfolio/remote.py`의 OAuth transport와
`src/kis_portfolio/adapters/mcp/v2.py`의 18-tool adapter이며, application logic은 `services/`와
`application/`에 둔다. `src/kis_portfolio/adapters/mcp/server.py`는 V1 migration contract 검증용 내부
fixture surface일 뿐 production entrypoint가 아니다.

Future backend API는 별도 public surface가 필요해지는 시점에 `adapters/http` 후보로 둔다. ETL orchestration은
현재 `adapters/batch + services` 조합을 유지하고, 독립 ETL workflow가 여러 개로 늘어나면 `pipelines`
패키지를 재검토한다. 이번 경량 리팩터에서는 `pipelines` 패키지를 만들지 않는다.

## Repository Identity

이 저장소는 `migusdn/KIS_MCP_Server` fork에서 출발했지만, 신규 설계 기준은 KIS 공식 API와 개인
포트폴리오 서비스 요구사항이다.

현재 identity는 Python package `kis_portfolio`, production commands `kis-portfolio-auth`와
`kis-portfolio-remote`, client-visible connector `KIS Portfolio`다. `kis-portfolio-mcp`는 retired diagnostic이며
public product name이 아니다. Fork attribution과 Git history는 보존한다.
