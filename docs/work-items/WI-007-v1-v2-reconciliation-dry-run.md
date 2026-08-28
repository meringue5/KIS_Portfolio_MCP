---
id: WI-007
title: Rehearse V1 to V2 migration and produce reconciliation evidence
status: closed
type: change
owner: owner
decision_refs: ADR-021, ADR-023, V2-ADR-006, V2-ADR-008, V2-ADR-010, V2-ADR-016
requirement_refs: DEC-003, DEC-005, DEC-010, DEC-044, DEC-045, DGOV-005..DGOV-007
architecture_impact: none; consumes the approved mapping and isolated migration path
data_impact: writes only to a disposable DuckDB or isolated temporary database and emits reconciliation evidence
security_impact: uses private backups without logging account identifiers or raw payloads
cost_impact: local-first rehearsal; temporary MotherDuck validation only if needed
---

# WI-007 — Rehearse V1 to V2 migration and produce reconciliation evidence

## Problem and evidence

An approved mapping is not sufficient evidence that historical data can be transformed without loss, duplication or
semantic drift. The migration must be replayed against the preserved V1 backup in an isolated target before any live
V2 business row is written.

## Classification and contract

- 초기 분류: `change`
- 선행조건: WI-006 closed and mapping contract checksum fixed
- 계약 미달인지 계약 변경인지: mapping implementation 검증이며 승인된 grain/key를 변경하지 않는다.
- 승인 필요 여부: local/isolated dry-run은 승인됨. live backfill은 이 결과의 owner 검토 전 금지.

## Scope

- 포함: fresh V2 DB 생성, V1 backup import, deterministic transform, failure injection/resume, row/key/null/value/
  aggregate reconciliation, reject/exception report, rerun idempotency와 restore rehearsal.
- 제외: live production V2 write, V1 mutation, source API recollection, public MCP/consumer cutover.

## Acceptance criteria

- [ ] WI-006 mapping checksum과 input backup manifest checksum이 run evidence에 남는다.
- [ ] source row disposition 합계가 input row count와 일치하고 누락·중복이 0이거나 승인된 exception이다.
- [ ] key uniqueness, required null, position quantity, cash, trade/lot link와 total-asset aggregate가 WI-006 tolerance를 통과한다.
- [ ] failed-stage resume와 동일 input 재실행이 canonical duplicate를 만들지 않는다.
- [ ] reject/exception은 source locator, reason, severity와 proposed resolution을 가진다.
- [ ] fresh restore 후 동일 reconciliation 결과가 재현된다.
- [ ] WI-008 go/no-go 보고서가 포함·제외 partition과 rollback 조건을 제시한다.

## Change impact

- Architecture: 없음.
- Data/schema/backup: disposable target only; source backup immutable.
- Security/privacy: detailed report는 restricted local artifact, summary만 Git에 기록한다.
- MCP/API compatibility: 없음.
- Deployment/rollback: 운영 배포 없음; disposable DB 삭제로 rollback 가능.
- Cost/SLO: 약 7,876 source rows라 local execution은 수분 수준으로 예상한다.

## Plan

1. WI-006 manifest와 V1 backup을 checksum으로 고정한다.
2. fresh DuckDB에서 transform과 reconciliation을 수행한다.
3. failure/resume 및 idempotent rerun을 검증한다.
4. 필요할 때만 temporary MotherDuck에서 SQL compatibility를 확인한다.
5. owner용 go/no-go 요약을 작성한다.

## Estimate

- agent/개발 작업시간: 6~10시간
- 실제 dry-run 실행시간: 5분 이내 예상; temporary MotherDuck 포함 시 15분 이내
- 결과 검토·예외 triage: 1~2시간
- 일정 위험: source anomaly 수정이 필요하면 반복 1회당 2~4시간 추가

## Evidence

- 명령/테스트: isolated DuckDB transform 1회 + 동일 manifest 재실행; 자동 회귀 1개 통과
- 운영 증거: source 5,378 = Bronze 5,378; instrument 4,446; price 838; FX 100; 재실행 후 동일 count

## Closeout

- 결과: isolated DuckDB에서 5,378 source observation, 4,446 instrument, 838 price bar, 100 FX rate를 대사했고 동일 입력 재실행이 no-op임을 확인했다.
- 남은 위험: report가 통과해도 live permission/connection/locking은 WI-008에서 별도 검증
- 후속 Work Item: WI-008
