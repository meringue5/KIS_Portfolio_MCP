# MS-003 — Enrichment, stateless Remote MCP V2 and production cutover

> 상태: proposed
> 선행 milestone: MS-002
> machine registry: `governance/project/milestones.toml`

## Outcome

실적·consensus·배당·macro enrichment와 승인된 분석 결과를 stateless Remote MCP V2로 제공하고, dual-run과
검증을 거쳐 사용자-facing MCP SSOT 및 필수 schedule을 V2 production으로 전환한다.

## Baseline boundary

이 마일스톤은 현재 Work Item 번호를 선점하지 않는다. 시작 전 남아 있는 설계 항목을 당시 최댓값 다음
번호로 발급하고 dependency·인수·production approval gate를 기준선화한다.

- Enrichment: V2-W0406~0410, V2-W0506
- Remote MCP V2: V2-W0601~0607
- dual-run/cutover: V2-W0701~0707

## Readiness and acceptance gate

- MS-002 metric, signal, shadow와 Telegram delivery가 닫혀 있다.
- provider rights·비용·coverage와 point-in-time 조건이 승인돼 있다.
- Remote MCP tool budget, OAuth scope, stateless replica와 iPhone client compatibility가 검증된다.
- V1/V2 dual-write/read reconciliation과 rollback evidence가 있고 V2 schedule SLO가 충족된다.
- production cutover와 외부 resource 변경은 당시 승인 gate를 따른다.

## Revision log

| Version | Date | Change | Identity impact |
| --- | --- | --- | --- |
| 2026-08-28.1 | 2026-08-28 | MS-002 밖의 승인 설계에서 MS-003 경계를 최초 기준선화 | Work Item 미발급 |
