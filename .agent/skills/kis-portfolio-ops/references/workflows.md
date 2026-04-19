# KIS Portfolio Workflow Notes

## 전체 계좌 현황

1. `get-latest-portfolio-summary`로 MotherDuck 최신 스냅샷을 합산한다.
2. `get-portfolio-daily-change`로 최근 일별 변화와 전일 대비 값을 확인한다.
3. 스냅샷이 없거나 오래되었으면 계좌별 `inquery-balance`를 실행해 live KIS API 값을 적재한다.
4. 다시 `get-latest-portfolio-summary`를 호출해 저장된 값을 확인한다.

## 계좌별 분석

1. 사용자가 계좌 종류를 말하면 `ria`, `isa`, `brokerage`, `irp`, `pension` 라벨로 매핑한다.
2. 계좌번호를 직접 말하지 않아도 되는 응답에서는 계좌번호 전체를 노출하지 않는다.
3. 장기 추세는 `get-portfolio-trend`, 급격한 변화는 `get-portfolio-anomalies`를 사용한다.

## 조회와 주문의 경계

- 포트폴리오 요약, 리밸런싱 아이디어, 위험 점검은 모두 조회-only 작업으로 처리한다.
- 주문 tool은 사용자가 명시적으로 주문 실행을 요청하고, 별도 안전장치가 활성화된 경우에만 고려한다.
- remote MCP 배포에서는 주문 tool을 기본 비활성으로 둔다.

## 데이터 출처 표기

- `inquery-balance`: live KIS API 호출이며 호출 시점 스냅샷이 DB에 저장된다.
- `get-latest-portfolio-summary`: MotherDuck DB-only 집계다.
- `get-portfolio-daily-change`: MotherDuck DB-only 일별 대표 스냅샷 집계다.
- `get-portfolio-history`: MotherDuck DB-only raw snapshot 이력이다.
