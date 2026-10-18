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
| 3 | WI-063 incremental trade-event collection | WI-062 | closed; owner accepted 2026-10-19 |
| 4 | WI-064 trade-event business-key deduplication | WI-063 | stabilizing; production/actual OAuth verified, owner acceptance pending |
| 5 | WI-065 Claude asset-change MCP recovery | WI-063 | stabilizing |
| 6 | WI-066 legacy total-asset history quality recovery | WI-065 | stabilizing |
| 7 | WI-067 calendar-aware pipeline run status | WI-066 | closed |
| 8 | WI-068 retained legacy history recovery | WI-066 | stabilizing |

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
- WI-067 owns the independent pipeline-status defect discovered during WI-066 acceptance: a holiday/weekend-only
  empty lookback is reported as unavailable data because the read model ignores the governed market calendar and due
  slots.
- WI-068 owns the independent recovery decision exposed after WI-066 quarantine: retained pre-V2 data and backups may
  still support present longitudinal analysis, but must be inventoried and classified before choosing canonical V2
  compatibility import, governed noncanonical reference access or a bounded hybrid. Registration authorizes no
  restore, migration, API, deployment or production mutation.
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
| 2026-10-09.1 | 2026-10-09 | After the owner restored billing, PR #147/master cb83958 and protected run 37842065536 deployed the daily-only history schema to Remote 00059-d7z; direct Codex OAuth repeated the full owner question, returned truthful legacy gaps, current pass data, a working pipeline read and bounded validation errors without waiting for a slot | Move WI-066-S01 to stabilizing; retain owner-Claude same-question replay as the only remaining S01 acceptance exit |
| 2026-10-12.1 | 2026-10-12 | Owner-Claude showed that a three-day holiday/weekend-only pipeline window returns partial/unavailable while seven days returns nine successful runs; code inspection proved the read model never evaluates calendar or due slots | Register WI-067 as an independent defect and start it as the sole implementation Work Item; keep production effects gated |
| 2026-10-12.2 | 2026-10-12 | Four red regressions now distinguish no-runs-expected, scheduled-run-missing, calendar-unavailable and future same-day slots; additive read-model 1.2.0, actual MCP tool-boundary fixtures, quick gate and all 815 tests pass | Move WI-067 to verified; require protected release plus immediate Codex and owner-Claude replay before stabilizing |
| 2026-10-13.1 | 2026-10-13 | Owner clarified that pre-V2 application history remains in incompatible retained data/backups and approved Work Item definition so its present analytical value can be recovered without weakening WI-066 quarantine | Register WI-068 as proposed; allow read-only inventory and fixture design only, then require an owner-approved architecture decision before any restore, import, read model, API, deployment or production mutation |
| 2026-10-13.2 | 2026-10-13 | Owner approved DEC-062/ADR-033: 25 dated total-level references, external FX/zero-cash assumptions, two NULL unavailable totals, explicit MCP opt-in | WI-068 in_progress; isolated verification then protected additive import/Remote release; native state and WI-066 quarantine preserved |
| 2026-10-13.3 | 2026-10-13 | WI-068 protected migration/import/restore and actual Codex positive/partial/error passed; native state and quarantine preserved | WI-068 stabilizing; owner-Claude replay/acceptance remains |
| 2026-10-14.1 | 2026-10-14 | PR #149/merge `fa4a1ead`, protected run `38342496464`, Remote `00060-6ts`, direct Codex positive/real-partial/error and owner-Claude PASS completed WI-067 acceptance; owner noted slot-coverage versus run-health and evidence-time semantics plus non-blocking diagnostic limits | Close WI-067 independently of WI-068; clarify read-model 1.2.1 without changing runtime behavior, and retain per-run missing-coverage identity as a separately approved enhancement |

- 2026-10-18: owner prioritized existing WI-064 and approved its normal PR/CI/production release. The original shared checkout preserves blocked WI-072 and other uncommitted artifacts; they are not bundled in this isolated release. No identity/dependency renumbering or milestone rewind.

- 2026-10-18: WI-064 PR #166 / workflow 39105328346 applied the source-preserving 0022 projection repair. Direct OAuth 4→2 and production 300→281/19→0 reconcile; owner acceptance remains pending without replacing the Work Item or rewinding the milestone.

| 2026-10-19.1 | 2026-10-19 | Actual OAuth 2020 false pass exposed missing lower-bound and gap proof; WI-063-S02 validates exact source/quality/publish intervals and preserves watermark monotonicity | Append same-outcome corrective sub-item; verified repository phase, parent remains stabilizing; protected patch release and owner acceptance pending |

| 2026-10-19.2 | 2026-10-19 | Owner approved PR #168 merge and protected wi063-s02 release; run 39144314352 passed, both Remote routes converge and actual Codex OAuth passes 9/9 including 2020 partial | S02 stabilizing; parent/S01 preserve history and await owner result acceptance; no source replay, DDL or unrelated closure |

| 2026-10-19.3 | 2026-10-19 | Owner explicitly accepted deployed OAuth 9/9, bounded recurring sample and preserved source/failure evidence, and approved publishing closeout | Close WI-063/S01/S02 only; retain original identities and all failure history; MS-008 and unrelated acceptance gates remain unchanged |
