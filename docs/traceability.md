# KIS Portfolio Traceability

이 문서는 요구·결정·작업·구현·검증·인수 사이의 연결을 관리한다. 상세 정책은
`docs/governance/project-operating-system.md`가 소유하며, 이 표는 그 정책을 복제하지 않는다.

## Active and Recent Work

| Requirement / feedback | Decision | Work Item | Implementation artifacts | Verification / evidence | Status |
| --- | --- | --- | --- | --- | --- |
| DEC-018/019/025/030/038/041/044 ETF provider rights activation | ADR-023 + V2-ADR-006/010/012 | WI-026 | provider-specific official-source rights review; production registry remains fail-closed | four provider official-source reviews and KRX API alternative checked; 0 production calls/profiles/writes | blocked; explicit production rights or licensed full-composition API required |
| DEC-012..017/027/038/041/044 lot/thread path and risk | ADR-021/023 + V2-ADR-006/010/012 | WI-025 | 8 adjusted-price lot/episode and owner-stop thread/instrument risk metrics, PIT evaluator and readiness inspector | 6 focused/full 374 pass; complete restore; production 0 reconstructed lot, 0 adjusted price, 57 exceptions and no publish/write | closed |
| DEC-012..014/027/031/038/044 typed thread risk and owner review | ADR-021/023 + V2-ADR-006/010/012 | WI-024 | two dataset contracts, migration 0011, owner-authoritative plan revisions and review queue repository | 5 focused / 28 adjacent tests and complete restore; production read-only inventory 19 open threads, 0 generated intent, migration unapplied | closed |
| DEC-004/009..017/026/038/041/044 portfolio performance | ADR-021/023 + V2-ADR-006/010/012 | WI-023 | five versioned metrics, Modified Dietz evaluator, explicit residual and chain-linked drawdown | 9 focused / 22 adjacent tests; restore pass; production read-only gate blocks 889 non-pass state rows and missing exact cash coverage with zero writes/calls | closed |
| DEC-009..014 reconstruction production apply | ADR-021/023 + V2-ADR-006/010/016 | WI-022 / WI-022-S06 | exact-hash append-only exception publish; pre/post private recovery and isolated reconciliation | run 33163171218 attempt 2 / execution `9zmm2`: 57 exceptions, 0 Silver, idempotent replay and restore pass | closed |
| DEC-009..014 reconstruction production impact | ADR-021/023 + V2-ADR-006/010/016 | WI-022 / WI-022-S05 | aggregate-only read-only production planner; UTC/Decimal canonical hash; fail-closed Silver gate | hash `096a01a5...d50b`; 57 exceptions, 0 Silver projections, 0 writes/calls | closed |
| DEC-009..014 append-only reconstruction publish | ADR-021/023 + V2-ADR-006/010/016 | WI-022 / WI-022-S04 | two-hash publish gate; atomic episode, lot, whole-allocation and exception revisions | 7 S04 / 20 focused; full 346 passed; rollback and complete local restore | closed |
| DEC-009..014 deterministic position replay | ADR-021/023 + V2-ADR-006/010/016 | WI-022 / WI-022-S03 | pure reverse/forward trade-action replay, inferred opening, split/successor handling and episode boundaries | 10 focused; full 339 passed; no warehouse write or source call | closed |
| DEC-009..014 reconstruction physical ledger | ADR-021/023 + V2-ADR-006/010/016 | WI-022 / WI-022-S02 | migration 0010, 7 backed tables, 4 current views and complete recovery allowlist | 13 focused; full 329 passed; no live migration | closed |
| DEC-009..014 position/lot/sell reconstruction boundary | ADR-021/023 + V2-ADR-006/010/016 | WI-022 / WI-022-S01 | three governed datasets, reconstruction pipeline, evidence/outcome quality axes and deterministic scoped FIFO contract | 9 focused tests; full 326 passed; no production mutation | closed |
| DEC-015..017 corporate-action identity and adjustment lineage | ADR-021/023 + V2-ADR-006/010/012 | WI-036 | governed KIS source selection, dataset/pipeline, migration 0009, PIT repository and adjustment lineage | 8 focused; full 317 passed; complete local backup/restore; production source/migration not invoked | closed |
| DEC-009..014 production trade/cash history | V2-ADR-006/010/012 | WI-021 / WI-021-S06 | fixed-hash migration/recovery Cloud Run Jobs; pre/post V2 backup, private GCS recovery and restored aggregate reconciliation | run 33145645614 / execution `8q7q6`: 131/131 partitions, 131 calls, 393 stages, 262 quality, 150 lineage, 11 watermarks; private restore pass | closed |
| DEC-009..014 bounded physical broker history | V2-ADR-006/010/012 | WI-021 / WI-021-S05 | per-page KIS adapter and hash/backup-gated production command | 131 partitions, 6 gaps, 374/400 preflight; physical-page and negative CLI tests; full 303 passed | closed |
| DEC-009..014 governed trade/cash normalization | V2-ADR-006/010/012 | WI-021 / WI-021-S04 | guarded fixture pages, immutable observations, trade/cash facts and reconciliation report | incomplete pagination blocks Silver/watermark; replay no-op; full 297 passed | closed |
| DEC-009..014 resumable backfill control | V2-ADR-006/010/012 | WI-021 / WI-021-S03 | governed backfill pipeline identity, partition logical runs, pre-I/O persisted call usage and monotonic watermark | failure/resume, completed reuse, gap/no-regression tests; full 295 passed | closed |
| DEC-009..014 bounded source-call execution | V2-ADR-006/010/012 | WI-021 / WI-021-S02 | 3/3/2 page policy, 400-call preflight and guarded physical-call wrapper | 374/400 reservation, exhaustion/no-invocation tests; full 290 passed | closed |
| DEC-009..014 bounded three-year trade/cash planning | V2-ADR-006/010/012 | WI-021 / WI-021-S01 | deterministic 60-day source-boundary planner and read-only CLI | exact coverage/gap/secret tests; full 278 passed | closed |
| DEC-015..017/026 replay-safe trend and volatility metrics | V2-ADR-006/010/012 | WI-019 | 11 metric contracts, Decimal formulas and strict PIT evaluator | independent SQL/Python goldens, null quality and future-revision exclusion; full 262 passed | closed |
| DEC-009..014 canonical cash-event identity, revisions and PIT provenance | V2-ADR-006/010/012 | WI-020 | migration 0008, event/revision/current objects and PIT repository | category separation, immutable conflict and full backup/restore; full 257 passed | closed |
| complete remaining V2 delivery ownership before WI-020 and WI-019 execution | ADR-021/022 | WI-034 | historical disposition, WI-035~051 append-only baseline, MS-002~004 and completeness checker | all 69 delivery IDs owned; 8 focused and full 254 tests passed | closed |
| DEC-047/048 final M4 V2 documentation SSOT and exact total-asset valuation-change contribution intake | ADR-022 + V2-ADR-006/015 | WI-031 | MS-003/004 baseline, WI-032/033 and metric/read-model contracts | 10 focused tests; full gate 252 passed; no product mutation | closed |
| GOV-003/004/006/008 immutable milestone and Work Item control | ADR-022 | WI-018 | milestone registry, MS-002 baseline, stable relationships and checker | 5 focused tests; full gate 251 passed | closed |
| DEC-005/018/019/030/041/044 held instrument and ETF routing | V2-ADR-006/010/012 | WI-017 | versioned classification, exact routes, rights-gated offline parsers | live 18 versions/14 routes, zero network profiles, private backup/restore, 248 tests | closed |
| DEC-009..014/030/041/044 broker history correction | V2-ADR-006/010/012 | WI-016 | side/pagination/source-field correction and append-only revisions | live 19/19 revisions, zero unknown identity, private backup/restore, 239 tests | closed |
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
| DEC-001..DEC-048: KIS Portfolio data platform | ADR-021 approved architecture baseline | V2-W0001..V2-W0807 | `docs/design/kis-portfolio-v2-*.md` | WI-005 foundation closed; MS-002~004 and remaining delivery items tracked by immutable registry | in_progress |

## Planned Milestone Work

이 표의 Work Item ID는 예약된 불변 식별자다. 우선순위는 번호가 아니라
`governance/project/milestones.toml`의 dependency와 sequence를 따른다.

| Requirement | Design item | Work Item | Dependency | Status |
| --- | --- | --- | --- | --- |
| DEC-015..017/026 trend and volatility | V2-W0503 | WI-019 | WI-013, WI-015 | closed |
| DEC-009..014 canonical cash events | V2-W0304 | WI-020 | WI-013, WI-016 | closed |
| DEC-009..014 three-year trade/cash history | V2-W0403 | WI-021 | WI-016, WI-020 | closed; live recovery evidence recorded |
| DEC-015..017 corporate actions | V2-W0307 | WI-036 | WI-015 | closed; production activation remains gated |
| DEC-009..014 position/lot/sell reconstruction | V2-W0304/0305 | WI-022 | WI-010, WI-021, WI-036 | closed; 57 review exceptions, 0 fabricated Silver, private recovery pass |
| DEC-004/009..017/026 portfolio performance | V2-W0502 | WI-023 | WI-009, WI-015, WI-020..022 | closed; production values remain fail-closed on state/cash coverage quality |
| DEC-012..014/027/031 thread risk plans/review queue | V2-W0305/0306 | WI-024 | WI-010, WI-022 | closed; production migration and owner responses remain gated |
| DEC-012..017/027 lot/thread risk | V2-W0504 | WI-025 | WI-015, WI-019, WI-022, WI-024 | closed; production values remain fail-closed |
| DEC-018/019/025 ETF forward collection | V2-W0405 | WI-026 | WI-012, WI-017 | blocked; no production-rights evidence or licensed full-composition API |
| DEC-018/019/026 ETF look-through | V2-W0505 | WI-027 | WI-009, WI-017, WI-026 | blocked by WI-026 |
| DEC-026/038/048 total-asset KRW valuation-change contribution | V2-W0510 | WI-033 | WI-009, WI-013 | ready |
| DEC-026..028 alert state | V2-W0507 | WI-028 | WI-019, WI-023, WI-025, WI-027, WI-033 | proposed |
| DEC-026..028 replay and shadow | V2-W0509 | WI-029 | WI-028 | proposed |
| DEC-006/026..030 Telegram delivery | V2-W0508 | WI-030 | WI-029 | proposed; external-send gate |
| DEC-033..041 production cost/release controls | V2-W0002/0003/0106 | WI-035 | WI-012 | proposed; MS-003 |
| DEC-020..025 filing actual/fundamental facts | V2-W0406 | WI-037 | WI-012, WI-017 | proposed; MS-003 |
| DEC-020/024 dividend ledger | V2-W0407 | WI-038 | WI-020, WI-021, WI-037 | proposed; MS-003 |
| DEC-022 macro profile | V2-W0408 | WI-039 | WI-012 | proposed; MS-003 |
| DEC-031/032 catalog and quality read model | V2-W0410 | WI-040 | WI-012, WI-019, WI-020 | proposed; MS-003 |
| DEC-020/021/023 forward consensus | V2-W0506 | WI-041 | WI-037 | proposed; MS-003 |
| DEC-002/029/034 stateless Remote MCP reads | V2-W0601~0603 | WI-042 | WI-030, WI-040, WI-041 | proposed; MS-003 |
| DEC-010..014/029 Remote managed commands | V2-W0604/0605 | WI-043 | WI-024, WI-042 | proposed; MS-003 |
| DEC-002/029 client compatibility | V2-W0606/0607 | WI-044 | WI-042, WI-043 | proposed; MS-003 |
| DEC-033..041 V1/V2 readiness | V2-W0701/0702/0703/0706 | WI-045 | WI-035, WI-044 | proposed; MS-003 |
| DEC-002/033..041 Remote production cutover | V2-W0704/0705/0707 | WI-046 | WI-045 | proposed; production gate |
| DEC-002/034 local and V1 public retirement | V2-W0801/0802 | WI-047 | WI-046 | proposed; MS-004 |
| DEC-034/045 V1 main consumer transition | V2-W0803 | WI-048 | WI-046 | proposed; MS-004 |
| DEC-034/040 V1 resource cleanup | V2-W0804 | WI-049 | WI-047 | proposed; destructive gate |
| DEC-033..041 steady-state runbooks | V2-W0805 | WI-050 | WI-047, WI-048 | proposed; MS-004 |
| DEC-034/045 final V2 audit | V2-W0806 | WI-051 | WI-047~050 | proposed; MS-004 |
| DEC-047 final V2 documentation SSOT | V2-W0807 | WI-032 | WI-051 | proposed; final MS-004 |

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
- Work Item ID를 발급하면 기존 row를 이동·재번호화하지 않는다. 새 발견은 sub-item 또는 다음 새 ID로 append한다.
- 상세 로그나 긴 테스트 출력은 Work Item/CI artifact에 두고 이 표에는 링크나 명령 이름만 둔다.
- closed row는 삭제하지 않는다. 오래된 항목은 별도 archive table/file로 이동할 수 있다.
- 요구나 결정이 superseded되면 새 ID와 대체 관계를 기록하고 과거 연결을 덮어쓰지 않는다.
