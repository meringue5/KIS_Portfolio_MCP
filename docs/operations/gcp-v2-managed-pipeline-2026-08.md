# GCP V2 managed pipeline foundation — 2026-08

## Provisioned resources

- Private bucket: `grand-forge-279904-kis-portfolio-private`, Seoul `asia-northeast3`, Standard.
- Controls: public-access prevention enforced, uniform bucket-level access, Google-managed encryption, versioning,
  7-day soft delete, 30-day noncurrent-version cleanup and 7-day incomplete multipart cleanup.
- Runtime identity: `kis-portfolio-pipeline@grand-forge-279904.iam.gserviceaccount.com`.
- Scheduler identity: `kis-portfolio-scheduler@grand-forge-279904.iam.gserviceaccount.com`.
- Runtime Firestore IAM: `roles/datastore.user` with a condition restricting `resource.name` to
  `projects/grand-forge-279904/databases/kis-portfolio-state`.
- Runtime GCS IAM: `roles/storage.objectAdmin` on the private bucket only.
- Runtime Secret Manager IAM: 15 account KIS app-key/app-secret/CANO secrets are scoped individually. MotherDuck token
  and KIS token-encryption-key accessor bindings remain pending explicit high-risk credential authorization.

No V1 Job, Scheduler, auth service, remote MCP service or MotherDuck object was deleted or disabled.

## Managed collection contract

`collect-owned-portfolio-v2` accepts only `today`/explicit date, one of `kr-1000`, `kr-1430`, `kr-1600`, and the
fixed `all-accounts` partition. KRX calendar state gates execution. The 10:00 run also reads the latest U.S. holdings,
cash, daily price history and USD/KRW inputs; a seven-day bounded price/FX window catches the latest prior U.S.
session after weekends or Korean holidays.

The release generator builds one image, resolves its immutable digest and deploys three separate fixed-argument
Cloud Run Jobs. The three Schedulers use `0 10`, `30 14`, `0 16` in `Asia/Seoul`; no request body can replace the
fixed container arguments. Scheduler and future allowlisted MCP requests share the same logical key and Firestore
lease/run-request state.

## Verification and pending production gates

- Full Project OS gate: 221 tests passed.
- Fixture production-adapter tests cover calendar skip, logical no-op, GCS landing/hash verification, source-call
  budget, failure resume without source recall, quality, lineage, watermark and Gold publish.
- Deploy dry-run shows one digest reused by three Jobs and exact fixed arguments.
- Actual backup upload/restore is pending explicit authorization to transfer confidential portfolio Parquet payloads
  to the provisioned private bucket.
- Actual Job/Scheduler deployment is pending the two secret accessor bindings above plus normal master/CI release.
