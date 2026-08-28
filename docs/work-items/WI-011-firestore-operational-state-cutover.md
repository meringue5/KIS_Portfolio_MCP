---
id: WI-011
title: Move operational state behind Firestore ports and remove runtime DDL
status: closed
type: architecture
owner: owner
decision_refs: ADR-021, V2-ADR-005, V2-ADR-008, V2-ADR-017
requirement_refs: DEC-037, DEC-040, DEC-045, DEC-046
milestone_ref: MS-001
delivery_refs: V2-W0202, V2-W0203, V2-W0204, V2-W0205, V2-W0206, V2-W0207
parent_work_item: none
depends_on: WI-009, WI-010
architecture_impact: approved operational-state boundary implementation
data_impact: OAuth KIS token lease and run-request state move outside analytics warehouse
security_impact: restricted state migration and reconnect/reissue path
cost_impact: low-volume named Firestore operations within approved envelope
---

# WI-011 — Move operational state behind Firestore ports

## Problem and evidence

OAuth/KIS token state가 analytics warehouse에 결합되어 있고 production cold start가 DDL을 수행한다.

## Classification and contract

- 분류: 승인된 state-plane boundary의 `architecture` 구현.
- 계약: MotherDuck 원본 보존, Firestore에는 digest/ciphertext만 저장, reconnect/reissue rollback 유지.

## Scope

- OAuth client/grant/code/token, KIS token cache/lease와 pipeline run request를 StateStorePort 뒤로 이동한다.
- runtime auto-DDL을 version check로 교체하고 existing MotherDuck state는 backup 후 reconnect/reissue 방식으로 종료 준비한다.

## Acceptance criteria

- [x] refresh rotation, expiry, revocation, lease fencing과 multi-process contention test가 통과한다.
- [x] auth/remote/token cache가 Firestore state adapter로 redacted smoke 성공한다.
- [x] runtime identity가 startup DDL을 실행하지 않는다.
- [x] rollback/reconnect/reissue runbook과 redacted migration evidence가 있다.

## Change impact

- Architecture: operational state를 Firestore port 뒤로 이동한다.
- Security: bearer plaintext를 저장하지 않고 Secret Manager key 경계를 유지한다.
- Deployment: 환경변수 기반 가역 전환이며 runtime DDL을 금지한다.

## Plan

1. document repository와 concurrency/expiry/revocation test를 구현한다.
2. runtime DDL을 read-only version/schema gate로 교체한다.
3. active state를 preservation-first로 복사하고 smoke/reconnect 경로를 검증한다.

## Sub-items

- `none`.

## Evidence

- focused auth/token/schema tests 47 passed; Project OS quick gate passed.
- live migration source=verified: users 1, identities 1, clients 6, grants 5, active OAuth tokens 1,
  encrypted KIS tokens 5; code 0. No bearer/ciphertext/digest/account value logged.
- named Firestore `asia-northeast3`, Native, delete protection enabled; lease fencing token 2 verified.
- runtime smoke: OAuth client 1, decryptable KIS ciphertext 1, plaintext logged 0.
- runbook: `docs/operations/firestore-state-cutover.md`.

## Closeout

- 결과: state adapter/copy/recovery path 완료. Production revision activation은 WI-012 release에 결합한다.
- 후속 Work Item: WI-012
