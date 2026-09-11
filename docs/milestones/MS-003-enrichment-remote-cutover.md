# MS-003 — Enrichment, stateless Remote MCP V2 and production cutover

> 상태: in_progress; continuous isolated overlap
> 선행 milestone: MS-002
> machine registry: `governance/project/milestones.toml`

## Outcome

실적·consensus·배당·macro enrichment와 승인된 분석 결과를 stateless Remote MCP V2로 제공하고, dual-run과
검증을 거쳐 사용자-facing MCP SSOT 및 필수 schedule을 V2 production으로 전환한다.

## Baseline

| Sequence | Work Item | Design refs | Depends on | 상태 / 결과 |
| ---: | --- | --- | --- | --- |
| 1 | WI-035 production operations/cost/release guardrails | V2-W0002/0003/0106 | WI-012 | verified; isolated contracts/fixtures/local dry-run only; production inventory and cleanup apply remain gated |
| 2 | WI-037 filing actual/fundamental pipeline | V2-W0406 | WI-012, WI-017 | verified; additive 0014, dual-clock revision repository, safe fixtures, budget/quality and fresh restore complete; contracts approved-inactive, production effects none |
| 3 | WI-038 dividend event ledger | V2-W0407 | WI-020, WI-021, WI-037 | verified; additive 0015, action/entitlement/reversible receipt-link repository and fresh local restore; contracts inactive, production effects none |
| 4 | WI-039 macro profile pipeline | V2-W0408 | WI-012 | verified; exact 17-series registry, additive 0016, heterogeneous PIT revisions, five metrics, guardrails and fresh local restore; contracts inactive and production effects none |
| 5 | WI-040 catalog/quality read model | V2-W0410 | WI-012, WI-019, WI-020 | verified; internal DTO/query and synthetic local evidence complete; contracts remain inactive and public MCP/production effects stay gated |
| 6 | WI-041 consensus forward outlook | V2-W0506 | WI-037 | verified; exact inactive Alpha bundle, additive 0017, normalized forward-only snapshots, fixture guards and fresh local restore; historical PIT and production effects remain prohibited |
| 7 | WI-042 stateless Remote MCP V2 read surface | V2-W0601~0603 | WI-030, WI-040, WI-041 | verified; exact inactive 15-read builder, typed DTO/query port, scope/resource and safe envelope enforcement, official stateless JSON transport plus local replica-equivalent fixtures; V1/public production unchanged |
| 8 | WI-043 Remote MCP managed commands | V2-W0604/0605 | WI-024, WI-042 | verified; exact inactive 18-tool catalog, fixed-job async run ID, split command scopes, owner-subject/idempotency/concurrency and append-only journal/thread revision fixtures; production effects none |
| 9 | WI-044 Remote MCP client compatibility | V2-W0606/0607 | WI-042, WI-043 | in progress; recorded client-profile protocol fixtures and exact migration/unsupported guide only; actual connector/public smoke remains gated |
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

## Implementation and production gates

- implementation gate: MS-002가 최소 `stabilizing`이면 MS-003은 `in_progress`로 전환한다. WI-046 cutover를
  제외한 검토된 Work Item은 dependency가 최소 `verified`이고 현재 phase가 `execution_scope: isolated`,
  `production_effects: none`인 동안 단일 `in_progress` 제한 아래 repository implementation·fixture·local
  또는 inactive verification을 연속 수행해 `verified`까지 전진할 수 있다. WI-035와 WI-040은 이미
  `verified`이며 WI-039, WI-041, WI-042와 WI-043도 isolated verification을 마쳤다. 다음 dependency-ready
  isolated 구현 단위인 WI-044가 현재 활성화됐다.
- production gate: MS-002가 `closed`여야 migration, live DB write, external source activation, credential/IAM,
  Cloud Run/Scheduler, public MCP surface와 traffic cutover를 수행할 수 있다.
- 안정화 중 발견된 rollback은 dependency를 역전시키지 않고 새 corrective Work Item의 append-only feedback
  관계로 기록한다.

## Revision log

| Version | Date | Change | Identity impact |
| --- | --- | --- | --- |
| 2026-09-11.32 | 2026-09-11 | Activated WI-044 after WI-042/043 under continuous dependency-ready isolated overlap | recorded client-profile fixtures and exact V1-to-V2 migration guide only; no public endpoint, connector, OAuth grant, live DB/KIS, infrastructure, deployment, traffic or production effect |
| 2026-09-11.31 | 2026-09-11 | Verified WI-043 exact inactive 18-tool catalog, fixed managed-run mapping, split command auth and append-only revision/idempotency fixtures with 590 full tests | local fixture evidence only; no OAuth grant, actual Job, live DB/KIS, infrastructure, public catalog, client, deployment, traffic or production effect |
| 2026-09-11.30 | 2026-09-11 | Activated WI-043 after WI-024/042 under continuous dependency-ready isolated overlap | typed command/application ports and fixed local fixtures only; no OAuth grant, actual Job, live DB write, infrastructure, public catalog, deployment, traffic or production effect |
| 2026-09-11.29 | 2026-09-11 | Verified WI-042 exact inactive 15-read V2 catalog, typed query/envelope, application auth boundary and official stateless local transport with 575 full tests | local fixture evidence only; no OAuth grant, public endpoint, live DB/KIS, infrastructure, deployment, traffic, V1 retirement or production effect |
| 2026-09-11.28 | 2026-09-11 | Activated WI-042 after WI-030/040/041 under continuous dependency-ready isolated overlap | parallel V2 read builder, typed DTO/handler, auth context and local transport fixtures only; no OAuth grant, public endpoint, live DB/KIS, infrastructure, deployment, traffic or production effect |
| 2026-09-10.27 | 2026-09-10 | Verified WI-041 approved-inactive Alpha forward-only pipeline with strict fixtures, fetched-at revision analysis and fresh local recovery | synthetic local evidence only; no source, secret, live DB, infrastructure, schedule, MCP, Telegram, retention apply or production effect |
| 2026-09-10.26 | 2026-09-10 | Activated WI-041 after WI-039 under continuous dependency-ready isolated overlap | Alpha forward-only migration code, repository, synthetic fixtures and local recovery only; no source, secret, live DB, infrastructure, schedule, consumer or production effect |
| 2026-09-10.25 | 2026-09-10 | Verified WI-039 exact inactive macro registry, heterogeneous revision ledger, five metrics and fresh local recovery | synthetic local evidence only; no source, credential, live DB, infrastructure, schedule, public MCP, Telegram or production effect |
| 2026-09-10.24 | 2026-09-10 | Activated WI-039 after WI-038 under continuous dependency-ready isolated overlap | migration 0016 code, repository, safe fixtures and local recovery only; no source, credential, live DB, infrastructure, schedule or public effect |
| 2026-09-10.23 | 2026-09-10 | Verified WI-038 additive dividend revision ledger with 10 focused, 33 integration and 539 full tests | local fixture/migration/recovery evidence only; no source, credential, live DB, infrastructure, schedule or public effect |
| 2026-09-10.22 | 2026-09-10 | Activated WI-038 after WI-037 under continuous dependency-ready isolated overlap | additive 0015, repository, fixtures and local recovery only; no source, credential, live DB, infrastructure, schedule or public effect |
| 2026-09-10.21 | 2026-09-10 | Verified WI-037 additive filing revision pipeline with 15 focused and 532 full tests | local fixture/migration/recovery evidence only; no source, credential, live DB, infrastructure, schedule or public effect |
| 2026-09-10.20 | 2026-09-10 | Activated WI-037 after WI-057 under continuous dependency-ready isolated overlap | migration code, repository, safe fixtures and local verification only; no source/live DB/credential/schedule/public effect |
| 2026-09-10.19 | 2026-09-10 | Corrected the implementation gate to continuous dependency-ordered isolated overlap and moved MS-003 to in progress | WI identities and dependencies unchanged; production gate and cutover exclusion preserved |
| 2026-09-09.18 | 2026-09-09 | Verified WI-040 six-kind catalog and bounded fail-closed Control read models with 12 focused and 518 full tests | synthetic local evidence only; no DDL, live DB, source, credential, infrastructure, schedule, public MCP or production effect |
| 2026-09-09.17 | 2026-09-09 | Activated WI-040 under the allowlisted isolated overlap gate | repository DTO/query/fixture/local verification only; no production effects |
| 2026-09-09.16 | 2026-09-09 | Verified WI-035 inventory, cost, release/rollback and cleanup dry-run contracts with 493 full tests | no production capture/apply/effects; production gate unchanged |
| 2026-09-09.15 | 2026-09-09 | Activated WI-035 under the allowlisted isolated overlap gate | repository implementation/fixtures/local verification only; no production effects |
| 2026-09-08.14 | 2026-09-08 | WI-056에 따라 milestone을 ready로 열고 WI-035/WI-040 isolated overlap과 production close gate를 분리 | ID/dependency 불변; production 권한 없음 |
| 2026-09-02.13 | 2026-09-02 | WI-042-S01 completed exact 35-to-18 grouping and froze research inputs for parallel V2 catalog, request actor, scope and official stateless JSON transport | S01 closed as final planned MS-003 pre-research before MS-002 close; no implementation, OAuth grant, public catalog, client, deployment, parent or milestone status change |
| 2026-09-02.12 | 2026-09-02 | WI-042-S01 opened for research-only V1 tool, OAuth, V2 budget and thin read-adapter audit | parent, milestone and implementation gate unchanged; no public MCP, OAuth, code, deployment or runtime change |
| 2026-09-02.11 | 2026-09-02 | Owner approved all WI-040-S02 recommendations; S03 adopted six Control dataset and three inactive read-model contracts plus bounded fail-closed checker rules | S03 closed; 161 DGH contracts and full 443 pass; no DTO, DDL, DB, source, credential, infrastructure, schedule, MCP activation, parent or milestone status change |
| 2026-09-02.10 | 2026-09-02 | WI-040-S02 froze DB-only authority, six Control evidence datasets, three typed read models, sensitivity suppression, query bounds and fail-closed status composition | S02 ready for owner decision; WI-042-S01 identified as next useful research after adoption; no contract lifecycle, code, DDL, DB, MCP, infrastructure or milestone status change |
| 2026-09-02.9 | 2026-09-02 | WI-039-S04 adopted ADR-027, requirements/system-design clarification, exact 17-series registry, Gold snapshot and five transparent metrics | S04 closed; 152 DGH contracts; no DDL, DB, credential, infrastructure, source call, schedule, deployment, MCP activation, parent or milestone status change |
| 2026-09-02.8 | 2026-09-02 | Owner approved WI-039-S02 and S03 verified five exact ECOS identities and observed-content time boundary within the 16-call ceiling | S02/S03 closed; S04 adoption pending; no code, DDL, DB, credential, infrastructure, schedule, activation, parent or milestone status change |
| 2026-09-02.7 | 2026-09-02 | WI-039-S02 froze the proposed exact profile, FRED/VIX transport, heterogeneous revision, series registry, metrics, migration, rights, budget and capacity design | S02 ready for owner decision; S03 exact ECOS evidence and S04 adoption remain; no implementation, source, activation, parent or milestone status change |
| 2026-09-02.6 | 2026-09-02 | Owner approved WI-038-S02 and WI-038-S03 adopted ADR-026, requirements/system-design clarification and eight approved-inactive dividend contract deltas | S02/S03 closed; no implementation, DDL, source, activation, parent or milestone status change |
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
