# MS-006 — Scheduled collection and Telegram recovery

> 상태: closed; numeric report and distinct permanent-detail receipt accepted
> 선행 milestone: MS-005
> machine registry: `governance/project/milestones.toml`

## Outcome

Restore the scheduled 10:00 governed pipeline and the previously owner-accepted outbound Telegram alert and
total-asset report configuration without replaying historical messages or weakening the publish quality gate.

## Baseline

| Sequence | Work Item | Depends on | Status |
| ---: | --- | --- | --- |
| 1 | WI-059 scheduled core and Telegram recovery | WI-058, WI-055 | closed; numeric-report receipt/presentation accepted 2026-10-21 |
| 2 | WI-070 permanent held-position Telegram signals | WI-059 | closed; actual permanent-detail receipt accepted 2026-10-21 |
| 3 | WI-076 three-slot held-signal status | WI-070 | closed; all three 2026-10-19 reports succeeded and owner accepted receipt on 2026-10-21 |

## Gates

- implementation and production gates: MS-005 closed.
- release: protected master workflow with existing `wi055-s04` photo smoke and same-image three-Job deployment.
- exit: exact runtime configuration, successful post-release 10:00 collection and quality evidence, provider ledger,
  owner-visible total-asset and held-position signal behavior, plus explicit no-eligible-alert evidence where
  applicable. WI-070 is part of the exit because the approved signal rule had expired while transport remained healthy.

## Revision log

| Version | Date | Change | Identity impact |
| --- | --- | --- | --- |
| 2026-10-21.1 | 2026-10-21 | Closed WI-076 after the released Jobs sent the 2026-10-19 10:00, 14:30 and 16:00 reports and the owner confirmed all three receipts | Existing recovery outcome preserved; MS-006 remains stabilizing for its other declared exit items |
| 2026-10-13.1 | 2026-10-13 | Appended WI-070 after live logs proved all three Jobs and Telegram transport were healthy but the bounded production-value rule had expired, producing zero external candidates | Existing Telegram-recovery outcome preserved; no new milestone; unheld watchlist remains excluded |
| 2026-09-17.2 | 2026-09-17 | WI-059-S01 PR #120 and protected run `35172054518` corrected FX landing and report preflight; release is stabilizing, while owner rejected the all-or-nothing information design and opened WI-060/MS-007 | Recovery history preserved; new architecture outcome is separate and production-gated |
| 2026-09-17.1 | 2026-09-17 | Appended WI-059-S01 after the first post-release 10:00 run succeeded but the owner report was blocked by the missing 2026-09-16 same-slot state; read-only inspection also found ungoverned stale FX in pass-marked Gold | Parent remains stabilizing; one isolated corrective sub-item is in progress; no historical send replay |
| 2026-09-16.2 | 2026-09-16 | PR #118 passed CI and merged as `9c7d518`; protected run `35070642487` passed photo smoke and restored all three Jobs on one immutable image | No new identity; parent enters live stabilization without replaying 2026-09-16 messages |
| 2026-09-16.1 | 2026-09-16 | Opened WI-059 after the first post-release 10:00 run failed at price quality and the generic Job deployment removed Telegram delivery configuration | New append-only corrective milestone; MS-005 remains closed |

- 2026-10-21: WI-059/S01 closed on four numeric-report receipts and source/quality/hash reconciliation.
  WI-070 detail-signal acceptance remains independent; MS-006 stays stabilizing until its exit is complete.

## Accepted handoff — 2026-10-21

WI-059/S01 numeric report recovery and WI-070 permanent-detail signal delivery both have provider/runtime evidence
and direct owner receipt acceptance. Close MS-006 without rewinding earlier milestones. WI-076 regular summaries
were independently accepted; their receipt was not substituted for the exact WI-070 detail. Existing fixed Jobs,
quality gates, immutable rule and rollback controls transfer to ordinary operations; no missed message is replayed.
