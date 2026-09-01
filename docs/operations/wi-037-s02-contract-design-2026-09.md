# WI-037-S02 filing contract design — 2026-09-02

> Work Item: `WI-037-S02`
> 상태: in progress
> 분류: architecture/data-contract clarification; design only
> 선행 증거: `WI-037-S01`
> 변경 경계: production code, DDL, migration, DB write, source call, credential, payload fixture, deployment와 schedule activation 없음

## Purpose

OpenDART와 SEC EDGAR actual을 구현하기 전에 issuer identity, immutable source evidence, canonical filing event,
financial fact revision과 point-in-time query의 의미를 하나의 승인 가능한 설계로 고정한다. S01이 발견한
논리 Bronze `dataset.filing-event`와 물리 `silver.filing_events`의 layer mismatch를 조용히 수용하지 않는다.

## Starting evidence

- `source.opendart`와 `source.sec-edgar`는 canonical·approved이고 무료 공식 source다.
- `collection.fundamentals-dividends-v1`, `dataset.filing-event`, `dataset.financial-fact`와
  `pipeline.fundamentals-dividends-v2`는 approved지만 아직 active가 아니다.
- 현재 직접 filing 대상은 보유 KRX equity 3개와 미국 equity/REIT 4개다. S01 시점에 미국 4개는 CIK가
  있었고 국내 3개는 DART `corp_code`가 없었다.
- `silver.filing_events`와 `silver.financial_facts`는 foundation DDL에 존재하지만 S01 live inventory에서
  모두 0행이었다. 이 빈 foundation을 승인된 의미의 구현 완료로 간주하지 않는다.
- 현재 filing table은 jurisdiction, source URL, reporting period, correction relation과 object manifest를,
  fact table은 period start, context/revision identity와 source/normalized concept 분리를 충분히 표현하지 못한다.

## Questions to freeze

1. source observation/object evidence와 canonical filing ledger를 어떤 Bronze/Silver dataset ID로 분리할 것인가?
2. KRX `stock_code ↔ corp_code`와 U.S. ticker/exchange ↔ CIK alias의 유효시점·관찰시점·품질을 어떻게 보존할 것인가?
3. SEC acceptance timestamp, OpenDART day-grain receipt date, system `fetched_at`과 `knowledge_at`을 어떻게 구분할 것인가?
4. amendment/correction/withdrawal relation을 무엇을 근거로 확정하고 불명확한 관계를 어떻게 격리할 것인가?
5. source taxonomy/context를 보존하면서 normalized concept mapping을 어떤 version/provenance로 추가할 것인가?
6. 원문 object의 허용 media, content hash, private GCS retention, backup/restore와 재배포 금지를 어떻게 고정할 것인가?
7. routine/backfill 호출예산, pagination, conditional request, retry, partial quarantine와 watermark gate를 어떻게 고정할 것인가?
8. 기존 v1 계약과 빈 Silver foundation의 compatibility, additive migration, dual-read와 rollback 경계를 어떻게 정의할 것인가?

## Work plan and checkpoints

| Checkpoint | State | Output |
| --- | --- | --- |
| S02 registration and immutable scope | complete | registry, parent Work Item, traceability and milestone revision |
| current contract/physical compatibility matrix | in progress | logical/physical mismatch and consumer impact |
| target identity/time/correction/object model | pending | keys, timestamps, relation quality and source-specific rules |
| bounded pipeline/cost/failure design | pending | routine/backfill budgets, pacing, retry, quarantine and watermark |
| alternatives and ADR/approval package | pending | versioning, migration, rollback, residual risk and owner decisions |
| quick/full verification and closeout | pending | deterministic checks; no production mutation |

## Initial constraints

- directly held equity/REIT issuer만 포함하며 ETF look-through issuer를 다시 끌어오지 않는다.
- ticker, 종목명이나 heuristic만으로 issuer를 확정하지 않는다. missing/ambiguous alias는 fail closed다.
- backfill의 historical filing time과 시스템 최초 관찰시각을 동일시하지 않는다.
- correction은 이전 filing/fact를 덮어쓰지 않고 새 revision과 relation으로 보존한다.
- source taxonomy, concept, unit, period와 dimensional context를 normalized mapping이 대체하지 않는다.
- 원문은 허용된 official artifact만 private content-addressed object로 보존하고 MCP·Telegram에 재배포하지 않는다.
- approved contract를 구현 편의에 맞춰 같은 version으로 조용히 변경하지 않는다.

## Acceptance criteria

- [ ] Bronze/Silver dataset 경계, grain, natural key, time semantics와 compatibility가 명시된다.
- [ ] issuer alias, filing correction, fact revision과 point-in-time selection이 source별로 정의된다.
- [ ] raw object retention, restore, security와 consumer 경계가 정의된다.
- [ ] routine/backfill call budget, partial/failure, idempotency와 watermark가 수치로 제안된다.
- [ ] ADR 필요 여부, contract version delta, migration/rollback과 owner approval 항목이 제시된다.
- [ ] 구현·DB·source·credential·deployment 변경이 없고 quick/full gate가 통과한다.

## Current disposition

S02는 설계 조사 중이다. parent `WI-037`과 MS-003은 `proposed`이고, 현재 approved 계약은 active로
승격하지 않았다. 이 문서는 승인된 계약이나 구현 권한을 새로 만들지 않는다.
