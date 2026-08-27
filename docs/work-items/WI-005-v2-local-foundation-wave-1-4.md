---
id: WI-005
title: Build the locally verifiable V2 foundation through Wave 4
status: in_progress
type: change
owner: owner
decision_refs: ADR-021, ADR-023, V2-ADR-001..V2-ADR-017
requirement_refs: DEC-001..DEC-045, DGOV-001..DGOV-010
architecture_impact: modular core, ports and adapters, explicit migration and managed pipeline runtime
data_impact: local-only bronze, silver, gold and control schemas plus governed fixture data
security_impact: state port, restricted owner PDF intake and approved Secret Manager/Firestore foundation
cost_impact: local execution plus free-tier-oriented approved GCP state/secret provisioning; no paid data provider
---

# WI-005 — Build the locally verifiable V2 foundation through Wave 4

## Problem and evidence

V2 architecture와 승인된 40개 DGH contract는 있지만 현재 checkout에는 modular application boundary,
versioned migration runner, V2 warehouse object, resumable pipeline runtime와 owner PDF intake가 없다. 목표는
production을 건드리지 않고 fresh local DuckDB와 비민감 fixture로 Wave 1~4 계약을 실행 가능하게 만드는 것이다.

## Classification and contract

- 초기 분류: `change`
- 비교한 요구사항/ADR/catalog: DEC-001..044, ADR-021/023, V2 architecture/delivery plan,
  approved source·dataset·collection contracts
- 계약 미달인지 계약 변경인지: 승인 계약을 구현하는 작업이며 의미 확장은 하지 않는다.
- 승인 필요 여부: DEC-044와 활성 goal이 repository-local 구현·fixture·test·migration dry-run을 승인했고,
  DEC-045가 Secret Manager·Seoul Firestore 기반 provisioning을 추가 승인했다. production traffic cutover,
  기존 writer 중지, 유료 provider, 외부 전송, 삭제와 대량 backfill은 범위 밖이다.

## Scope

- 포함: Wave 1 package boundary/value object/port, Wave 2 local state port와 explicit migration runner, Wave 3
  local V2 schema·repository·canonical ledger, Wave 4 pipeline registry/runner·fixture adapter·PDF intake·catalog
  quality/lineage read model, Secret Manager·Firestore create-or-verify, 문서·백업 계약과 자동 검증.
- 제외: GCS/Cloud Run provisioning, production traffic cutover, destructive live MotherDuck migration, production source call, 대량 backfill,
  Remote MCP public surface cutover, Telegram, 신호, 주문, push/deploy.

## Acceptance criteria

- [ ] domain/application이 DuckDB, MCP, HTTP와 GCP SDK 없이 import되고 architecture test가 방향을 강제한다.
- [ ] local state adapter가 atomic claim/lease semantics를 검증하고 versioned migration은 fresh DuckDB에서
      apply, no-op rerun, checksum mismatch와 failure resume를 검증한다.
- [ ] bronze/silver/gold/control 객체와 account/instrument/position/cash, trade/lot/thread/journal, price/FX,
      ETF/filing/fact/dividend/macro 및 pipeline evidence가 catalog·migration·repository·backup 계약을 가진다.
- [ ] approved fixture pipeline은 logical idempotency, stage resume, call budget, quality, lineage와 catalog
      read model을 검증한다.
- [ ] owner PDF intake는 signature/hash/size/rights 검증, private content-addressed local object, versioned
      extraction lineage와 restricted-output 경계를 검증한다.
- [ ] V1 193개 이상 테스트와 full Project OS gate가 통과한다.

## Change impact

- Architecture: V1을 보존하며 `modules/application/ports/adapters/platform` V2 경계를 병렬 추가한다.
- Data/schema/backup: local explicit migrations만 실행하고 V2 catalog/registry/backup 문서를 함께 갱신한다.
- Security/privacy: 테스트에는 synthetic fixture만 사용하고 PDF는 private local path와 restricted metadata만 노출한다.
- MCP/API compatibility: 기존 public MCP catalog와 disabled order stub을 변경하지 않는다.
- Deployment/rollback: 배포 없음. V2 consumer가 없으므로 로컬 커밋 revert로 rollback 가능하다.
- Cost/SLO: 외부 호출과 유료 서비스 없음. local fixture 실행시간과 예상 storage만 기록한다.

## Plan

1. modular foundation과 architecture test를 만든다.
2. local state port와 versioned DuckDB migration runner를 만든다.
3. V2 physical catalog, migration, repositories와 canonical ledger test를 만든다.
4. managed pipeline runtime, fixture sources, PDF intake와 governance read model을 만든다.
5. fresh DB rehearsal, failure injection, full regression과 문서 정합성을 검증하고 checkpoint commit을 남긴다.

## Evidence

- 명령/테스트: 진행 중
- 운영 증거: production·live DB·GCP·외부 source 변경 없음

## Closeout

- 결과: 진행 중
- 남은 위험: 진행 중
- 후속 Work Item: Wave 5 이후는 이 작업 범위 밖
