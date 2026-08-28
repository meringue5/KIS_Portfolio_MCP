---
id: WI-012
title: Run the first production V2 managed collection pipeline
status: in_progress
type: architecture
owner: owner
decision_refs: ADR-021, ADR-023, V2-ADR-007, V2-ADR-009..011
requirement_refs: DEC-003, DEC-005, DEC-030, DEC-035..041, DEC-045, DEC-046
architecture_impact: approved managed Job and raw-object boundary implementation
data_impact: recurring governed Bronze Silver Gold writes and run quality lineage
security_impact: private GCS, Secret Manager and least-privilege service accounts
cost_impact: scale-to-zero Jobs and bounded source-call budget within approved ceiling
---

# WI-012 — Run the first production V2 managed collection pipeline

## Problem and evidence

V2 계약과 과거 ledger는 있으나 recurring governed writer와 off-vendor raw/backup boundary가 없다.

## Classification and contract

- 분류: approved managed pipeline의 `architecture` 구현.
- 계약: approved catalog only, fixed args, idempotent logical run, V1 writer 유지.

## Scope

- private Seoul GCS raw/backup foundation을 create-or-verify하고 lifecycle/retention/restore를 검증한다.
- held-account/position, price/FX와 ledger incremental 수집을 fixed-argument managed Job으로 실행한다.
- Scheduler와 allowlisted LLM trigger가 같은 pipeline logical key를 사용하도록 한다.

## Acceptance criteria

- [ ] approved pipeline contract가 production adapter, run/stage/quality/lineage/watermark를 남긴다.
- [ ] GCS encryption/public-access prevention/lifecycle와 off-vendor restore evidence가 있다.
- [ ] 동일 logical run은 no-op이고 failure resume/call-budget/pagination gate가 동작한다.
- [ ] 10:00, 14:30, 16:00 및 미국 마감 입력 정책이 calendar-aware fixed schedule로 표현된다.
- [ ] production deployment는 build-once digest, Secret Manager와 least-privilege identity를 사용한다.
- [ ] V1 writer는 유지되며 5거래일 dual-write 관찰을 시작할 수 있다.

## Change impact

- Data: governed Bronze/Silver/Gold incremental write와 GCS recovery objects를 추가한다.
- Security/cost: private bucket, least privilege, scale-to-zero와 bounded call budget.
- Deployment: 정상 GitHub Actions build-once release path만 사용한다.

## Plan

1. private GCS create-or-verify와 restore evidence를 만든다.
2. fixed-argument collection adapter, run/quality/lineage/watermark를 구현한다.
3. Job/Scheduler 구성을 배포 경로에 연결하고 dual-write 관찰을 시작한다.

## Evidence

- WI-011 closed; V1 writers remain active and unchanged.
- private Seoul GCS create/verify: public prevention enforced, uniform access, versioning, bounded lifecycle.
- conditional Firestore IAM and bucket-only object IAM; dedicated runtime/scheduler identities.
- managed adapter tests: calendar/no-op/resume/call budget/raw hash/quality/lineage/watermark/Gold.
- build-once deploy dry-run: one digest, three fixed Jobs at 10:00/14:30/16:00 KST.
- Project OS full gate: 221 passed.
- pending explicit gates: confidential Parquet GCS upload; MotherDuck-token and token-encryption-key accessor IAM;
  normal master/CI Job/Scheduler deployment and first production run.

## Closeout

- 결과: 시작 전
- 후속 Work Item: analytics/signals milestone
