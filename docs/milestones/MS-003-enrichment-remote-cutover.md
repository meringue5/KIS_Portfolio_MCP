# MS-003 — Enrichment, stateless Remote MCP V2 and production cutover

> 상태: proposed
> 선행 milestone: MS-002
> machine registry: `governance/project/milestones.toml`

## Outcome

실적·consensus·배당·macro enrichment와 승인된 분석 결과를 stateless Remote MCP V2로 제공하고, dual-run과
검증을 거쳐 사용자-facing MCP SSOT 및 필수 schedule을 V2 production으로 전환한다.

## Baseline

| Sequence | Work Item | Design refs | Depends on | 상태 / 결과 |
| ---: | --- | --- | --- | --- |
| 1 | WI-035 production operations/cost/release guardrails | V2-W0002/0003/0106 | WI-012 | proposed; S01 research-only closed |
| 2 | WI-037 filing actual/fundamental pipeline | V2-W0406 | WI-012, WI-017 | proposed; S01~S03 closed; ADR-025 and 7 contracts approved but inactive; implementation/formal gate unchanged |
| 3 | WI-038 dividend event ledger | V2-W0407 | WI-020, WI-021, WI-037 | proposed; S01 closed; S02 owner-decision-ready; ADR-026/contract adoption and formal gate pending |
| 4 | WI-039 macro profile pipeline | V2-W0408 | WI-012 | proposed; S01 research-only closed; contract hardening gate |
| 5 | WI-040 catalog/quality read model | V2-W0410 | WI-012, WI-019, WI-020 | proposed; S01 research-only closed; contract hardening gate |
| 6 | WI-041 consensus forward outlook | V2-W0506 | WI-037 | proposed; S01/S02 closed; S03 rejected; S04 closed with four approved-but-inactive Alpha contracts; historical PIT gap remains |
| 7 | WI-042 stateless Remote MCP V2 read surface | V2-W0601~0603 | WI-030, WI-040, WI-041 | proposed |
| 8 | WI-043 Remote MCP managed commands | V2-W0604/0605 | WI-024, WI-042 | proposed |
| 9 | WI-044 Remote MCP client compatibility | V2-W0606/0607 | WI-042, WI-043 | proposed |
| 10 | WI-045 V1/V2 dual-run readiness | V2-W0701/0702/0703/0706 | WI-035, WI-044 | proposed |
| 11 | WI-046 Remote MCP V2 production cutover | V2-W0704/0705/0707 | WI-045 | proposed; production gate |

V2-W0409의 build-once production release는 WI-012에서 이미 완료됐으며 이 milestone의 잔여 범위가 아니다.

## Readiness and acceptance gate

- MS-002 metric, signal, shadow와 Telegram delivery가 닫혀 있다.
- 초기 V2에 포함된 provider의 rights·비용·coverage와 point-in-time 조건이 승인돼 있다. ETF provider와
  look-through는 DEC-049에 따라 이 gate에서 제외되며 unsupported coverage로 남는다.
- Remote MCP tool budget, OAuth scope, stateless replica와 iPhone client compatibility가 검증된다.
- V1/V2 dual-write/read reconciliation과 rollback evidence가 있고 V2 schedule SLO가 충족된다.
- production cutover와 외부 resource 변경은 당시 승인 gate를 따른다.

## Revision log

| Version | Date | Change | Identity impact |
| --- | --- | --- | --- |
| 2026-09-02.5 | 2026-09-02 | WI-038-S02 froze the proposed action/entitlement/receipt-link, cash SSOT, PIT, coverage, migration, call-budget and capacity design | S02 ready for owner decision; no contract adoption, implementation, source, activation, parent or milestone status change |
| 2026-09-02.4 | 2026-09-02 | WI-037-S03 adopted ADR-025, requirements/system-design clarification and seven approved-inactive filing contracts with shared implementation constraint | S03 closed; no implementation, source, activation, parent or milestone status change |
| 2026-09-02.3 | 2026-09-02 | Owner approved WI-037-S02 package and shared implementation constraint; WI-037-S03 appended for canonical ADR/DGH adoption | S02 closed, S03 in progress; no code, DDL, source, activation, parent or milestone status change |
| 2026-09-02.2 | 2026-09-02 | WI-037-S02 completed the proposed ADR-025 and seven-contract filing design with additive migration, dual as-of semantics, bounded source budgets and rollback gates | S02 ready for owner decision; no contract lifecycle, parent or milestone status change |
| 2026-09-02.1 | 2026-09-02 | WI-037-S02 appended to freeze filing issuer identity, Bronze/Silver, correction, point-in-time, raw-object and call-budget contracts before implementation | parent WI and milestone status unchanged; implementation, source call, DDL and activation excluded |
| 2026-09-01.12 | 2026-09-01 | Owner approved the bounded Alpha personal-use contract and residual-risk package; source, dedicated collection, normalized dataset and pipeline are approved but inactive | S04 closed; mixed consensus collection stays proposed; no activation or parent/milestone status change |
| 2026-09-01.11 | 2026-09-01 | WI-041-S04 proposed a secondary Alpha source, forward-only normalized dataset and bounded pipeline with a three-year capacity/risk package | S04 ready for owner contract decision; no activation or parent/milestone status change |
| 2026-09-01.10 | 2026-09-01 | WI-041-S04 appended to correct S03's over-broad rights gate through proportionate published-license, normalized-retention and no-redistribution contract review | S03 history preserved; parent WI and milestone status unchanged |
| 2026-09-01.9 | 2026-09-01 | Owner skipped the low-value Alpha rights inquiry; no message was sent and S03 closed rejected with production/raw-retention gates fail-closed | parent WI and milestone status unchanged; future reconsideration needs a new sub-item |
| 2026-09-01.8 | 2026-09-01 | WI-041-S03 stored a research-only Alpha key and completed four-call sanitized sampling; 1/4 coverage and historical PIT gates failed, rights inquiry remains pending | parent WI and milestone status unchanged |
| 2026-09-01.7 | 2026-09-01 | Owner approved Alpha Vantage free account, personal EULA and credential issuance; WI-041-S03 opened with paid, production and raw-payload boundaries unchanged | parent WI and milestone status unchanged |
| 2026-09-01.6 | 2026-09-01 | WI-041-S02 closed with bounded KIS evidence and Alpha demo denial; WI-041-S03 appended for owner credential and rights evidence | parent WI and milestone status unchanged |
| 2026-09-01.5 | 2026-09-01 | WI-041-S02 opened for bounded domestic KIS and U.S. Alpha Vantage schema/rights sampling | parent WI and milestone status unchanged |
| 2026-09-01.4 | 2026-09-01 | WI-041-S01 recorded provider rights, cost, PIT semantics and retained-replay contract gaps | parent WI and milestone status unchanged |
| 2026-09-01.3 | 2026-09-01 | WI-038-S01 recorded state identity, receipt reconciliation and account/source coverage gaps | parent WI and milestone status unchanged |
| 2026-09-01.2 | 2026-09-01 | WI-039-S01 recorded series-scope, vintage identity, rights and call-budget gaps | parent WI and milestone status unchanged |
| 2026-09-01.1 | 2026-09-01 | WI-040-S01 recorded catalog/quality sensitivity, false-green and Control dataset contract gaps | parent WI and milestone status unchanged |
| 2026-08-31.2 | 2026-08-31 | WI-037-S01 recorded official-source, live identity coverage and point-in-time contract gaps | parent WI and milestone status unchanged |
| 2026-08-31.1 | 2026-08-31 | WI-037-S01 filing source and point-in-time pre-research started without opening the formal gate | parent WI and milestone status unchanged |
| 2026-08-30.2 | 2026-08-30 | WI-035-S01 recorded live inventory, cost-observability limits and fail-closed cleanup inputs | parent WI and milestone status unchanged |
| 2026-08-30.1 | 2026-08-30 | WI-035-S01 read-only pre-research checkpoint started without opening the formal gate | parent WI and milestone status unchanged |
| 2026-08-28.2 | 2026-08-28 | 잔여 delivery를 WI-035/037~046으로 배정하고 완료된 V2-W0409를 제외 | 신규 WI append; 기존 ID 불변 |
| 2026-08-28.1 | 2026-08-28 | MS-002 밖의 승인 설계에서 MS-003 경계를 최초 기준선화 | Work Item 미발급 |
