---
id: WI-008
title: Backfill only reconciled V1 history into live V2 tables
status: proposed
type: change
owner: owner
decision_refs: ADR-021, ADR-023, V2-ADR-006, V2-ADR-008, V2-ADR-010, V2-ADR-016
requirement_refs: DEC-003, DEC-005, DEC-010, DEC-044, DEC-045, DGOV-004..DGOV-009
architecture_impact: none; bounded execution of the approved parallel migration
data_impact: additive idempotent writes to allowlisted live V2 tables; V1 remains unchanged
security_impact: security/token/OAuth state excluded and logs redacted
cost_impact: small one-time MotherDuck write/read workload within the existing cost envelope
---

# WI-008 — Backfill only reconciled V1 history into live V2 tables

## Problem and evidence

Live V2 schemas are empty pre-production foundations. Only partitions that passed WI-007 may be copied into live V2,
with a pre-backfill backup, bounded manifest, idempotent resume and an explicit abort path. This is not a consumer
cutover and does not retire V1.

## Classification and contract

- 초기 분류: `change`
- 선행조건: WI-006 and WI-007 closed; reconciliation go decision accepted by owner
- 계약 미달인지 계약 변경인지: 승인된 mapping의 additive live execution이다. 새 source/grain/key는 제외한다.
- 승인 필요 여부: 실행 직전 WI-007 요약, included partitions, estimated writes와 rollback을 owner가 승인해야 한다.

## Scope

- 포함: live V2 preflight, backup, allowlisted partition manifest, bounded additive backfill, checkpoint/resume,
  post-write reconciliation, no-op rerun, cost/quality/lineage evidence와 1영업일 관찰.
- 제외: failed/deferred/rejected row, V1 update/delete, V2 schema drop, runtime writer/reader cutover, Scheduler/MCP 변경,
  security state와 외부 source 3년 신규 수집.

## Acceptance criteria

- [ ] pre-backfill live inventory와 V2 backup/restore evidence가 있다.
- [ ] write 대상은 WI-007 `pass` partition allowlist와 checksum이 일치한다.
- [ ] 모든 write가 idempotent key, run id, source lineage와 quality result를 가진다.
- [ ] post-write row/key/null/quantity/cash/total-asset reconciliation이 dry-run 결과와 일치한다.
- [ ] 동일 manifest 재실행이 no-op이고 V1 row와 기존 V2 row를 변경하지 않는다.
- [ ] abort 시 V2 writer를 중단하고 V1 runtime을 그대로 유지할 수 있다.
- [ ] 1영업일 동안 신규 drift, failed run과 예상 밖 비용이 없다.

## Change impact

- Architecture: 없음; consumer는 계속 V1을 사용한다.
- Data/schema/backup: V2 additive writes only; destructive rollback 대신 failed run을 보존하고 교정 migration/run을 사용한다.
- Security/privacy: restricted report와 redacted logs, analytics 대상 외 security state 제외.
- MCP/API compatibility: 없음.
- Deployment/rollback: application deployment/cutover 없음; V1 reader/writer 유지.
- Cost/SLO: 현재 약 7,876 V1 managed rows 기준 실제 DB 작업은 작고 기존 월 50,000원 ceiling 안이다.

## Plan

1. owner go/no-go와 immutable backfill manifest를 고정한다.
2. live backup, schema/checksum/lock/cost preflight를 실행한다.
3. 저위험 reference/market data부터 작은 shard로 적재하고 매 shard를 대사한다.
4. 통과한 confidential portfolio/ledger shard를 적재한다.
5. 전체 reconciliation, no-op rerun과 1영업일 관찰 후 닫는다.

## Estimate

- agent/운영 작업시간: 3~5시간
- 실제 live backfill 실행시간: 10분 이내 예상; shard 사이 검증을 포함하면 30~60분
- 관찰시간: 1영업일
- 일정 위험: live lock/permission 또는 unexpected drift 발생 시 즉시 중단하며 해결은 별도 Work Item

## Evidence

- 명령/테스트: 시작 전
- 운영 증거: 시작 전

## Closeout

- 결과: 시작 전
- 남은 위험: V2 production writer/reader와 Remote MCP cutover는 별도 Work Item
- 후속 Work Item: remaining Wave 3/4 production integration and dual-run
