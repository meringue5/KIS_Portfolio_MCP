# MS-006 — Scheduled collection and Telegram recovery

> 상태: stabilizing
> 선행 milestone: MS-005
> machine registry: `governance/project/milestones.toml`

## Outcome

Restore the scheduled 10:00 governed pipeline and the previously owner-accepted outbound Telegram alert and
total-asset report configuration without replaying historical messages or weakening the publish quality gate.

## Baseline

| Sequence | Work Item | Depends on | Status |
| ---: | --- | --- | --- |
| 1 | WI-059 scheduled core and Telegram recovery | WI-058, WI-055 | stabilizing; deployed, awaiting first post-release slots and owner receipt |

## Gates

- implementation and production gates: MS-005 closed.
- release: protected master workflow with existing `wi055-s04` photo smoke and same-image three-Job deployment.
- exit: exact runtime configuration, successful post-release 10:00 collection and quality evidence, provider ledger,
  and owner-visible Telegram receipt or explicit no-eligible-alert evidence.

## Revision log

| Version | Date | Change | Identity impact |
| --- | --- | --- | --- |
| 2026-09-17.1 | 2026-09-17 | Appended WI-059-S01 after the first post-release 10:00 run succeeded but the owner report was blocked by the missing 2026-09-16 same-slot state; read-only inspection also found ungoverned stale FX in pass-marked Gold | Parent remains stabilizing; one isolated corrective sub-item is in progress; no historical send replay |
| 2026-09-16.2 | 2026-09-16 | PR #118 passed CI and merged as `9c7d518`; protected run `35070642487` passed photo smoke and restored all three Jobs on one immutable image | No new identity; parent enters live stabilization without replaying 2026-09-16 messages |
| 2026-09-16.1 | 2026-09-16 | Opened WI-059 after the first post-release 10:00 run failed at price quality and the generic Job deployment removed Telegram delivery configuration | New append-only corrective milestone; MS-005 remains closed |
