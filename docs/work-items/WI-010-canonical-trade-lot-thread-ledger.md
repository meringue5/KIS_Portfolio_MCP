---
id: WI-010
title: Build the canonical trade purchase-lot and trade-thread ledger
status: closed
type: change
owner: owner
decision_refs: ADR-021, ADR-023, V2-ADR-006, V2-ADR-010, V2-ADR-016
requirement_refs: DEC-010..DEC-014, DEC-028, DEC-045, DEC-046
milestone_ref: MS-001
delivery_refs: V2-W0304, V2-W0305
parent_work_item: none
depends_on: WI-009
architecture_impact: none; implements approved order-grain lot model
data_impact: additive V2 trade events purchase lots threads and allocation quality
security_impact: account ids remain internal and reports are redacted
cost_impact: bounded MotherDuck reads and writes
---

# WI-010 — Build the canonical trade, lot and thread ledger

## Problem and evidence

평단가와 별개인 order-grain lot/thread 분석을 위해 canonical immutable trade ledger가 필요했다.

## Classification and contract

- 분류: 승인된 lot/thread 요구를 구현하는 `change`.
- 계약: 불완전한 source history로 opening lot을 추측하지 않는다.

## Scope

- canonical domestic order 20행과 신뢰 가능한 거래를 immutable trade event와 order-grain purchase lot으로 변환한다.
- correction, incomplete overseas transaction과 source gap은 추측하지 않고 quality/disposition을 남긴다.

## Acceptance criteria

- [x] 19개 filled buy(그중 correction 1개)의 event identity/link가 결정적이다.
- [x] purchase lot 합계와 해당 position의 설명 가능한 범위가 대사된다.
- [x] 기본 thread key와 journal-ready link가 생성되며 inferred/manual quality가 구분된다.
- [x] isolated/live/no-op/backup/restore evidence가 있다.

## Change impact

- Data: canonical trade/lot/thread를 additive 생성하며 deferred source를 보존한다.
- API/deployment: consumer cutover나 주문 API 변경 없음.

## Plan

1. source disposition과 deterministic event identity를 확정한다.
2. isolated/live migration과 position reconciliation을 수행한다.
3. no-op과 restore를 검증한다.

## Sub-items

- `none`.

## Evidence

- live: trade 19, lot 19, thread/link 19; account-instrument 6개 중 2 match, 4 partial history.
- unfilled 1개와 side/quantity 없는 overseas 2개는 Bronze에 보존하고 canonical event는 defer.
- recovery points: pre `20260827_233030`, post `20260827_233357`; fresh restore 통과.

## Closeout

- 결과: 완료
- 후속 Work Item: WI-011
