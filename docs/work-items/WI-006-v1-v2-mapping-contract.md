---
id: WI-006
title: Define the executable V1 to V2 mapping contract
status: closed
type: change
owner: owner
decision_refs: ADR-021, ADR-023, V2-ADR-006, V2-ADR-008, V2-ADR-016
requirement_refs: DEC-003, DEC-005, DEC-010, DEC-044, DEC-045, DGOV-005..DGOV-007
architecture_impact: none; implements the approved parallel-schema migration decision
data_impact: classifies every V1 managed object and known drift row for copy, transform, rebuild, reference-only, defer, or reject
security_impact: excludes security and token payloads from the analytics migration
cost_impact: read-only profiling and local artifacts; negligible compute cost
---

# WI-006 — Define the executable V1 to V2 mapping contract

## Problem and evidence

V2 physical objects exist beside the preserved V1 `main` schema, but there is no complete source-column-to-target-field
contract. The 2026-08-28 V1 backup contains about 7,876 rows across populated managed tables. Known unmanaged drift and
extra quality columns must be classified explicitly rather than silently adopted.

## Classification and contract

- 초기 분류: `change`
- 비교한 요구사항/ADR/catalog: DEC-045, V2-ADR-006/008/016, `docs/data-catalog.md`, V2-W0308
- 계약 미달인지 계약 변경인지: 승인된 parallel migration을 실행 가능하게 구체화한다. V2 grain/key 변경은 제외한다.
- 승인 필요 여부: mapping 문서·read-only profiling은 승인됨. source/target 계약 변경 발견 시 별도 owner 승인.

## Scope

- 포함: 모든 V1 managed table/view와 known live drift의 disposition, column transform, identity/key, timestamp,
  currency/decimal, provenance, quality flag, reject reason, replay order와 backfill dependency matrix.
- 제외: live V2 row write, V1 mutation, security/token/OAuth state migration, source API 호출, consumer cutover.

## Acceptance criteria

- [ ] 모든 V1 object가 `copy/transform/rebuild/reference-only/defer/reject` 중 하나와 근거를 가진다.
- [ ] populated V1 row 약 7,876개가 target, deliberate exclusion 또는 reject rule에 추적된다.
- [ ] account/instrument identity, natural key, UTC/timezone, KRW/foreign currency와 decimal rounding이 명시된다.
- [ ] `cash_flow`, `trade_journal`, `asset_return_daily` 및 추가 quality column의 처리 결정이 명시된다.
- [ ] executable mapping fixture와 mapping-contract validator가 schema drift·누락 field를 실패시킨다.
- [ ] WI-007에서 사용할 reconciliation rule, tolerance와 severity가 확정된다.

## Change impact

- Architecture: 승인된 parallel schema 경계를 변경하지 않는다.
- Data/schema/backup: read-only source profiling; schema/row write 없음.
- Security/privacy: account identifier는 내부 stable id로만 매핑하고 보고서에는 원문 계좌번호를 쓰지 않는다.
- MCP/API compatibility: 없음.
- Deployment/rollback: 배포 없음; 문서·fixture revert 가능.
- Cost/SLO: MotherDuck read와 local validation뿐이며 예상 과금은 미미하다.

## Plan

1. live inventory와 V1 backup manifest를 고정한다.
2. object/column/key/time/money mapping matrix를 작성한다.
3. known drift를 adopt/defer/reject로 판정한다.
4. executable fixture와 validator를 만들고 WI-007 입력 manifest를 생성한다.

## Estimate

- agent/개발 작업시간: 4~6시간
- DB 실행시간: read-only profiling 및 validator 합계 5분 이내 예상
- owner 검토시간: 30~60분
- 일정 위험: drift 의미가 불명확하거나 V2 grain 변경이 필요하면 2~4시간 추가

## Evidence

- 명령/테스트: `governance/migrations/v1-v2-history-v1.toml`; mapping validator와
  `tests/test_v1_v2_history_migration.py` 통과
- 운영 증거: `docs/operations/motherduck-v2-foundation-2026-08.md`의 preflight와 backup manifest

## Closeout

- 결과: 20개 V1 managed/drift object를 transform 3, reference-only 1, defer 16으로 분류하고 executable TOML 계약과 validator를 완료했다.
- 남은 위험: mapping 과정에서 새 requirement/ADR가 필요할 수 있음
- 후속 Work Item: WI-007
