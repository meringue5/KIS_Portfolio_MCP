# MS-008 — Real-use MCP acceptance and capability remediation

> 상태: in_progress
> 선행 milestone: MS-005 closed
> machine registry: `governance/project/milestones.toml`

## Outcome

User-visible functionality is not called complete merely because code, CI or deployment passed. The actual OAuth
Remote MCP client must execute deterministic positive, partial and error scenarios, and defects or honest capability
gaps found there must be classified and routed to an owned follow-up.

## Baseline

| Sequence | Work Item | Depends on | Status |
| ---: | --- | --- | --- |
| 1 | WI-061 real-use completion gate | none | closed |
| 2 | WI-062 direct Remote MCP remediation | WI-061 | closed |
| 3 | WI-063 incremental trade-event collection | WI-062 | stabilizing |
| 4 | WI-064 trade-event business-key deduplication | WI-063 | proposed |
| 5 | WI-065 Claude asset-change MCP recovery | WI-063 | stabilizing |
| 6 | WI-066 legacy total-asset history quality recovery | WI-065 | stabilizing |

## Gates

- Implementation and production gates depend on closed MS-005, the canonical V2 production baseline.
- WI-061 changes Project OS policy, template and deterministic checker, then dogfoods the rule on WI-062.
- WI-062 separates actual defects from accurate degraded results and inactive capability scope. No source activation,
  backfill or public-catalog removal is implied by registering the Work Item.
- WI-063 owns the newly proven contract/implementation gap: the recurring core pipeline declares trade-event output
  but does not increment the trade ledger or its source coverage watermark after the one-time backfill.
- WI-064 preserves a separate correctness finding from WI-063 real-use evidence: the current trade view contains
  repeated business-key groups that require source-grounded identity analysis before any deduplication.
- WI-065 owns the next owner-Claude workflow finding: no-argument pipeline status raises before the owner-debug
  boundary, and the retained Claude tag still serves a pre-fix revision whose quality vocabulary reverses current
  `pass` rows into false `degraded` history.
- WI-066 owns the independent longitudinal-data finding discovered after WI-065: retained V1 aggregate rows preserve
  an overseas-feeder-zero interval, while the migration can infer `pass` from non-null remaining holdings and expose
  the incomplete total as an apparent drawdown.
- Completion requires immediate reproducible client calls; waiting for a future scheduler slot cannot be the only
  acceptance method.

## Revision log

| Version | Date | Change | Identity impact |
| --- | --- | --- | --- |
| 2026-09-23.1 | 2026-09-23 | Direct Codex calls showed that deployed tools can be healthy, degraded, empty or response-contract defective despite green CI | Create MS-008, WI-061 and WI-062 without changing earlier milestone identities |
| 2026-09-23.2 | 2026-09-23 | WI-061 checker regression and full 783-test gate passed; WI-062 declares the new real-use fields | Close WI-061 and start WI-062 as the sole implementation Work Item |
| 2026-09-23.3 | 2026-09-23 | Production rows ended 2026-08-25 and backfill watermark ended 2026-08-28 while current core runs omit trade collection | Register WI-063; keep WI-062 response correction active and do not claim September no-trade coverage |
| 2026-09-23.4 | 2026-09-23 | PR #135, deploy run 35868121973 and six-call direct Codex OAuth replay passed the corrected positive, partial and error contracts | Keep WI-062 stabilizing until owner acceptance; WI-063 remains proposed for collection restoration |
| 2026-09-24.1 | 2026-09-24 | Owner accepted the WI-062 replay and approved the next work; independent incremental trade collection was selected to prevent trade-source failure from blocking portfolio capabilities | Close WI-062 and start WI-063 as the sole implementation Work Item |
| 2026-09-30.1 | 2026-09-30 | Initial replay and direct Codex OAuth positive/partial/error calls passed, but stabilization found four consecutive overseas schedule failures caused by legacy and new jobs refreshing the same KIS credential at 07:35 through separate state stores | Keep WI-063 in progress; open WI-063-S01, pause both legacy trade schedulers as recoverable containment, and verify durable cutover plus immediate/recurring overseas recovery |
| 2026-09-30.2 | 2026-09-30 | PR #138 and protected run 36595665194 made scheduler cutover fail-closed; only the two new schedules are enabled, immediate overseas execution `...-vnmvk` succeeded, and direct Codex OAuth positive/partial/error plus unaffected-overview scenarios passed | Move WI-063 and WI-063-S01 to stabilizing; retain the pre-cutover failed pipeline row as honest history and await bounded recurring evidence plus owner acceptance |
| 2026-09-30.3 | 2026-09-30 | Owner Claude asset-change use found no-argument pipeline status failing generically and all history falsely degraded; logs proved the first is an unhandled selector validation error and the second is served by stale `wi046-v2` revision `00048` with reversed `passed` versus current `pass` semantics | Start WI-065 test-first as the sole implementation item; keep WI-064 proposed and do not mutate production until the tested release is approved |
| 2026-09-30.4 | 2026-09-30 | Five exact regressions failed before implementation; no-selector default, mixed `pass`/`passed` normalization and stable/tag atomic release guard then passed 158 focused and 799 full tests, plus a patched-code production read returned 60 pass and six honestly degraded history groups | Move WI-065 to verified; request a protected Remote-only release before stabilizing and actual Claude/Codex replay |
| 2026-09-30.5 | 2026-09-30 | The owner approved the protected WI-065 production release after PR #140 merged with green CI | Permit only the Remote image, stable traffic and retained `wi046-v2` compatibility tag to move together; require immediate actual-client replay and rollback on smoke failure |
| 2026-09-30.6 | 2026-09-30 | PR #141/master `485dac0` and protected run `36664435767` deployed Remote `00057-52l`; stable traffic and `wi046-v2` now share the revision, smoke passed, and direct Codex OAuth positive/partial/error plus unaffected reads passed | Move WI-065 to stabilizing; await owner replay of the original Claude prompt before acceptance and closure |
| 2026-10-05.1 | 2026-10-05 | Ecological longitudinal use and read-only MotherDuck inspection proved that retained V1 totals from 2026-07-24 through 2026-09-04 omit overseas assets, while physical backfill reconciliation and row-level null checks can still produce false `pass` history | Register independent WI-066 discovered from WI-065; preserve all source rows, start no production correction, and require source-grounded fail-closed recovery plus actual-client acceptance |
| 2026-10-07.1 | 2026-10-07 | The owner approved proceeding with the separated data-defect Work Item | Start WI-066 as the sole `in_progress` implementation item; limit the phase to deterministic fixtures, fail-closed read behavior and read-only production profiling, with no production data mutation or deployment |
| 2026-10-07.2 | 2026-10-07 | View-only migration 0020, the matching Remote projection and future-backfill labels passed immediate MCP positive/partial/error fixtures, quick gates and 803 full tests; a direct production Codex baseline still returned the 6/20 legacy total as `pass` because no release occurred | Keep WI-066 in progress; request separate production migration/release approval, then require post-release Codex and owner-Claude replay before stabilization |
| 2026-10-08.1 | 2026-10-08 | The owner explicitly approved the complete WI-066 PR, private backup/restore, view-only migration, Remote release and immediate MCP validation process | Add one protected `wi066` target; require migration and both restore checks before moving stable and `wi046-v2`, preserve source rows and keep source replay outside the approval |
| 2026-10-08.2 | 2026-10-08 | Protected run 37643171197 created and restored its pre-backup and applied view-only 0020, then exhausted the platform-default 512Mi transition-Job memory during later recovery work before Remote update; original rows and serving routes remained unchanged | Keep WI-066 in progress, set an explicit bounded 2Gi Job memory limit with regression coverage, and repeat the resumable protected target rather than waiting for a scheduled slot |
| 2026-10-08.3 | 2026-10-08 | PR #145 and protected run 37693993263 succeeded at master f472a24: both 79-object backups restored, 3273 rows were fingerprint-preserved, all 27 legacy groups were quarantined, all 75 native groups validated, Remote 00058-5qk serves stable plus wi046-v2, and immediate Codex positive/partial/error plus overview/pipeline calls passed | Move WI-066 to stabilizing; require the owner to repeat the original longitudinal prompt in Claude before closure |
