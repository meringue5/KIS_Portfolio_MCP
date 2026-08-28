---
id: WI-005
title: Build the locally verifiable V2 foundation through Wave 4
status: closed
type: change
owner: owner
decision_refs: ADR-021, ADR-023, V2-ADR-001..V2-ADR-017
requirement_refs: DEC-001..DEC-045, DGOV-001..DGOV-010
architecture_impact: modular core, ports and adapters, explicit migration and managed pipeline runtime
data_impact: parallel live bronze, silver, gold and control foundation; governed fixture data remains local-only
security_impact: state port, restricted owner PDF intake and approved Secret Manager/Firestore foundation
cost_impact: local execution plus free-tier-oriented approved GCP state/secret provisioning; no paid data provider
---

# WI-005 — Build the locally verifiable V2 foundation through Wave 4

## Problem and evidence

V2 architecture와 승인된 DGH contract를 modular application boundary, versioned migration runner, V2 warehouse,
resumable pipeline runtime와 owner PDF intake로 실행 가능하게 만들고, 기존 `main`을 보존한 병렬 live foundation과
fresh local DuckDB rehearsal로 이를 검증하는 것이 목표다.

## Classification and contract

- 초기 분류: `change`
- 비교한 요구사항/ADR/catalog: DEC-001..044, ADR-021/023, V2 architecture/delivery plan,
  approved source·dataset·collection contracts
- 계약 미달인지 계약 변경인지: 승인 계약을 구현하는 작업이며 의미 확장은 하지 않는다.
- 승인 필요 여부: DEC-044와 활성 goal이 repository-local 구현·fixture·test·migration dry-run을 승인했고,
  DEC-045가 Secret Manager·Seoul Firestore 기반 provisioning을 추가 승인했다. production traffic cutover,
  기존 writer 중지, 유료 provider, 외부 전송, 삭제와 대량 backfill은 범위 밖이다.

## Scope

- 포함: Wave 1 package boundary/value object/port, Wave 2 local/Firestore state port와 explicit migration runner,
  Wave 3 V2 schema·repository·canonical ledger, Wave 4 pipeline registry/runner·fixture adapter·PDF intake·catalog
  quality/lineage read model, Secret Manager·Firestore create-or-verify, 기존 `main` 보존 병렬 MotherDuck migration,
  V1/V2 backup·fresh restore rehearsal와 자동 검증.
- 제외: GCS/Cloud Run provisioning, production traffic cutover, destructive live MotherDuck migration, production source call, 대량 backfill,
  Remote MCP public surface cutover, Telegram, 신호, 주문, push/deploy.

## Acceptance criteria

- [x] domain/application이 DuckDB, MCP, HTTP와 GCP SDK 없이 import되고 architecture test가 방향을 강제한다.
- [x] local state adapter가 atomic claim/lease semantics를 검증하고 versioned migration은 fresh DuckDB에서
      apply, no-op rerun, checksum mismatch와 failure resume를 검증한다.
- [x] bronze/silver/gold/control 객체와 account/instrument/position/cash, trade/lot/thread/journal, price/FX,
      ETF/filing/fact/dividend/macro 및 pipeline evidence가 catalog·migration·repository·backup 계약을 가진다.
- [x] approved fixture pipeline은 logical idempotency, stage resume, call budget, quality, lineage와 catalog
      read model을 검증한다.
- [x] owner PDF intake는 signature/hash/size/rights 검증, private content-addressed local object, versioned
      extraction lineage와 restricted-output 경계를 검증한다.
- [x] V1 193개 이상 테스트와 full Project OS gate가 통과한다.

## Change impact

- Architecture: V1을 보존하며 `modules/application/ports/adapters/platform` V2 경계를 병렬 추가한다.
- Data/schema/backup: 기존 `main`을 보존하고 V2 schema를 병렬 적용했으며, catalog/registry/backup·restore 문서를 함께 갱신한다.
- Security/privacy: 테스트에는 synthetic fixture만 사용하고 PDF는 private local path와 restricted metadata만 노출한다.
- MCP/API compatibility: 기존 public MCP catalog와 disabled order stub을 변경하지 않는다.
- Deployment/rollback: application 배포·traffic cutover 없음. V2 consumer가 없어 V1 runtime은 영향 없이 유지된다.
- Cost/SLO: 유료 data provider와 production source call 없음. named Firestore는 low-volume state operation만 허용하고 기존 월 비용 gate로 감시한다.

## Plan

1. modular foundation과 architecture test를 만든다.
2. local state port와 versioned DuckDB migration runner를 만든다.
3. V2 physical catalog, migration, repositories와 canonical ledger test를 만든다.
4. managed pipeline runtime, fixture sources, PDF intake와 governance read model을 만든다.
5. fresh DB rehearsal, failure injection, full regression과 문서 정합성을 검증하고 checkpoint commit을 남긴다.

## Evidence

- governance: DGH checker `registered_contracts=45`; approved pipeline contract 5개 포함.
- focused tests: Wave 1~4 architecture, state, migration, warehouse, pipeline, rehearsal, PDF intake 8개 통과.
- local rehearsal: Bronze→Silver→quality→Gold, logical rerun no-op, failed-stage resume, call-budget fail closed,
  lineage/read model과 restricted PDF 경계 확인.
- GCP: Secret Manager 기존 secret name 23개를 payload 조회 없이 보존; Firestore API enable;
  named `kis-portfolio-state` 생성 및 marker read-back, lease contention/fencing/release 확인.
- MotherDuck: preflight V1 backup 후 migration `0001`, `0002` 적용 및 no-op rerun; V2 32개 object,
  missing/신규 drift 없음; V2 29개 table backup과 fresh DuckDB restore 확인.
- full gate: 205 passed, 기존 Authlib deprecation warning 1개; Project OS, DGH 45 contract, architecture,
  warehouse와 MCP 35-tool surface 검사 통과.
- 운영 기록: [GCP V2 foundation](../operations/gcp-v2-foundation-2026-08.md),
  [MotherDuck V2 foundation](../operations/motherduck-v2-foundation-2026-08.md).

## Closeout

- 결과: Wave 1~4의 로컬 실행 기반과 승인된 live state/warehouse foundation을 완료했다. 이 결과는 전체
  delivery plan의 Wave 1~4(배포 image, OAuth cutover, 3년 backfill 포함) 완료를 뜻하지 않는다.
- 남은 위험: V1→V2 historical backfill, production pipeline source adapter, GCS restricted-object backup,
  Remote MCP/Telegram cutover는 검증·승인 전이며 이번 변경에서 활성화하지 않았다.
- 후속 Work Item: V1→V2 historical backfill mapping/reconciliation dry-run과 아직 남은 delivery-plan
  Wave 1~4 production integration을 별도 bounded Work Item으로 진행한다.
