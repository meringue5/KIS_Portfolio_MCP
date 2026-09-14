# MS-004 — V2 canonicalization and V1 retirement

> 상태: in_progress; project delivery의 final milestone
> 선행 milestone: MS-003
> machine registry: `governance/project/milestones.toml`

## Outcome

V2 cutover 뒤 V1 runtime·data consumer·문서 잔존물을 검증 가능한 방식으로 퇴역시키고, 보존할 역사와 현재
운영 정본을 구분하여 V2 문서·계약·runbook 하나를 프로젝트의 canonical baseline으로 만든다.

## Baseline

| Sequence | Work Item | Design refs | Depends on | 상태 / 결과 |
| ---: | --- | --- | --- | --- |
| 1 | WI-047 V1 public-surface retirement | V2-W0801/0802 | WI-046 | closed; local/setup/public activation paths retired, internal history preserved |
| 2 | WI-048 V1 main consumer transition | V2-W0803 | WI-046 | closed; protected reference transition, restore and owner-observed canonical Remote read passed |
| 3 | WI-049 V1 runtime resource cleanup | V2-W0804 | WI-047 | closed; 11 obsolete Job definitions and 59 separately approved untagged digests removed with runtime/history/recovery preservation |
| 4 | WI-050 steady-state operations runbooks | V2-W0805 | WI-047, WI-048 | proposed |
| 5 | WI-051 final V2 architecture audit | V2-W0806 | WI-047~050 | proposed |
| 6 | WI-032 V2 canonical documentation | V2-W0807 | WI-051 | proposed; final documentation gate |

WI-032는 문서 정본화 outcome만 소유하며 live resource 삭제를 자동으로 포함하지 않는다. 실제 resource
cleanup은 WI-049의 명시적 inventory, 복구 증거와 별도 파괴적 변경 승인 아래에서만 수행한다.

## Implementation and production gates

- implementation gate: MS-003가 최소 `stabilizing`이면 MS-004를 `in_progress`로 열 수 있다. registry에서
  검토된 Work Item은 dependency 순서와 단일 `in_progress` 제한 아래 repository 구현·fixture·local 또는
  inactive verification을 연속 수행해 `verified`까지 전진할 수 있다.
- production gate: MS-003가 `closed`이기 전에는 public V1 surface retirement, compatibility migration,
  runtime resource cleanup, canonical production switch와 final cutover effect를 수행할 수 없다.

## Acceptance gate

- V2-W0801~0806의 retirement/audit evidence와 MS-003 cutover evidence가 닫혀 있다.
- architecture, requirements/decisions, MCP, data, security, deployment, recovery, cost와 onboarding의 현재
  문서가 V2 정본 하나를 가리킨다.
- V1 문서는 역사 보존, superseded redirect 또는 승인된 삭제 대상으로 전수 분류된다.
- 새 clone, Remote MCP/iPhone 연결과 운영 runbook을 문서대로 재현한다.
- destructive resource/data deletion은 별도 승인과 복구 증거 없이는 수행하지 않는다.

## Revision log

| Version | Date | Change | Identity impact |
| --- | --- | --- | --- |
| 2026-09-14.13 | 2026-09-14 | Closed WI-049 and S03 after exact Artifact Registry cleanup and preservation checks | 59 approved untagged digests removed; exact 49-digest retain set, active runtime, 15 history baselines and private recovery index passed; WI-050 is next |
| 2026-09-14.12 | 2026-09-14 | Activated WI-049-S03 production phase after owner approved all 59 exact untagged digests | Apply is limited to the merged specification; tag, data, backup, IAM, Scheduler, Secret, service and active V2 changes remain forbidden |
| 2026-09-14.11 | 2026-09-14 | Activated WI-049-S03 exact-digest specification in isolated read-only scope | Artifact Registry mutation remains disabled until a separate owner approval names exact digests |
| 2026-09-14.10 | 2026-09-14 | Closed WI-049-S02 after exact production deletion and post-cleanup protection checks | Exactly 11 approved Job definitions removed; 15 history objects, active runtime, backup and images preserved; S03 remains separately gated |
| 2026-09-14.9 | 2026-09-14 | Activated WI-049-S02 production phase after owner approved all 11 exact Job names | Only those unscheduled one-time Job definitions may be deleted; data, backup, image, IAM, Scheduler, Secret and service exclusions unchanged |
| 2026-09-13.8 | 2026-09-13 | Verified WI-049-S01 cleanup readiness without production mutation | 11 unscheduled Job candidates, 15 protected data baselines, 19 protected resources and exact private recovery index are frozen; apply remains disabled |
| 2026-09-13.7 | 2026-09-13 | Activated WI-049 in isolated read-only inventory phase | Databases, portfolio/trade history and backups remain protected; no deletion authorized |
| 2026-09-13.6 | 2026-09-13 | Closed WI-048 after protected production transition and owner-observed canonical Remote read passed | V2 is the sole canonical path; retained V1 cleanup remains separately gated by WI-049 |
| 2026-09-13.5 | 2026-09-13 | Closed WI-047 and activated isolated WI-048 | V2-only public surface is canonical; destructive data/runtime cleanup remains excluded |
| 2026-09-13.4 | 2026-09-13 | Opened MS-004 and activated WI-047 after owner accepted V2-only production | MS-003 and WI-046 closed under DEC-056/ADR-028; one isolated Work Item active, destructive cleanup remains WI-049 |
| 2026-09-10.3 | 2026-09-10 | Added continuous isolated implementation overlap at MS-003 stabilizing while preserving MS-003 closed for retirement and cleanup effects | Work Item identities and dependencies unchanged |
| 2026-08-28.2 | 2026-08-28 | V2-W0801~0806을 WI-047~051로 배정하고 WI-032를 최종 문서 gate로 연결 | 신규 WI append; WI-032 identity 불변 |
| 2026-08-28.1 | 2026-08-28 | final MS-004와 WI-032 문서 정본화 작업을 최초 기준선화 | 기존 WI 변경 없음; WI-032 신규 발급 |
