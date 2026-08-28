---
id: WI-002
title: Establish the current operating cost baseline
status: verified
type: maintenance
owner: owner
decision_refs: ADR-021, V2-ADR-013
requirement_refs: DEC-041, V2-W0001
architecture_impact: none
data_impact: none
security_impact: none
cost_impact: yes
---

# WI-002 — Establish the current operating cost baseline

## Problem and evidence

과거 서비스가 상시 실행에 가까웠을 때 월 약 50,000원까지 비용이 발생했으나, 현재 scale-to-zero와
batch-first 구성에서는 훨씬 적게 청구되는 것으로 관찰됐다. 현재 설계 문서에는 7,500원 budget만 있고,
최근 실제 청구·credit·서비스별 attribution·forecast 기준선은 없다.

## Classification and contract

- 초기 분류: `maintenance` — 승인된 비용 architecture를 바꾸지 않는 read-only 운영 조사와 문서화
- 비교 계약: DEC-041, ADR-021, V2-ADR-013, V2 delivery plan의 V2-W0001
- 계약 미달 여부: 현재 비용이 상한을 넘었다는 증거는 없으나 actual baseline evidence가 비어 있다.
- 승인 필요 여부: 조사와 문서 기록은 불필요. billing export, budget, resource 또는 배포 변경은 별도 승인 필요

## Scope

- 포함: 최근 3개 완료월과 당월 MTD의 GCP actual cost·credit·net cost·서비스/SKU attribution, 현재
  resource·budget·forecast 가용성, MotherDuck/provider 고정비, 과거 고비용 구간과 현재 정상월 비교
- 제외: billing export 생성, budget 수정, resource cleanup, Secret Manager/Firestore 변경, 배포

## Acceptance criteria

- [x] 최근 3개 완료월과 당월 MTD actual·credit·net cost를 가능한 범위에서 확인한다.
- [x] 현재 주요 비용 서비스와 고정/사용량 비용을 구분한다.
- [x] 7,500원 정상월 목표와 50,000원 ceiling 대비 headroom을 계산한다.
- [x] 확인된 사실, 추정, 미확인 항목을 분리한 비용 기준선 문서를 남긴다.
- [x] production과 billing 설정을 변경하지 않았음을 확인한다.
- [x] Project OS full gate를 통과한다.

## Change impact

- Architecture: none — 승인된 scale-to-zero·batch-first 구조의 실측 근거만 추가
- Data/schema/backup: none
- Security/privacy: 비용·resource metadata만 기록하고 secret payload·계좌정보는 조회하지 않음
- MCP/API compatibility: none
- Deployment/rollback: read-only 조사와 문서 변경뿐이므로 runtime rollback 없음
- Cost/SLO: actual baseline, headroom과 측정 공백을 기록

## Plan

1. GCP billing account, budget, export와 최근 비용 가용성을 read-only로 확인한다.
2. Cloud Run, Jobs, Scheduler, Artifact Registry, storage와 Secret Manager의 현재 비용 driver를 inventory한다.
3. MotherDuck과 외부 provider 고정비를 확인하고 actual·estimate를 분리한다.
4. 비용 기준선 보고서, traceability와 검증 evidence를 기록한다.

## Evidence

- 보고서: `docs/operations/cost-baseline-2026-08.md`
- Cloud Billing Reports: 5월 730원, 6월 32,706원, 7월 49,473원, 8월 1~26일 9,702원,
  8월 forecast 9,980원
- 원인: 7월 minimum-instance CPU·memory 42,626원, 전체의 86.2%
- scale-to-zero 이후 8월 12~26일: 1,835원, 월 환산 3,724원; 최근 6일 보수 환산 5,093원
- GCP metadata: auth/remote min 0·max 1, Jobs 3, Scheduler 3, secrets 23, registry 2,652.602 MB,
  cleanup policy 없음, BigQuery billing export 없음
- MotherDuck console: Lite Plan with limits, $0/month, 결제수단 미등록; `kis_portfolio` 49.0 MiB,
  active+history+failsafe 약 188.4 MiB
- DB routing: MCP·auth·세 batch Job 모두 `kis_portfolio`; `my_db`는 5 tables + 1 view, 모든 table 0 rows,
  code/deploy/view reference 없음
- `bash scripts/check.sh quick`: 통과
- `bash scripts/check.sh full`: 190 passed, Project OS/architecture/warehouse/MCP surface 통과
- 운영 변경 증거: budget, export, service, Job, Scheduler, secret, database와 deployment 변경 없음

## Closeout

- 결과: 보수 정상월 GCP baseline을 5,100원으로 설정했다. 7,500원 budget과 50,000원 ceiling은 유지하며,
  7월 49,473원은 warm minimum-instance transition 비용으로 분리했다.
- 사용자 인수: 검토 대기
- 남은 위험: MotherDuck Lite compute 세부 counter, GCP 세금/카드 청구, 완전한 scale-to-zero 월말 값은
  아직 확인하지 않았다. 빈 legacy `my_db` 삭제는 destructive maintenance 승인 전까지 보류한다.
- 후속 Work Item: 다음 완전월 cost review, Secret Manager bundle migration, build-once/registry cleanup은
  각각 별도 승인·작업으로 수행한다.
