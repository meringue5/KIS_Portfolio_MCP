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
- Runtime Secret Manager IAM: 15 account KIS app-key/app-secret/CANO secrets plus the MotherDuck token and KIS
  token-encryption-key are scoped individually to the runtime identity.
- GitHub deploy identity has read-only Project Viewer for default Cloud Build log streaming and service-account-level
  `actAs` only on the V2 runtime and Scheduler identities.

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

## Production verification

- Full Project OS gate: 222 tests passed after the dedicated Scheduler identity regression fix.
- Fixture production-adapter tests cover calendar skip, logical no-op, GCS landing/hash verification, source-call
  budget, failure resume without source recall, quality, lineage, watermark and Gold publish.
- Confidential backup upload wrote 30 content-addressed objects (3,459,255 bytes). Index digest:
  `86e068b30fa78c952dc4c4aab7e6757c396ab1b3b8e390a97e27464d235fef57`.
- Isolated restore verified the index and every object hash, then restored 29 V2 tables into in-memory DuckDB.
- Master/CI deployed all three fixed Jobs from one immutable image digest and all three KST Schedulers. The runtime
  identity is `kis-portfolio-pipeline`; the invoker identity is `kis-portfolio-scheduler`.
- First production run `kis-portfolio-owned-core-v2-1000-x7fhp` succeeded on 2026-08-28 in 3m2s: 4/4 stages,
  36/64 source calls, account coverage pass, three lineage edges, watermark current, and 31 Gold rows all pass.
- Idempotency run `kis-portfolio-owned-core-v2-1000-45nbg` retained one logical run, maximum stage attempt 1 and the
  same 103 source observations. It did not recollect or duplicate the logical run.
- The five-trading-day dual-write observation window began on 2026-08-28. V1 writers remain enabled.
