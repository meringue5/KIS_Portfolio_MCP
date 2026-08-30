# WI-035 production operations pre-research — 2026-08-30

> Work Item: `WI-035-S01`
> 조사 시각: 2026-08-30 18:08 KST
> 변경 경계: repository와 live metadata read-only 조사. GCP·DB·배포·cleanup·계약 변경 없음

## 결론

`WI-035` 구현에 필요한 운영 기준선은 확보됐다. 다만 지금 Artifact Registry cleanup을 활성화해서는 안
된다. 현재 runtime은 legacy `cloud-run-source-deploy`와 build-once `kis-portfolio` repository를 함께 쓰며,
모든 active digest는 식별할 수 있지만 canonical rollback manifest와 `prod-current`/`prod-previous`/
`rollback-*` tag가 아직 없다. cleanup 구현은 이 보호집합이 완전하지 않으면 fail closed해야 한다.

비용 면에서는 7,500원 budget과 threshold가 live configuration에 유지되고 있다. 2026-08-28 기준 정상월
보수적 baseline은 5,100원, MotherDuck은 Lite $0/month다. Cloud Billing Budget API는 alert configuration을
제공할 뿐 현재 actual/forecast 값을 제공하지 않으며 BigQuery billing export도 없으므로, 첫 구현은 월간
Console snapshot을 typed input으로 검증하는 방식이 현실적이다. 자동 비용 차단장치라고 주장해서는 안 된다.

## 조사한 근거

- canonical 요구·설계: `docs/design/kis-portfolio-v2-delivery-plan.md`의 V2-W0002/0003/0106,
  `docs/design/kis-portfolio-v2-system-design.md` 12장, `docs/design/v2-architecture-delta-review.md` 5.3장
- 기존 비용 기준선: `docs/operations/cost-baseline-2026-08.md`
- 배포 코드와 workflow: `scripts/deploy_cloud_run.py`, `.github/workflows/deploy-cloud-run.yml`,
  `docs/deployment.md`
- live read-only metadata: Cloud Run, Scheduler, IAM service account, Secret Manager, GCS, Firestore,
  Artifact Registry, Cloud Billing budget와 최근 GitHub Actions deployment runs

## 현재 resource inventory

| Resource kind | Count | Current finding |
| --- | ---: | --- |
| Cloud Run services | 2 | `auth`, `remote`; both max 1 and no minScale annotation, therefore scale-to-zero |
| Cloud Run jobs | 12 | 3 current core slots, 3 standing V1 jobs, 6 bounded migration/recovery jobs |
| Cloud Scheduler jobs | 6 | all enabled; 07:35, 08:30, 10:00, 14:30, 15:35, 16:00 KST weekday schedules |
| service accounts | 5 | deployer, scheduler, pipeline and two Google-managed/default identities |
| Secret Manager resources | 24 | payload not inspected; one more than 2026-08-28 baseline because Telegram token now exists |
| GCS buckets | 5 | one application-private bucket and four platform-managed buckets |
| Firestore databases | 2 | default Datastore-mode database plus `kis-portfolio-state`; PITR disabled |
| Artifact Registry repositories | 2 | legacy 2,652.602 MB/75 versions; build-once 604.698 MB/12 versions |
| MotherDuck | 1 operational DB | 2026-08-28 evidence: `kis_portfolio` 49 MiB, Lite plan; not re-queried in S01 |

The application-private GCS bucket has versioning, seven-day soft delete, 30-day noncurrent-version deletion and
seven-day incomplete multipart cleanup. No lifecycle or resource setting was changed in this investigation.

## Image and rollback findings

The active runtime currently resolves to nine distinct image digests:

- two service digests in `cloud-run-source-deploy`;
- three standing V1 Job digests in `cloud-run-source-deploy`;
- four build-once Job digests in `kis-portfolio`: current core, WI-021 recovery, WI-022 recovery and WI-029 shadow.

The three current core jobs share one immutable digest and one Git SHA, which confirms the implemented build-once
boundary for that target. Service and Job labels provide `git-sha`, `github-run-id`, `deploy-target` and
`deploy-source`, and recent runs can be reconciled to those labels.

The two service revision histories expose previous digests, but that is not a sufficient rollback contract. Job
definitions do not provide an equivalent canonical previous release, SHA tags are not semantic rollback tags, and no
versioned release manifest or cleanup policy exists. The repositories also contain untagged versions. Therefore:

1. inventory must resolve every service and Job current digest across both repositories;
2. a versioned release/rollback manifest must add explicit protected digests;
3. missing resources, unresolved digests, missing rollback evidence or partial API results must block cleanup;
4. keep rules must cover active digests, manifest rollback digests, semantic keep tags and the approved recent-version
   floor before age-based delete candidates are calculated;
5. dry-run output must include the protected reason for every kept digest and must be reviewed before any apply gate.

## Cost guardrail findings

The live project budget is KRW 7,500 with current-spend thresholds 50%, 90% and 100%, plus forecast 100%. Approved
hard-envelope behavior remains:

| State | Threshold | Required deterministic response |
| --- | ---: | --- |
| Early | budget 50/90/100% | inspect retry, image/storage growth and cost attribution |
| Guard | KRW 35,000 actual or forecast | stop new backfill and high-frequency optional sources |
| Approval | KRW 42,500 | require owner approval for non-essential pipelines |
| Ceiling | KRW 50,000 | keep only essential auth/backup candidates; open optional pipeline circuits |

Repository search found no executable cost-state evaluator, no machine-readable consolidated resource inventory, no
release manifest, and no Artifact Registry cleanup planner. The existing deployment label and build-once helpers are
usable inputs but are not those controls.

Because actual/forecast spend is not available from the Budget API and there is no billing export, the implementation
must either validate a dated, reviewable manual cost snapshot or introduce a separately approved billing data source.
Stale or missing cost evidence must produce `unknown`, not a fabricated safe state. A budget alert must never be
described as an automatic spending cap.

## Implementation-ready inputs

The parent `WI-035` can be decomposed without changing its identity:

1. produce a schema-versioned JSON inventory with observation time, project/region, completeness, resource kind/name,
   state, deployment labels, image digest and non-secret configuration hashes;
2. add a typed cost snapshot and deterministic threshold evaluator with `unknown`/stale fail-closed behavior;
3. add a release/rollback manifest and cleanup planner that reads both repositories and emits protected/candidate
   reasons;
4. test partial inventory, unresolved image, missing rollback, threshold boundaries and active-digest exclusion;
5. run cleanup only in dry-run during implementation; active policy/apply remains a separate production approval.

The formal implementation should preserve the existing two-repository runtime until MS-003 cutover work moves all
targets. It must not infer that recovery Jobs, old revisions, system buckets or the default Firestore database are
deletion candidates merely because they are not part of the steady-state target list.

## Remaining decisions and limits

- Choose the versioned inventory and release-manifest file locations during formal `WI-035` planning.
- Decide whether monthly manual cost snapshots remain sufficient after the first clean scale-to-zero month; billing
  export remains a separate architecture/cost decision.
- Define the rollback retention window and operator review record before cleanup apply.
- This research did not inspect secret payloads, query current MotherDuck usage, calculate post-2026-08-28 actual GCP
  spend, execute a deploy, mutate IAM, or create/apply cleanup policies.

`WI-035-S01` is closed as research evidence. Parent `WI-035` remains `proposed` and MS-003 remains gated by MS-002.
