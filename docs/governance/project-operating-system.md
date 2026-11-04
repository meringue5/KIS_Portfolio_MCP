# KIS Portfolio Project Operating System

> 정식 명칭: Project Operating System
> 한국어 명칭: 프로젝트 운영체계
> 약칭: Project OS
> 상태: 승인·활성
> 현행 운영 기준 검토: 2026-11-04
> 소유 범위: 요구·결정·작업·검증·배포·운영 피드백의 개발 운영체계

## 0. 운영 작업의 진입점

V2 구축 인수 범위는 [인수 기준선](../milestones/v2-acceptance.md)에 있다. 평소에는 실제 증상, 기능
또는 승인된 요청에서 출발한다. [운영 모델](../operating-model.md)에서 결과의 의미를 확인하고 필요한
[현행 계약](../design/README.md) 한 편과 [기능 추적표](../traceability.md)의 해당 행으로 좁힌다.

| 들어온 일 | 출발점 | 남길 결과 |
| --- | --- | --- |
| 정기 운영 점검 | [운영 런북](../operations/steady-state-operations-runbook.md)의 점검 주기와 증거 | 실제 run·품질·전송·복원 결과. 후속 조치가 필요한 발견은 triage |
| 장애·품질 이상 | [증상별 대응](../troubleshooting.md), 현재 계약, 영향 범위와 관측 증거 | 완화·재검증 및 남은 조치의 소유자. 닫힌 인수 기준선의 교정은 §6.4 적용 |
| 유지보수·기능 수정 | [작업 큐](../../TODO.md)와 기능 추적표. 요구 → 계약 → 구현 → 테스트 | 해당 작업의 상태·검증과 바뀐 규칙의 정본 갱신 |
| 새 제품 범위 | 제안·후보의 승인 여부와 기존 DEC/ADR 확인 | 승인된 변경만 요구·작업으로 등록. 새 delivery 경계가 필요할 때 §6.2–6.3 적용 |
| 판단의 배경·당시 사례 | 현행 문서의 관련 근거, [구축 원문 목록](../history/README.md) | 필요한 사례만 열고 해당 버전과 당시 조건을 확인 |

## 1. 목적과 경계

Project OS는 KIS Portfolio를 일관되게 변경하고 운영하기 위한 상위 control system이다. 제품의
application/data/runtime architecture를 대체하지 않고, 그것을 승인된 계약에 맞게 변화시키는 절차와
검사·증거를 소유한다. `Project Governance`는 Project OS 안에서 결정권, 문서 권한과 변경 통제를 담당하는
하위 영역이다.

```text
KIS Portfolio 전체 시스템
├── Product System
│   ├── application architecture
│   ├── data architecture
│   └── deployment/runtime architecture
└── Engineering Control System = Project OS
    ├── governance and decision authority
    ├── issue/work-item lifecycle
    ├── skills and shared check harness
    ├── Data Governance Harness and specialized contract gates
    ├── local hooks, CI and release gates
    └── operational evidence and feedback
```

Project OS는 제품의 자동 주문 권한, 운영 secret 접근 또는 배포 권한을 새로 부여하지 않는다. 각 작업의
실제 권한은 사용자 요청과 기존 보안·배포 계약을 따른다.

## 2. 운영 원칙

1. **정책과 실행을 분리한다.** 문서는 정책, Skill은 절차, script는 결정적 검사, CI는 강제 장치다.
2. **티켓은 결정 SSOT가 아니다.** Issue/Work Item은 관찰부터 승인·증거까지 연결하고, 승인된 결정은
   요구사항·ADR·catalog 같은 소유 문서에 기록한다.
3. **계약을 코드에 맞춰 조용히 넓히지 않는다.** 구현이 계약을 어기면 구현을 고친다. 의도한 동작을
   바꾸려면 사용자 승인과 계약 변경이 먼저다.
4. **한 검사 엔진을 재사용한다.** Skill, Git hook과 CI는 `scripts/check.sh`를 호출하며 검사 로직을
   별도로 복제하지 않는다.
5. **위험에 비례한 절차를 사용한다.** 단순 결함은 regression test로 닫고, 경계·SSOT·보안·비용을
   바꿀 때만 ADR gate를 연다.
6. **증거 없는 완료를 금지한다.** 자동 테스트만으로 충분하지 않은 변경은 live/shadow/restore/cost
   증거와 사용자 인수를 요구한다.
7. **Project OS도 자신을 우회할 수 없다.** 이 문서, Skill, hook 또는 검사 변경도 Work Item과 검증을
   거친다.
8. **사용자 노출 기능은 실제 사용으로 인수한다.** unit/integration test, CI, 배포 성공과 HTTP smoke는
   필요조건이지 정보가치의 완료 증거가 아니다. 실제 승인 client와 transport로 즉시 재현 가능한
   positive, partial, error 시나리오를 실행하고 발견된 결함·데이터 공백·미지원 범위를 소유 작업에
   연결해야 한다.

## 3. 권한과 Source of Truth

| 책임 | Canonical source | 변경 권한 |
| --- | --- | --- |
| 제품 목적·사용자 동작·인수 기준 | `docs/requirements/`의 승인된 DEC | 사용자 승인 |
| 장기 architecture decision | `SPEC.md`의 승인 ADR | 사용자 승인 |
| 현재 코드·신뢰 경계 | [ARCHITECTURE](../../ARCHITECTURE.md)와 승인 ADR | ADR/Work Item에 따라 변경 |
| 운영 의미·분야별 판단 규칙 | [운영 모델](../operating-model.md)과 [현행 계약](../design/README.md) | 소유 정본을 근거로 갱신 |
| 일상 점검·장애 대응 | [운영 런북](../operations/steady-state-operations-runbook.md)과 [증상별 대응](../troubleshooting.md) | 운영 절차 및 기존 승인 범위 |
| 구축 원문·사례 | [원문 목록](../history/README.md), 고정 Git 버전, Work Item·운영 증거 | 출처와 당시 조건을 보존 |
| 데이터 객체·grain·key·민감도 | `docs/data-catalog.md` + `db/catalog.py` | warehouse change contract |
| source·collection·dataset·metric·pipeline 계약 | `docs/governance/data-governance-harness.md` + `governance/catalog/` | Data Governance Harness |
| 보안·secret·token | `docs/security-and-secrets.md` | security review |
| 배포·rollback | `docs/deployment.md` + versioned manifest | release approval |
| Project OS 정책 | 이 문서 | 사용자 승인 또는 비의미적 정비 |
| 마일스톤 기준선·Work Item 불변 식별자·관계 | `governance/project/milestones.toml` + `docs/milestones/` | governance Work Item |
| 변경 접수·진행 상태 | GitHub Issue; 로컬 bootstrap은 `docs/work-items/` | maintainer triage |
| 요구→구현→증거 연결 | `docs/traceability.md` | Work Item과 같은 변경 |
| 임시 우선순위 메모 | `TODO.md` | 편집 가능; 결정·상태 SSOT 금지 |

충돌 시 더 구체적인 canonical 문서가 우선하지만 상위 사용자 요구나 승인 ADR을 위반할 수 없다. 충돌을
발견하면 임의로 하나를 선택하지 않고 Issue/Work Item에 기록해 계약을 먼저 정리한다.

### 3.1 운영 지식 갱신

분야별 계약은 `docs/design/<영역>-contract.md`에 범위와 의미, 판단 규칙, 변경과 검증, 관련 근거
순서로 작성한다. 다른 작업에도 적용할 수 있는 판단 규칙은 승인 근거와 함께 운영 모델 또는 소유 계약에
반영한다. 날짜·특정 실행의 증거는 작업 기록에 두고 관련 근거에서 연결한다. 인수 근거가 바뀌면 기능
추적표의 해당 행을 갱신하고, 작업 우선순위나 후보 상태는 TODO에서 확인한다. 계약의 적용 범위나
권한을 바꾸려면 기존 승인 절차를 따른다.

버전 인수 문서는 `docs/milestones/v<버전>-acceptance.md`에 인수 범위와 한계, 종료 기준, 운영 책임을
기록한다. 구축 보관본은 `docs/history/`에 버전과 기준일을 붙이고 원문 경로, 출처 버전, 해시를
manifest에 남긴다. 운영 중 발견한 재사용 가능한 교훈은 해당 계약이나 런북에 반영하고 원래 사례를 연결한다.

## 4. 변경 분류

모든 비사소한 repository 변경과 운영 이상은 다음 중 하나로 분류한다.

| Type | 판정 | 계약 처리 | 기본 증거 |
| --- | --- | --- | --- |
| `defect` | 승인 계약은 명확하나 구현/운영이 미달 | 계약 변경 없음 | 재현 + regression test |
| `clarification` | 기대 동작 또는 인수 조건이 모호함 | DEC/acceptance 보완 승인 | 예시·경계조건 |
| `change` | 기존 계약대로 동작하지만 새 결과를 원함 | 요구사항 승인 후 구현 | 대안·영향·인수 기준 |
| `architecture` | 경계, SSOT 또는 비기능 결정 변경 | ADR 승인 후 구현 | 대안·trade-off·rollback |
| `incident` | 운영 장애·보안·데이터 오염/유실 | 먼저 완화·보존, 이후 원인 분류 | timeline·logs·impact |
| `maintenance` | 동작을 바꾸지 않는 의존성·문서·도구 정비 | 필요 시 contract 갱신 | 회귀·운영 무변경 증거 |
| `governance` | Project OS 자체 변경 | 이 문서/하네스 영향 검토 | self-check와 dogfood |

분류는 원인을 조사하며 바뀔 수 있다. 변경 전후의 분류와 이유는 Work Item history에 남긴다.

## 5. ADR Gate

다음 중 하나라도 참이면 단순 구현으로 진행하지 않고 architecture impact를 판정한다.

- Remote MCP의 public tool, scope, OAuth 또는 trust boundary 변경
- 데이터 SSOT, grain, natural key, retention, lineage 또는 destructive migration 변경
- 새 저장소, 외부 provider, Cloud service, 상시 process 또는 network hop 추가
- 월비용 단계, SLO, RPO/RTO, 개인정보·secret 정책 변경
- module 의존 방향, source/application/adapter 책임 또는 public response 호환성 변경
- 기존 ADR을 폐기·대체하거나 승인된 비목표를 제품 범위로 전환

영향이 없으면 Work Item에 `architecture_impact: none`과 근거를 남긴다. 영향이 있으면 관련 ADR이
`approved` 상태가 되기 전 production code나 infrastructure를 바꾸지 않는다.

## 6. Work Item Lifecycle

```text
feedback
  → intake
  → evidence/reproduction
  → classification and contract comparison
  → decision/approval when required
  → ready
  → in_progress
  → verified
  → stabilizing when operational evidence is required
  → owner acceptance
  → closed
```

Work Item 허용 상태는 `proposed`, `ready`, `in_progress`, `verified`, `stabilizing`, `closed`와 side state
`blocked`, `rejected`다.

- repository에는 동시에 하나의 `in_progress` 구현 Work Item만 둔다.
- `verified`는 승인된 코드·계약·자동 검사와 통제된 검증이 끝났다는 뜻이다. 시간축 운영 증거나 사용자
  정보가치 인수가 필요하면 완료가 아니라 `stabilizing`으로 간다.
- `stabilizing`은 production 또는 production-equivalent 경로가 실사용 중이며 정해진 관찰창, 품질·전송
  증거, rollback 준비와 owner acceptance를 모으는 상태다. 여러 항목이 동시에 `stabilizing`일 수 있지만
  구현 WIP 한도에는 포함하지 않는다.
- 운영 증거가 필요 없는 repository-only 작업은 `verified`에서 바로 `closed`할 수 있다. 필요한 작업은
  `stabilization_window`, `stabilization_exit_refs`, `rollback_plan`과 `## Stabilization plan` 없이는
  `stabilizing`이 될 수 없다.
- read-only 조사나 사용자 질문은 파일 변경이 없으면 Work Item 없이 수행할 수 있다.
- 긴 조사와 구현을 분리할 때 조사 결과는 evidence로 연결하고, 구현만 WIP 제한에 포함한다.
- blocked 항목은 blocking condition과 재개 조건을 기록한다.
- closed 항목은 acceptance, 테스트, 운영 증거와 남은 후속 작업을 명시한다.
- `user_visible_impact: yes`인 신규 Work Item은 `real_use_acceptance: required`와 실제 client/transport 증거
  참조를 가져야 `closed`가 될 수 있다. 자동 테스트, deployment run 또는 health check만으로 대체할 수
  없으며, 미래 scheduler slot을 기다리는 것이 유일한 인수 방법이어서는 안 된다.
- 큰 작업은 `docs/work-items/WI-NNN-*.md`, 일반 작업은 GitHub Issue를 canonical tracker로 쓴다.
- `WI-NNN`은 한 번 할당하면 완료 여부와 무관하게 삭제·재사용·재번호화하지 않는다. 다음 번호는 현재
  최댓값 다음 번호이며 빈 번호를 메우지 않는다.
- 실행 우선순위와 의존관계는 Work Item 번호가 아니라 milestone registry의 `sequence`와 `depends_on`으로
  표현한다. 순서 변경은 milestone revision log에 남기며 ID를 바꾸지 않는다.
- 기존 outcome 안에서 발견한 작업은 `WI-NNN-SNN` sub-item으로 추가한다. 독립적으로 승인·검증·rollback할
  수 있거나 outcome을 넓히면 최댓값 다음의 새 Work Item을 할당하고 `parent_id` 또는 `discovered_from`으로
  연결한다.
- `ready`, `in_progress`, `verified`, `closed`가 된 Work Item의 identity와 outcome은 새 작업을 흡수하기 위해
  바꾸지 않는다. 교정이 필요하면 새 Work Item과 `supersedes` 관계를 사용한다.
- 계획된 Work Item도 `docs/work-items/` 파일과 milestone registry에 함께 등록한다. 요구·설계 항목이 아직
  Work Item으로 기준선화되지 않았다면 delivery backlog로 남기고 번호를 선점하지 않는다.

필수 Work Item 내용은 `docs/work-items/TEMPLATE.md`를 따른다.

### 6.1 Recovery loop and immutable history

계획 의존성은 재현 가능한 순서 계산을 위해 계속 DAG여야 하지만 실제 운영 수명주기는 feedback loop다.
rollback은 과거 상태·증거·release를 삭제하거나 milestone을 과거 상태로 되감는 동작이 아니다.

1. incident의 run ID, release digest, 영향과 판단 근거를 먼저 보존한다.
2. 승인된 rollback plan으로 영향 경로를 비활성화하거나 마지막 안전 release를 복원한다.
3. 기존 milestone과 parent Work Item은 `stabilizing`에 둔다.
4. 동일 outcome의 작은 보정은 새 sub-item, 독립 acceptance/rollback이 필요한 보정은 새 Work Item으로
   append하고 `discovered_from`, 필요 시 `rollback_of` 또는 `supersedes`를 기록한다.
5. 새 보정 작업 하나만 `in_progress → verified → stabilizing/closed`로 진행한다.
6. 회복 release와 새 관찰 증거가 exit 기준을 만족하면 parent/milestone을 닫는다.

안정화 중 보정 Work Item은 `work_lane: stabilization_recovery`를 선언한다. `defect`, `incident`,
`maintenance`, `governance` 중 하나여야 하고 기존 Work Item을 `discovered_from`, `rollback_of` 또는
`supersedes`로 가리켜야 한다. 이는 새 제품 범위나 architecture outcome을 안정화 작업으로 위장하는 통로가
아니다. milestone을 `in_progress`로 되감거나 보정마다 새 milestone을 만들지 않으며 단일 구현 WIP 제한은
그대로 적용한다.

`depends_on`만 cycle 검사와 실행 선후관계에 참여한다. `discovered_from`, `rollback_of`, `supersedes`는
존재하는 Work Item을 가리키는 append-only feedback 관계이며 위상정렬 입력이 아니다. 따라서 운영상
`build → use → defect → rollback → correct → verify → use` loop를 표현하면서도 계획 DAG를 깨뜨리지 않는다.

### 6.2 Milestone baseline

`governance/project/milestones.toml`은 milestone, Work Item identity, design delivery ref, dependency와 sub-item
관계의 machine-readable SSOT다. 발급된 V2 delivery ID는 레지스트리 옆
[식별자 목록](../../governance/project/delivery-identities.md)에 보존한다. `docs/milestones/`는
인수 범위와 한계를 설명하고, 구축 당시 계획과 증거는 고정된 원문으로 연결한다. 새 delivery 기준선은
목적·인수 조건·순서 변경 사유를 해당 마일스톤 기록에 남긴다. Work Item 본문은 실행 상태와 증거의 SSOT이고
`docs/traceability.md`는 요구→결정→작업→증거 연결을 제공한다.

새 요구나 조사 결과가 생기면 다음 순서로 처리한다.

1. 기존 Work Item outcome 안인지 판정한다.
2. 안이면 다음 sub-item 번호를 append하고 parent acceptance에 미치는 영향을 기록한다.
3. 아니면 가장 큰 Work Item 번호 다음 ID를 발급한다. 기존 계획 항목은 이동하거나 재번호화하지 않는다.
4. dependency/sequence 변경은 milestone revision log에 이유와 영향을 남긴다.
5. registry, Work Item, traceability를 같은 변경에서 갱신한다.

### 6.3 Milestone lifecycle and overlap gates

이 절은 활성 delivery 기준선을 진행할 때 적용한다. 인수 후 운영 작업은 §6.4의 교정 경로를 적용한다.

Milestone 상태는 `proposed → ready → in_progress → stabilizing → closed`이며 `blocked`, `rejected`는 side
state다. milestone에는 구조적 `depends_on`과 별도로 각 dependency를 정확히 한 번 포함하는 두 gate가 있다.

- `implementation_gate`: 선행 milestone이 최소 `stabilizing`이면 후속 milestone을 `ready`로 만들 수 있다.
  후속 milestone은 첫 구현 Work Item이 시작되면 `in_progress`로 전환하고, 선행 milestone의 안정화가 끝날
  때까지 멈추지 않고 dependency 순서에 따라 격리 구현·fixture·local 또는 production-equivalent 비활성
  검증을 계속한다. 한 번에 하나의 구현 Work Item만 `in_progress`일 수 있다.
- `overlap_mode = "continuous_isolated"`: `overlap_work_item_ids`는 단발성 예외가 아니라 production gate가
  닫힌 동안 격리 단계로 진행할 수 있는 현재 milestone의 reviewed phase allowlist다. 각 Work Item은 활성화
  시점의 `execution_scope: isolated`, `production_effects: none`을 가져야 하며 dependency Work Item은 최소
  `verified`여야 한다. repository 검증이 끝난 Work Item은 `verified`에 둘 수 있고, 후속 dependency는 이를
  구현 입력으로 사용할 수 있다.
- `production_gate`: 선행 milestone이 `closed`여야 production DB migration, external source activation,
  Scheduler/Cloud Run 변경, public MCP surface, traffic cutover, destructive cleanup을 실행할 수 있다.

후속 milestone이 `stabilizing` 또는 `closed`가 되려면 production gate도 충족해야 한다. overlap allowlist는
작업 outcome 전체의 조기 production 권한이 아니라 현재 격리 구현 단계만 승인한다. `execution_scope`와
`production_effects`는 Work Item 전체의 잠재 영향이 아니라 **현재 실행 단계**를 나타낸다. production
gate가 열린 뒤 실제 effect를 시작할 때 frontmatter와 증거를 갱신하며, 이미 `verified`인 구현은 승인된
release/migration 뒤 `stabilizing`으로 진행할 수 있다. checker는 production gate가 닫혀 있는 동안 모든
상태의 Work Item에서 명시된 production effect를 거부한다. `blocked`인 선행 milestone은 gate 진전으로
계산하지 않는다.

지속적 overlap은 Work Item dependency를 완화하지 않는다. 선행 Work Item이 `proposed`, `ready`,
`in_progress`, `blocked` 또는 `rejected`이면 그에 의존하는 구현은 시작할 수 없다. 안정화 중 선행 기능의
중대한 결함이 발견되면 append-only recovery 작업이 우선하며 필요하면 후속 구현을 `blocked`로 전환한다.

### 6.4 Stabilization exit and steady-state operations

Milestone은 유한한 delivery·acceptance 단위이고 운영은 지속적인 feedback cycle이다. `stabilizing` milestone은
다음 조건을 모두 만족할 때만 `closed`가 된다.

1. 선언한 관찰창·표본과 `stabilization_exit_work_item_ids`의 증거가 충족된다.
2. outcome을 무효화하는 미해결 결함이 없다.
3. rollback 준비와 인계할 운영 monitor·owner가 확인된다.
4. 사용자 노출 outcome이면 실제 승인 client/transport의 증거와 owner acceptance가 있다.

`closed`는 운영 종료가 아니라 승인된 outcome과 당시 증거의 immutable handoff다. 이후 발견된 동일 outcome의
결함은 milestone을 되열거나 새 milestone을 자동 생성하지 않고 `work_lane: operations`인 corrective Work
Item으로 append한다. 이 Work Item은 `defect`, `incident`, `maintenance`, `governance` 중 하나이고 기존 Work
Item으로의 feedback 관계를 가져야 한다. 새 제품 범위, 별도 acceptance/rollback 경계 또는 새로운 dependency
gate가 필요할 때만 새 milestone을 제안하며 owner 승인 전에 기준선화하지 않는다.

## 7. Change Set 계약

모든 구현 변경은 다음을 판정한다.

1. 관련 요구사항과 ADR
2. architecture/data/security/deployment 문서 영향
3. schema migration, backup과 rollback 영향
4. public MCP와 source contract 영향
5. 비용·SLO·민감정보 영향
6. 자동 테스트와 실제 운영 증거
7. traceability와 종료 조건

영향이 없다는 결론도 Work Item/PR에 `none`과 이유를 남긴다. source, collection basket, dataset, metric,
pipeline 또는 DB 변경은 `docs/governance/data-governance-harness.md`를 먼저 적용하고, 물리 DB 변경은
`docs/data-catalog.md`의 Change Contract도 따른다.

## 8. 공통 하네스와 Gate

`scripts/check.sh`가 로컬·Skill·CI의 단일 검사 entrypoint다.

| Mode | 용도 | 기본 검사 |
| --- | --- | --- |
| `staged` | commit 직전 | staged whitespace, Project OS, data governance, architecture, warehouse contract |
| `quick` | 작업 중 | Project OS, data governance, architecture, warehouse, MCP surface, V2 문서 분류·탐색, shell/JSON |
| `full` | push/PR | quick + 전체 pytest + tracked diff check |

- `.githooks/pre-commit`은 `staged`, `.githooks/pre-push`는 `full`을 실행한다.
- CI는 별도 명령을 복제하지 않고 `bash scripts/check.sh full`을 실행한다.
- hook은 로컬 조기 피드백이며 우회 가능하다. CI와 release approval이 최종 gate다.
- live inventory, migration, restore, remote smoke와 비용 검증은 release Work Item이 요구할 때 별도 실행한다.

### 8.1 Real-use acceptance gate

신규 Work Item은 `user_visible_impact`, `real_use_acceptance`, `real_use_evidence_refs`를 선언한다. 역사적으로
닫힌 Work Item을 소급 개작하지 않고 WI-061 이후 항목부터 checker가 다음을 강제한다.

- public MCP, Telegram, report, dashboard, CLI output처럼 사용자가 결과를 직접 소비하면
  `user_visible_impact: yes`, `real_use_acceptance: required`다.
- 실제 승인 client와 production 또는 production-equivalent transport로 최소 positive와 해당 기능에
  가능한 partial/error 경계를 즉시 호출한다. fixture는 clock/source 결손을 재현하고, live call은 adapter,
  인증, 직렬화와 실제 데이터 가용성을 함께 검증한다.
- 실사용 결과는 `usable`, `degraded_but_usable`, `unavailable`을 구분하며, unavailable 도구를 transport
  성공만으로 완료 처리하지 않는다.
- 발견 항목은 `defect`, `clarification`, `data/operations gap`, `approved-inactive scope`, `accurate degraded
  behavior`로 분류한다. 해결하지 않는 항목도 명시적 후속 Work Item·sub-item·승인된 비목표 중 하나를
  소유자로 가져야 한다.
- user-visible Work Item은 `real_use_evidence_refs`가 `pending` 또는 `none`인 채 `closed`가 될 수 없다.
  사용자 노출이 없으면 `not_applicable` 사유를 Work Item의 `## Real-use acceptance`에 기록한다.
- scheduled behavior도 deterministic no-send/fixture/manual trigger를 먼저 제공한다. 실제 시간축 수신 증거가
  추가로 필요할 수는 있지만 “다음 슬롯까지 대기”만을 테스트 계획으로 삼지 않는다.

## 9. Agent/Skill 계약

repository 변경이나 비사소한 triage를 시작하는 agent는 `.agent/skills/kis-project-os/SKILL.md`를 먼저
읽는다. 해당 Skill은 이 문서를 정책 SSOT로 사용하고 작업 성격에 따라 data governance, architecture,
warehouse, MCP, API capability 또는 release Skill을 추가로 읽는다. source·collection·dataset·metric·pipeline
변경은 `.agent/skills/kis-data-governance/SKILL.md`와 그 canonical 정책을 먼저 적용한다.

Skill은 사용자 승인 없이 다음을 하지 않는다.

- 요구사항·ADR을 승인 상태로 바꾸기
- infrastructure provisioning·배포·외부 메시지 전송
- 데이터 삭제·대량 backfill·credential 변경
- 실패한 검사를 통과시키려고 계약을 완화하기

## 10. 운영 Feedback Loop

- 운영 실패는 로그·run id·dataset freshness를 먼저 보존하고 추측보다 증거를 우선한다.
- incident 완화와 영구 수정은 별도 Work Item이 될 수 있다.
- 월간: 비용·capacity·unmanaged drift·data contract lifecycle·오래된 Work Item 검토
- 분기: backup restore rehearsal, source/API/license와 권한 검토
- release 후: smoke와 관찰기간을 거쳐 acceptance evidence 기록
- 반복되는 결함은 단순 패치로 끝내지 않고 contract/harness 누락 여부를 재분류한다.
- rollback 뒤에는 milestone 상태를 되감지 않고 6.1의 append-only corrective loop를 적용한다. 구조적
  dependency를 역방향으로 추가해 cycle을 만드는 방식으로 recovery를 표현하지 않는다.

정기 실행을 자동화할 때도 이 문서가 schedule과 권한을 승인하지는 않는다. 실제 automation 생성은 별도
사용자 요청과 비용·notification 정책을 따른다.

## 11. Project OS 변경 절차

1. governance Work Item을 만든다.
2. 실패 사례 또는 유지보수 목적을 기록한다.
3. 정책 변경인지 검사 구현 변경인지 분리한다.
4. 사용자 결정이 필요한 정책은 승인 후 문서를 바꾼다.
5. Skill, script, hook과 CI를 같은 검사 entrypoint에 맞춘다.
6. Project OS checker와 전체 suite를 실행한다.
7. 실제 Work Item 하나에 적용해 dogfood evidence를 남긴다.

편의 때문에 gate를 영구 삭제하지 않는다. 과도한 gate는 제거 대신 위험 기반 mode나 실행 시간을 먼저
조정한다.
