# WI-049 runtime cleanup readiness — 2026-09

## Decision

The first WI-049 boundary is ready for review, not execution. Eleven historical one-time Cloud Run Job definitions are
exact candidates. No service, scheduled Job, Scheduler, identity, Secret, database, backup, bucket, Firestore database
or image version is approved for deletion.

The machine-readable source is
`governance/project/evidence/wi049/runtime-cleanup-readiness-2026-09-13.json`. Its v1 validator is deliberately
review-only: `mode=dry_run`, `apply_allowed=false` and `owner_approved=false` are mandatory.

## Protected history baseline

The 2026-09-13 MotherDuck read-only inventory recorded aggregate row counts only. Values, holdings, account identifiers
and raw payloads are excluded from repository evidence.

| History family | Protected object | Rows |
| --- | --- | ---: |
| total assets | `main.asset_overview_snapshots` | 57 |
| holdings | `main.asset_holding_snapshots` | 1,895 |
| daily portfolio | `gold.portfolio_daily_state` | 1,865 |
| positions | `silver.position_snapshots` | 2,127 |
| domestic orders | `main.order_history` | 111 |
| overseas orders | `main.overseas_order_history` | 0 |
| overseas transactions | `main.overseas_transaction_history` | 69 |
| realized trades | `main.trade_profit_history` | 15 |
| trade events / revisions | `silver.trade_events` / `silver.trade_event_revisions` | 282 / 282 |
| cash events / revisions | `silver.cash_flow_events` / `silver.cash_flow_event_revisions` | 49 / 49 |
| trade threads | `silver.trade_threads` | 19 |
| lot / journal revision contracts | `silver.purchase_lot_revisions` / `silver.trade_journal_revisions` | 0 / 0 |

Zero-row history contracts remain protected. A zero count is not permission to drop an object.

The fresh WI-048 post-transition backup contains the governed database state and passed a fresh restore in GitHub run
`34759029400`. The immutable post index is identified by SHA-256
`bc91f37b77f5bc2ef98d218a416337de71e2112ccecba2bf879b8afd15968da0` in the private recovery bucket. WI-049 does
not delete or rewrite that index or any object it references.

## Protected runtime

- Services: `kis-portfolio-auth`, `kis-portfolio-remote`.
- Scheduled Jobs: domestic order history, overseas transaction history, canonical V2 `1000`/`1430`/`1600`, token
  warmup.
- Enabled Schedulers: the six schedules targeting those six Jobs.
- State and recovery: both Firestore databases, the private recovery bucket, both Artifact Registry repositories.
- Identities and Secrets: all remain unchanged and outside S01/S02.

The actual 100% traffic revisions were inspected separately from mutable service templates. Auth traffic resolves to
digest `sha256:b3b620eb...85ad43`; Remote traffic resolves to `sha256:c8abbb57...dfcf6b`. The three canonical V2
schedule Jobs resolve to `sha256:a35e6899...8208ab`. These and recent V2 forward-recovery digests are protected from
S03 until a fresh exact-digest release manifest is reviewed.

## Exact S02 candidates

All candidates have no Scheduler reference, have a recorded successful last execution, and can be recreated from the
frozen Git/GitHub references. Approval of this table would authorize deletion of these Job definitions only.

| Candidate Job | Last successful execution | Deployment evidence |
| --- | --- | --- |
| `kis-portfolio-wi021-s06` | `kis-portfolio-wi021-s06-8q7q6` | GitHub run `33145645614` |
| `kis-portfolio-wi021-s06-migration` | `kis-portfolio-wi021-s06-migration-gpzc6` | GitHub run `33145645614` |
| `kis-portfolio-wi022-s06` | `kis-portfolio-wi022-s06-9zmm2` | GitHub run `33163171218` |
| `kis-portfolio-wi022-s06-migration` | `kis-portfolio-wi022-s06-migration-qhs6v` | GitHub run `33163171218` |
| `kis-portfolio-wi029-s04-migration` | `kis-portfolio-wi029-s04-migration-dngbw` | GitHub run `33182018996` |
| `kis-portfolio-wi029-s04-verify` | `kis-portfolio-wi029-s04-verify-jlvt6` | GitHub run `33182018996` |
| `kis-portfolio-wi030-s02` | `kis-portfolio-wi030-s02-gt9g4` | GitHub run `33454254322` |
| `kis-portfolio-wi030-s03` | `kis-portfolio-wi030-s03-gsplw` | GitHub run `34466281709` |
| `kis-portfolio-wi046-migration` | `kis-portfolio-wi046-migration-czmrl` | GitHub run `34621191176` |
| `kis-portfolio-wi046-state-migration` | `kis-portfolio-wi046-state-migration-rknjw` | GitHub run `34621191176` |
| `kis-portfolio-wi048-s02` | `kis-portfolio-wi048-s02-ct5p9` | GitHub run `34759029400` |

Deleting a Cloud Run Job also removes its execution view. The exact last execution, completion timestamp, image digest,
non-secret configuration hash and recreation reference are therefore preserved in the manifest before any deletion.

## Artifact and cost boundary

`cloud-run-source-deploy` contained 75 versions across five packages: five tagged versions and 64 untagged versions
older than 30 days were age-eligible in the dry-run. `kis-portfolio` had no untagged version older than 30 days. These
counts do not make any digest safe to delete: active revisions, forward recovery and the exact images needed to recreate
S02 Jobs still overlap the repositories.

Image cleanup is S03 and needs its own exact-digest manifest and approval after S02 post-cleanup verification. Idle
one-time Job definitions do not imply ongoing compute charges; S02 primarily removes obsolete control-plane clutter.
S03 may reduce storage cost, but only after protected-digest reconciliation.

## S02 execution gate

Before an apply path exists, all of the following are required:

1. owner approval naming all or a subset of the 11 exact Job names;
2. fresh revalidation that every approved Job still has no Scheduler reference and matches its configuration hash;
3. deletion by exact project, region, kind and name with no wildcard;
4. post-delete inventory proving only approved names disappeared;
5. canonical Auth/Remote health, unauthenticated MCP 401 and an authenticated read smoke;
6. unchanged protected-history row counts or explained monotonic increases, plus unchanged backup objects;
7. a separate decision for S03. S02 approval never authorizes image deletion.

Repository verification passed the focused 23-test guardrail suite, the 33-test guardrail/readiness suite, Project OS
quick, and the full 682-test gate. The full gate reported one existing Authlib deprecation warning.
