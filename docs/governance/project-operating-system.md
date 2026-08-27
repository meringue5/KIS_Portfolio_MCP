# KIS Portfolio Project Operating System

> 정식 명칭: Project Operating System
> 한국어 명칭: 프로젝트 운영체계
> 약칭: Project OS
> 상태: 승인·활성
> 기준일: 2026-08-27
> 소유 범위: 요구·결정·작업·검증·배포·운영 피드백의 개발 운영체계

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

## 3. 권한과 Source of Truth

| 책임 | Canonical source | 변경 권한 |
| --- | --- | --- |
| 제품 목적·사용자 동작·인수 기준 | `docs/requirements/`의 승인된 DEC | 사용자 승인 |
| 장기 architecture decision | `SPEC.md`의 승인 ADR | 사용자 승인 |
| 현재·목표 코드/신뢰 경계 | `ARCHITECTURE.md`와 승인된 design 문서 | ADR/Work Item에 따라 변경 |
| 데이터 객체·grain·key·민감도 | `docs/data-catalog.md` + `db/catalog.py` | warehouse change contract |
| 보안·secret·token | `docs/security-and-secrets.md` | security review |
| 배포·rollback | `docs/deployment.md` + versioned manifest | release approval |
| Project OS 정책 | 이 문서 | 사용자 승인 또는 비의미적 정비 |
| 변경 접수·진행 상태 | GitHub Issue; 로컬 bootstrap은 `docs/work-items/` | maintainer triage |
| 요구→구현→증거 연결 | `docs/traceability.md` | Work Item과 같은 변경 |
| 임시 우선순위 메모 | `TODO.md` | 편집 가능; 결정·상태 SSOT 금지 |

충돌 시 더 구체적인 canonical 문서가 우선하지만 상위 사용자 요구나 승인 ADR을 위반할 수 없다. 충돌을
발견하면 임의로 하나를 선택하지 않고 Issue/Work Item에 기록해 계약을 먼저 정리한다.

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
  → automated verification
  → operational evidence when required
  → accepted
  → closed
```

허용 상태는 `proposed`, `ready`, `in_progress`, `blocked`, `verified`, `closed`, `rejected`다.

- repository에는 동시에 하나의 `in_progress` 구현 Work Item만 둔다.
- read-only 조사나 사용자 질문은 파일 변경이 없으면 Work Item 없이 수행할 수 있다.
- 긴 조사와 구현을 분리할 때 조사 결과는 evidence로 연결하고, 구현만 WIP 제한에 포함한다.
- blocked 항목은 blocking condition과 재개 조건을 기록한다.
- closed 항목은 acceptance, 테스트, 운영 증거와 남은 후속 작업을 명시한다.
- 큰 작업은 `docs/work-items/WI-NNN-*.md`, 일반 작업은 GitHub Issue를 canonical tracker로 쓴다.

필수 Work Item 내용은 `docs/work-items/TEMPLATE.md`를 따른다.

## 7. Change Set 계약

모든 구현 변경은 다음을 판정한다.

1. 관련 요구사항과 ADR
2. architecture/data/security/deployment 문서 영향
3. schema migration, backup과 rollback 영향
4. public MCP와 source contract 영향
5. 비용·SLO·민감정보 영향
6. 자동 테스트와 실제 운영 증거
7. traceability와 종료 조건

영향이 없다는 결론도 Work Item/PR에 `none`과 이유를 남긴다. DB 변경은
`docs/data-catalog.md`의 Change Contract를 추가로 따른다.

## 8. 공통 하네스와 Gate

`scripts/check.sh`가 로컬·Skill·CI의 단일 검사 entrypoint다.

| Mode | 용도 | 기본 검사 |
| --- | --- | --- |
| `staged` | commit 직전 | staged whitespace, Project OS, architecture, warehouse contract |
| `quick` | 작업 중 | Project OS, architecture, warehouse, MCP surface, shell/JSON |
| `full` | push/PR | quick + 전체 pytest + tracked diff check |

- `.githooks/pre-commit`은 `staged`, `.githooks/pre-push`는 `full`을 실행한다.
- CI는 별도 명령을 복제하지 않고 `bash scripts/check.sh full`을 실행한다.
- hook은 로컬 조기 피드백이며 우회 가능하다. CI와 release approval이 최종 gate다.
- live inventory, migration, restore, remote smoke와 비용 검증은 release Work Item이 요구할 때 별도 실행한다.

## 9. Agent/Skill 계약

repository 변경이나 비사소한 triage를 시작하는 agent는 `.agent/skills/kis-project-os/SKILL.md`를 먼저
읽는다. 해당 Skill은 이 문서를 정책 SSOT로 사용하고 작업 성격에 따라 architecture, warehouse, MCP,
API capability 또는 release Skill을 추가로 읽는다.

Skill은 사용자 승인 없이 다음을 하지 않는다.

- 요구사항·ADR을 승인 상태로 바꾸기
- infrastructure provisioning·배포·외부 메시지 전송
- 데이터 삭제·대량 backfill·credential 변경
- 실패한 검사를 통과시키려고 계약을 완화하기

## 10. 운영 Feedback Loop

- 운영 실패는 로그·run id·dataset freshness를 먼저 보존하고 추측보다 증거를 우선한다.
- incident 완화와 영구 수정은 별도 Work Item이 될 수 있다.
- 월간: 비용·capacity·unmanaged drift·오래된 Work Item 검토
- 분기: backup restore rehearsal, source/API/license와 권한 검토
- release 후: smoke와 관찰기간을 거쳐 acceptance evidence 기록
- 반복되는 결함은 단순 패치로 끝내지 않고 contract/harness 누락 여부를 재분류한다.

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
