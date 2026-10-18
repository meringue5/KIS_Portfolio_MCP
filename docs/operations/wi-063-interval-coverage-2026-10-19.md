# WI-063-S02 interval coverage correction — 2026-10-19

The lower-bound false pass is fixed and deployed through the owner-approved protected release. Actual Codex OAuth
passes all nine post-release oracles. The owner explicitly accepted the corrected results and explained recurring
sample on 2026-10-19; WI-063, S01 and S02 are closed. The candidate/baseline sections below preserve pre-release evidence.

## Independent oracles and implementation

The frozen regression matrix initially produced 15 failures and four passes on unmodified master. The failures
included 2020 before-start, boundary crossing, internal gap, incomplete/wrong-source/quality/publish/lineage evidence
and borrowing account/market coverage. Four existing covered/upper-gap boundaries already passed.
Additional tests cover malformed proof, explicit interval disagreement, all five accounts, both overseas sources,
existing populated rows, covered empty, failed extension, historical evidence compatibility, recollection, SOR correction,
watermark non-regression and producer resume guards. Expectations are fixed from complete exact source coverage,
not from the implementation's observed output. Existing tests that formerly treated an upper watermark as proof
now construct actual source/publish evidence and retain their original positive/partial behavior.

`trade_coverage.py` reads only existing governed Control evidence. It accepts approved producer runs with exact
v1 account/product/type/market/operation/route/start/end keys, successful collection/quality/publish stages, both
passing trade quality rules, matching source lineage, complete pagination and reconciled source rows. It unions
adjacent intervals per operation and intersects every required operation per account/market. Every date must be
covered for every requested scope before empty **or populated** pass is possible. `coverage_partitions` adds
outer bounds and bounded uncovered intervals (first 20 plus count). Outer bounds never imply gap-free coverage.

Producer 1.0.3 adds explicit interval metadata to existing publish JSON. Retained older keys are checked against
the same complete proof chain. Query resume watermarks remain hints; older replays cannot reduce their value
or overwrite a later run ID. No rows, revisions, identities, reference links or historical failures are deleted.
WI-064 identity repair is unchanged. No new table, view, column, migration, backup set, provider or MCP tool/scope.
Existing 120-day/no-gap guards and independent portfolio behavior remain under the full suite.

## Production evidence, read-only

[Candidate production read](../../governance/project/evidence/wi063/candidate-production-read-2026-10-19.json)
verified 376 exact source partition proofs. This is candidate code against existing production data inside a rolled-back
read transaction; it is **not** actual corrected OAuth transport acceptance. Source calls and production mutations: zero.

| Case | Candidate oracle/result |
| --- | --- |
| RIA 2020-01-01..02 | empty/partial, `collection_coverage_before_start`; exact uncovered dates retained |
| RIA 2026-08-25 | 2 rows/pass/matched; WI-064 result preserved |
| RIA 2026-10-16 | empty/pass; independently proven source window |
| RIA 2026-10-17..18 | empty/partial, `collection_watermark_before_query_end` |
| Brokerage 2026-10-15 | empty/pass only after KRX and both NAS sources intersect |
| Global 2026-10-15 | partial for IRP; other accounts cannot lend their proof |
| RIA 2026-08-28..09-24 | pass from actual contiguous retained source partitions; no gap is invented |

The proven source start is 2023-08-28, obtained from complete published partition ranges, not earliest trade rows.
RIA/ISA/pension/brokerage KRX end at 10/16, brokerage NAS at 10/15 and IRP KRX at 7/14. Recent IRP remains the
approved unavailable source route. No older range is invented or silently backfilled.

[Actual Codex baseline](../../governance/project/evidence/wi063/codex-production-baseline-2026-10-19.json)
reproduced the existing false pass: request `20e044b5a7cc431ea6d53e5b2184e508`. Actual positive, covered empty,
upper-gap partial and inverted-date `invalid_request` remain working. They are pre-release baselines, not proof
that the correction has reached the client.

## Three applicable scheduler-date audit

[Runtime audit](../../governance/project/evidence/wi063/runtime-three-date-audit-2026-10-19.json) correlates Job
execution ID, scheduler creator, timestamps, retained pipeline run/stage/quality/publish evidence and Cloud Logging.
The latest three completed applicable KST schedule dates are 10/14, 10/15 and 10/16; overseas logical dates are
10/13, 10/14 and 10/15 because its fixed argument uses New York's date.

| Scope/date KST | Execution suffix | Result and source proof |
| --- | --- | --- |
| Domestic 10/14 | 8twgd | success; four account KRX partitions, three stages/two quality rules each; IRP named unavailable |
| Domestic 10/15 | d789k | success; same supported scopes |
| Domestic 10/16 | kxlqf | success; same supported scopes |
| Overseas 10/14 | jkbtr | success; four bounded order/transaction partitions for brokerage NAS |
| Overseas 10/15 | klvld | failed; historical transaction partition hit HTTP 500/EGW00123, three bounded physical attempts |
| Overseas 10/16 | ntt7r | success; four bounded order/transaction partitions |

Failure run `30679156-d56d-4b15-8ccb-67b7a7fd9a4d` remains failed. Its zero summarized stage calls are not evidence
of zero HTTP attempts: correlated logs show three. The prior successful run `81e30e86-36ed-4b68-8c86-aac0e6fa9337`
and later independent success `a029a948-86de-4c8b-ae7d-f633aee1fd2d` prove that historical source range; the failed
run is never adopted as coverage. Quality, publish and coverage of every constituent partition are included in JSON.
This is two successful overseas slots plus one explained, retained upstream failure, not a claim of three successes.

Both legacy trade schedulers are paused and only the two incremental trade schedulers are enabled. Latest legacy
execution IDs predate the sample. Each scope/date has one scheduler-created execution; 10/14's additional domestic
`l6qml` recovery and rejected `zrx26` preflight have the GitHub deployer creator and belong to the approved WI-074
recovery. Partition/stage counts are not Scheduler invocation counts. The audit starts no source run or send.

## Protected release and rollback

The reviewable change includes the `wi063-s02` workflow target. After owner approval and merge to master, dispatch
Deploy Cloud Run with that target under its existing `production` environment approval. It builds one immutable
image, snapshots both Job definitions and Remote stable/tag revisions, updates only the two existing trade Job
images/labels, then moves stable and `wi046-v2` together using the existing smoke guard. It executes **no** Job,
source replay, migration/DDL, Scheduler update, secret update or external send.

The release regression injects failures during the second Job update, Remote update, traffic promotion and smoke;
each restores exact Job definitions and the prior stable/tag routes. Missing rollback inputs stop before build.
Pre-release [Remote rollback baseline](../../governance/project/evidence/wi063/remote-rollback-baseline-2026-10-19.json)
is informational: the protected run must recapture live state at release time. Rollback restores runtime images/routes;
it never deletes new pipeline evidence, reduces watermarks, or rewrites source facts.

The normal production authorization boundary comes from the owner's instruction and
`.agent/skills/kis-release-ops/SKILL.md`: “Deploy production through `.github/workflows/deploy-cloud-run.yml` with
the `production` environment approval.” This isolated work does not approve release on the owner's behalf.

## Immediate actual-client acceptance after release

Use the existing owner-approved Codex OAuth connection, no source pipeline invocation:

1. `get-trade-ledger(account_alias='ria',start_date='2020-01-01',end_date='2020-01-02',limit=20)`:
   zero rows, partial, before-start reason, exact 2020 uncovered interval. Any pass is FAIL and rolls back.
2. RIA `2026-08-25..25`: exactly two rows/pass. No duplicate identity work is reopened.
3. RIA `2026-10-16..16`: empty/pass with no uncovered interval; that source date is proven.
4. RIA `2026-10-17..18`: partial upper gap. Brokerage `2026-10-15..15`: pass only with KRX/NAS proof.
5. Global `2026-10-15..15`: partial with IRP gap; no global false pass.
6. Inverted dates `2026-10-18..17`: bounded `invalid_request`, no mutation.
7. `get-portfolio-overview`: still available with prior quality semantics. Retained pipeline failures remain visible.

Record request IDs, release SHA/digest/Actions run, observed quality/row count and gap dates. CI/health smoke alone
cannot close WI-063. Owner accepts these specific corrected results and the explained recurring sample before
parent/S01/S02 closure. If the owner elects to exercise Claude too, ask it to compare RIA 2020 coverage with 8/25
and explain why an empty result in the first window cannot mean “no trades”; it should show the partial/gap and
the two actual 8/25 events. WI-063's existing required acceptance client is Codex, so this optional scenario does
not add a new closure gate.


## Repository verification

Final full gate: **908 passed**, one existing Authlib deprecation warning, 45.23s. Project OS, data governance,
architecture, warehouse, MCP surface, V2 documentation, shell syntax and tracked/staged whitespace gates pass.
Protected release boundaries: six tests pass, including preflight and each rollback stage. A CLI dry-run emits only
build, two image updates, Remote image update and stable/tag promotion; it performs zero external mutations.
[Validation summary](../../governance/project/evidence/wi063/validation-2026-10-19.json) and
[dry-run transcript](../../governance/project/evidence/wi063/release-dry-run-2026-10-19.log) retain the commands
and distinguish local/candidate verification from post-release client acceptance.


## Executed protected release and actual OAuth — 2026-10-19

Owner approval: explicit “네 배포해요” in this chat. PR #168 merged `8ba01d81b5cd0d8c48f8c6a770f4abe55a53341a`;
[protected run 39144314352](https://github.com/meringue5/KIS_Portfolio_MCP/actions/runs/39144314352) succeeded.
The release reran the full gate: **908 passed**, one existing Authlib warning, 142.29s. Both trade Jobs and Remote
share digest `sha256:f2099627e6936013a471b05eaa525e7a27ffd67ac467c72a4d8d24deaa19cd39`. Stable traffic
and `wi046-v2` point to `kis-portfolio-remote-00064-ndw`; other tags are retained. Label/SHA/run identity, unchanged
non-image settings, eight Scheduler configurations and unchanged latest Job execution IDs were verified independently.
All 12 source/reference fingerprints, 281 current trades, 19 identity aliases and schema ceiling 0022 are unchanged.

Actual approved Codex OAuth [9/9 oracles](../../governance/project/evidence/wi063/codex-production-acceptance-2026-10-19.json):

| Case | Observed result |
| --- | --- |
| RIA 2020-01-01..02 | 0 rows, partial, collection_coverage_before_start, exact 2020 uncovered interval |
| RIA 8/25 | 2 rows/pass/matched |
| RIA 10/16 | empty/pass/no uncovered interval |
| RIA 10/17..18 | partial upper gap |
| Brokerage 10/15 | empty/pass with KRX and NAS proof |
| Global 10/15 | partial for IRP KRX; other accounts retain their own coverage |
| Inverted date range | bounded invalid_request |
| Portfolio overview | available/pass, 32 rows |
| Retained failed run 30679156… | failed/visible, not rewritten as successful |

The 2020 corrected request is `a637c9975f5c409eae7e3e9b8c3a831a`. This is post-release actual transport proof,
separate from prior candidate reads and fixture passes. The release executes no source Job, backfill, DDL/migration,
Scheduler/secret change or external send. [Release summary](../../governance/project/evidence/wi063/protected-production-release-2026-10-19.json)
and [resource comparison](../../governance/project/evidence/wi063/production-resources-2026-10-19.json) preserve deployment and data evidence.

Remaining exit is owner acceptance of these displayed corrected results and the already-explained recurring sample.
S02 advances to stabilizing; parent/S01 stay stabilizing. No new Claude or mandatory future-slot wait is introduced.


## Owner-accepted closure — 2026-10-19

The owner replied “네 인수하고 정리합시다” after the deployed 9/9 results and source-preservation outcome were
presented, accepting the results and authorizing publication of these post-release operational/OAuth evidence files
to the same repository. [Acceptance record](../../governance/project/evidence/wi063/owner-acceptance-2026-10-19.json)
closes WI-063 and both corrective sub-items. Earlier pending-acceptance statements above are historical snapshots.
Recent IRP remains an explicit unsupported-source gap; the overseas HTTP 500 remains failed history with its later
independent coverage proof. Owner acceptance does not turn either into fabricated successful coverage.

Existing Jobs/Schedulers and owner retain monitoring responsibility and source-preserving rollback; no source run,
DDL, notification or additional deployment is part of closeout. Other Work Items/milestones and the original dirty
shared checkout are preserved. The isolated managed worktree can be archived after the evidence/closeout PR merges.
