---
id: WI-009
title: Build and reconcile the canonical account position cash and daily asset ledger
status: closed
type: change
owner: owner
decision_refs: ADR-021, ADR-023, V2-ADR-006, V2-ADR-010, V2-ADR-016
requirement_refs: DEC-003, DEC-005, DEC-010, DEC-033, DEC-045, DEC-046
milestone_ref: MS-001
delivery_refs: V2-W0303
parent_work_item: none
depends_on: none
architecture_impact: none; implements approved V2 canonical ledger
data_impact: additive V2 account position cash and Gold daily state backfill
security_impact: stable internal account ids; no raw account number in evidence
cost_impact: bounded MotherDuck reads and writes
---

# WI-009 — Build and reconcile the canonical portfolio ledger

## Problem and evidence

V1 총자산은 계산 가능했지만 account/position/cash grain의 V2 canonical ledger가 없었다.

## Classification and contract

- 분류: 승인된 architecture를 구현하는 `change`.
- 계약: V1 보존, additive V2 write, ambiguity는 추측하지 않고 quality로 남긴다.

## Scope

- V1 portfolio/overseas/holding/overview snapshots를 Bronze provenance와 V2 account, position, cash, daily state로 변환한다.
- V1은 변경하지 않고 ambiguous holding grain은 quality exception으로 보존한다.

## Acceptance criteria

- [x] 5개 account label이 stable internal id와 provenance를 가진다.
- [x] holding 1,619행의 disposition과 natural-key duplicate 34건이 설명된다.
- [x] quantity/cash/총자산이 V1 canonical overview와 0원 tolerance로 대사된다.
- [x] isolated rerun, live bounded write, no-op rerun, backup/restore가 통과한다.

## Change impact

- Data: V2 Bronze/Silver/Gold만 additive write; V1 consumer와 writer는 유지.
- Security/cost: 내부 account id와 redacted evidence, bounded MotherDuck 작업.

## Plan

1. mapping을 고정하고 isolated rehearsal을 수행한다.
2. backup 후 live additive backfill과 reconciliation을 수행한다.
3. no-op rerun과 fresh restore를 검증한다.

## Sub-items

- `none`.

## Evidence

- live: accounts 5, positions 1,357, cash 232, daily state 889; 27일 max difference 0원.
- recovery points: pre `20260827_232909`, post `20260827_233030`; fresh restore 29 tables 통과.

## Closeout

- 결과: 완료
- 후속 Work Item: WI-010
