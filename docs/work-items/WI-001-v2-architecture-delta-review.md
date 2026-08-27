---
id: WI-001
title: Review and approve the KIS Portfolio V2 architecture delta
status: verified
type: architecture
owner: owner
decision_refs: ADR-021, V2-ADR-003..006, V2-ADR-009, V2-ADR-011, V2-ADR-015
requirement_refs: DEC-002, DEC-004, DEC-029, DEC-030, DEC-033..DEC-041
architecture_impact: yes
data_impact: yes
security_impact: yes
cost_impact: yes
---

# WI-001 — Review and approve the KIS Portfolio V2 architecture delta

## Problem and evidence

V2 설계는 현행 구조에서 네 가지 큰 변경을 제안한다: Firestore operational state plane, stateless Remote
MCP, 하나의 immutable image digest, 18개 이하의 V2 public tool catalog. 모두 구현 가능성은 조사됐지만
ADR-021과 일부 V2 ADR은 아직 제안 상태이며 사용자 승인 전에는 production 구현을 시작할 수 없다.

## Classification and contract

- 초기 분류: `architecture`
- 관련 승인 요구: Remote MCP SSOT, scope 분리, Scheduler primary, scale-to-zero·batch-first와 월 5만원 상한
- 변경 대상: auth/storage trust boundary, remote transport, release topology, public MCP contract
- 승인 필요 여부: 네 결정은 architecture gate 조건에 해당하며 사용자 승인 필요

## Scope

- 포함: 현행 코드·배포·비용 근거 갱신, 공식 플랫폼 문서 확인, 대안·trade-off, security/IAM, migration,
  compatibility, rollback과 승인 권고
- 제외: Firestore 활성화, Cloud Run 변경, OAuth/token migration, tool 제거·추가, container build·배포

## Acceptance criteria

- [x] 네 architecture delta별 현재 근거와 문제를 확인한다.
- [x] 유지·대안·권고안을 비용·보안·운영·호환성 관점에서 비교한다.
- [x] 승인할 결정과 구현 전 검증 gate를 명확히 분리한다.
- [x] tool catalog의 업무 책임, scope와 V1 migration mapping을 검토한다.
- [x] 선택을 바꾸거나 보류할 조건과 rollback 경계를 기록한다.
- [x] 사용자에게 한 묶음으로 승인 가능한 review package를 제공한다.
- [x] production·DB·connector에 변경이 없음을 검증한다.

## Change impact

- Architecture: auth/resource 배포와 application/state/data plane 경계 확정 후보
- Data/schema/backup: operational state를 MotherDuck 밖으로 옮기는 제안; 이번 작업은 문서만 변경
- Security/privacy: OAuth/KIS token 저장소, IAM, scope와 tool surface 검토
- MCP/API compatibility: stateless transport와 V1→V2 public tool migration 검토
- Deployment/rollback: build-once digest와 fixed Job image의 release/rollback 검토
- Cost/SLO: Firestore, image storage, cold start와 timeout 영향 검토

## Plan

1. 현재 code, live metadata와 승인 계약을 다시 조사한다.
2. 공식 Firestore, Cloud Run, MCP SDK 근거와 비용 조건을 갱신한다.
3. 네 delta의 대안·결정·검증·rollback을 review package로 작성한다.
4. Project OS quick/full gate를 실행하고 사용자 승인 질문을 묶어서 제시한다.

## Evidence

- review package: `docs/design/v2-architecture-delta-review.md`
- `uv run python .agent/skills/kis-mcp-surface-audit/scripts/inspect_mcp_surface.py`: 통과, 35 tools
- `uv run python .agent/skills/kis-architecture-audit/scripts/check_architecture_contracts.py`: 통과
- `bash scripts/check.sh quick`: Project OS/architecture/warehouse/MCP surface 통과
- `bash scripts/check.sh full`: 190 passed, Project OS/architecture/warehouse/MCP surface 통과
- code evidence: MCP adapter 1,202행, DB repository 1,442행, KIS service 1,560행; MCP adapter direct
  `get_connection()` 경로 10개; deploy target별 `--source .`
- 운영 metadata: auth/remote scale-to-zero·max 1, 3개 Job 최근 성공, Artifact Registry 약 2.65 GB와 cleanup
  policy 없음, Firestore API 비활성, Secret Manager resources 23개
- MotherDuck inventory: managed 25 tables + 2 views, live 27 tables + 3 views와 documented drift
- 공식 근거: Firestore transaction/TTL/pricing/IAM/location, Secret Manager pricing/best practices,
  MCP Python SDK transport, Cloud Run digest/Job, Artifact Registry cleanup, BigQuery/Cloud SQL pricing
- 운영 증거: GCP·MotherDuck는 read-only metadata/inventory만 조사; production, DB, scheduler, connector 변경 없음

## Closeout

- 결과: Firestore 1 DB + Secret Manager key 격리, conditional stateless MCP, build-once digest, 18-tool V2
  catalog의 승인 권고와 migration·rollback·cost/compatibility gate를 한 review package로 작성했다.
- 사용자 인수: 대기 중. 승인 전에는 ADR 상태와 production implementation을 변경하지 않는다.
- 남은 위험: 실제 client compatibility, active secret version 수와 billing baseline, Firestore collection
  allowlist의 IAM 대비 약한 격리는 implementation rehearsal이 필요하다.
- 후속 Work Item: 사용자 승인 결과에 따른 ADR 승격/수정, 이후 V2-W0001 또는 architecture revision
