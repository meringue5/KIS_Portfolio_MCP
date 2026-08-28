# KIS Portfolio Traceability

이 문서는 요구·결정·작업·구현·검증·인수 사이의 연결을 관리한다. 상세 정책은
`docs/governance/project-operating-system.md`가 소유하며, 이 표는 그 정책을 복제하지 않는다.

## Active and Recent Work

| Requirement / feedback | Decision | Work Item | Implementation artifacts | Verification / evidence | Status |
| --- | --- | --- | --- | --- | --- |
| DEC-005/015..017/030/041/044 V2 dual-basis price history | V2-ADR-006/010/012 | WI-015 | price pipeline, revision ledger, bounded backfill | live 18 instruments, 15,152 dual-basis rows, 36/36 partitions, private backup/restore | closed |
| DEC-015..019/026/038/041/044 Milestone 2 production data readiness | V2-ADR-006/010/012 | WI-014 | readiness review and prerequisite order | six read-only research tracks; price/trade/ETF-rights blockers documented | closed |
| DEC-015..017/026/038/041/044 Milestone 2: point-in-time metric foundation | V2-ADR-006/010/012 | WI-013 | metric contracts, Gold value ledger, replay-safe evaluator | nullable unavailable outcome, idempotency, PIT and restore gates; 227 tests pass | closed |
| DEC-046 Milestone 1: canonical portfolio ledger | V2-ADR-006/010/016 | WI-009 | account/position/cash/daily-state mapping and repositories | live 5 accounts, 1,357 positions, 232 cash; 27-day 0 KRW difference; restore | closed |
| DEC-046 Milestone 1: trade/lot/thread ledger | V2-ADR-006/010/016 | WI-010 | trade events, purchase lots, thread links and quality | live 19 trade/lot/thread; 2 matched, 4 partial-history groups; restore | closed |
| DEC-046 Milestone 1: Firestore operational state | V2-ADR-005/008/017 | WI-011 | OAuth/KIS/lease/run-request ports and runtime version gate | concurrency, reconnect/reissue and smoke | closed |
| DEC-046 Milestone 1: managed collection | V2-ADR-007/009..011 | WI-012 | private GCS, fixed Jobs/Scheduler, V2 pipeline adapters | production run, quality/lineage, restore and 5-day observation started | closed |
| DEC-045 / V2-W0308: V1→V2 historical transition | V2-ADR-006/008/016 | WI-006 | executable object/column/key/time/money mapping contract | 20 object disposition, transform allowlist and validator | closed |
| DEC-045 / V2-W0308: isolated migration proof | V2-ADR-008/010/016 | WI-007 | disposable transform runner and reconciliation report | 5,378 observations; price 838, FX 100; idempotent rerun | closed |
| DEC-045 / V2-W0308: reconciled live history | V2-ADR-008/010/016 | WI-008 | bounded allowlisted V2 backfill manifest | live 5,378 observations, no-op rerun, post-backup/restore | closed |
| DEC-001..045 + DGOV-001..010: V2 Wave 1~4 foundation | ADR-021/023 + V2 ADR baseline | WI-005 | modular core, state port, explicit migrations, V2 warehouse, managed pipeline, PDF intake, approved GCP state/secret foundation, parallel MotherDuck schemas | fresh DuckDB and live restore, idempotency/resume/catalog-quality-lineage, GCP provision, 205 tests, full gate | closed |
| DEC-003/005/010..025/030/035..044 + DGOV-010: source inventory와 수집 장바구니 | ADR-023 source selection gate | WI-004 | 14 source, 19 dataset, 7 collection contracts; owner PDF 수동 반입 포함 | DGH/full gate; approved core·recommended와 proposed later·excluded 분리; production 변경 없음 | closed |
| DGOV-001..DGOV-010: Data Governance Harness | ADR-023 | WI-003 | `docs/governance/data-governance-harness.md`, governed TOML registry, Skill/checker | full gate 193 passed; positive/negative contract tests; production 변경 없음 | verified, acceptance pending |
| DEC-041 / V2-W0001: 현재 비용 baseline | ADR-021 + V2-ADR-013 | WI-002 | `docs/operations/cost-baseline-2026-08.md` | GCP 보수 정상월 5,100원; MotherDuck Lite 0원; `my_db` empty legacy 확인; 운영 변경 없음 | verified, acceptance pending |
| DEC-002/004/029/030/033..041: V2 Architecture delta | ADR-021 + reviewed V2 ADR approved | WI-001 | `docs/design/v2-architecture-delta-review.md`, owner docs | 2026-08-28 사용자 승인 반영; full gate 190 passed; 구현·provisioning 미착수 | closed |
| GOV-001..GOV-008: Project OS 도입 | ADR-022 | WI-000 | governance docs, templates, Skill, `scripts/check.sh`, hooks, CI | full gate 190 passed, Skill/YAML validation, state-independent duplicate-WIP negative test | closed |
| DEC-001..DEC-044: KIS Portfolio data platform | ADR-021 approved architecture baseline | V2-W0001..V2-W0806 | `docs/design/kis-portfolio-v2-*.md` | WI-005 foundation closed; delivery-plan Wave 1~4의 배포·cutover·3년 backfill은 후속 Work Item | in_progress |

## Governance Requirements

| ID | Requirement | Acceptance owner |
| --- | --- | --- |
| GOV-001 | 정식 명칭은 Project Operating System, 약칭 Project OS로 고정한다. | owner |
| GOV-002 | Project Governance는 Project OS의 결정·권한·변경통제 하위 영역이다. | owner |
| GOV-003 | 티켓은 추적 레코드이고 승인된 요구·ADR·catalog가 결정 SSOT다. | owner |
| GOV-004 | 모든 비사소한 변경은 분류·계약비교·영향·인수·증거를 가진다. | owner / maintainer |
| GOV-005 | Skill, hook과 CI는 동일한 결정적 검사 entrypoint를 사용한다. | maintainer / CI |
| GOV-006 | 동시에 하나의 구현 Work Item만 `in_progress`로 둔다. | maintainer |
| GOV-007 | 계약 변경은 사용자 승인 뒤 반영하고, 구현에 맞춘 silent widening을 금지한다. | owner |
| GOV-008 | Project OS 자체 변경도 Work Item과 dogfood 검증을 거친다. | owner / maintainer |

## Data Governance Requirements

| ID | Requirement | Acceptance owner |
| --- | --- | --- |
| DGOV-001 | Data Governance Harness는 Project OS 아래에서 data architecture를 집행하는 전문 control system이다. | owner |
| DGOV-002 | 정책은 canonical 문서, 계약 형식은 machine schema, 인스턴스는 registry, 검사는 단일 checker가 소유한다. | owner / maintainer |
| DGOV-003 | source, dataset, collection basket, metric과 pipeline은 구현 전에 versioned contract를 가진다. | data owner |
| DGOV-004 | 승인·활성 계약만 production 수집·publish·분석의 근거가 될 수 있다. | owner / pipeline runner |
| DGOV-005 | grain, key, time semantics, freshness, quality, lineage, sensitivity, retention과 cost 책임을 누락할 수 없다. | data owner |
| DGOV-006 | 미등록 객체·참조, schema drift와 승인 없는 breaking change는 hook·CI·release gate에서 실패한다. | maintainer / CI |
| DGOV-007 | runtime은 run, stage, watermark, quality result와 lineage evidence를 남기고 품질 미달을 성공으로 숨기지 않는다. | pipeline owner |
| DGOV-008 | Gold, metric, signal과 Telegram은 선언된 quality publish gate를 통과한 입력만 공식 결과로 사용한다. | analytics owner |
| DGOV-009 | 예외는 사유·범위·만료·승인자를 가진 Work Item으로만 허용하며 silent bypass를 금지한다. | owner |
| DGOV-010 | 원천 데이터 카탈로그와 수집 장바구니는 이 하네스의 source·collection·dataset 계약 형식을 따른다. | owner / data architect |

## Update Rules

- Work Item을 시작·검증·종료할 때 해당 row의 artifact, evidence와 상태를 같은 변경에서 갱신한다.
- 상세 로그나 긴 테스트 출력은 Work Item/CI artifact에 두고 이 표에는 링크나 명령 이름만 둔다.
- closed row는 삭제하지 않는다. 오래된 항목은 별도 archive table/file로 이동할 수 있다.
- 요구나 결정이 superseded되면 새 ID와 대체 관계를 기록하고 과거 연결을 덮어쓰지 않는다.
