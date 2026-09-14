# KIS Portfolio steady-state operations runbook

> Owner: WI-050 / V2-W0805
> Canonical scope: V2 production after WI-049 cleanup
> Safety: inspection and local restore only; this runbook authorizes no mutation or recurring automation

## Operating contract

| Cadence | Required review | Evidence |
| --- | --- | --- |
| Every managed run | run/stage result, idempotency, freshness, quality, lineage, publish/delivery outcome | Control read models and run ID |
| Daily | failed/missing slot, stale dataset, backup completion, reconciliation gap | redacted run and backup evidence |
| Monthly | GCP/MotherDuck capacity, actual/forecast cost, Artifact Registry growth, runtime drift, source lifecycle and open exceptions | versioned review JSON + cost snapshot |
| Quarterly | fresh private-backup restore, source API/license/terms, IAM/service-account and Secret metadata, retention candidates | versioned review JSON + restore output |
| Release | immutable digest, migration/backup/restore, runtime smoke, cost and rollback manifest | Git SHA, workflow run and release evidence |

Recurring scheduling is deliberately absent. Create an automation only after a separate owner request defines cadence,
notification policy and cost.

## Prerequisites

1. A clean clone at the intended Git SHA with Python 3.13 and `uv sync` complete.
2. Repository-only review needs no cloud or database credential.
3. Production read-only review needs authenticated `gcloud`, `.env` with MotherDuck read access, and private recovery
   bucket access. Never print `.env`, tokens, account identifiers or Secret payloads.
4. Use a new `/tmp/kis-wi050-restore-<date>` destination. Never restore into the production database.

Start every review with:

```bash
git status --short --branch
git rev-parse HEAD
git rev-parse origin/master
bash scripts/check.sh quick
```

## Daily triage

1. Query `get-pipeline-run`/Control evidence for each expected slot. A successful Cloud Run execution alone is not a
   successful portfolio run.
2. Separate `failed`, `partial`, `stale`, closed-market `skipped` and idempotent `reused`; do not convert absence into
   pass.
3. Check latest off-site backup time. If the newest usable backup would make RPO exceed 24 hours, stop new risky
   writes/backfills and open an incident.
4. Preserve run ID, logical date/slot, immutable image digest, quality status and aggregate counts. Never paste raw
   provider bodies or portfolio values into repository evidence.

## Monthly capacity and cost review

Capture a dated `kis-portfolio.cost-snapshot/v1` from Cloud Billing Reports. An open month requires actual and forecast
KRW plus complete project attribution. Record MotherDuck database size and governed drift; service/Job/Scheduler counts,
scaling caps and Artifact Registry versions; all source lifecycle/rights/cost fields; and open exceptions.

Evaluate without applying changes:

```bash
uv run python scripts/steady_state_operations.py \
  governance/project/evidence/wi050/steady-state-review-2026-09-14.json \
  governance/project/evidence/wi045/cost-snapshot-2026-09-11.json \
  --as-of 2026-09-13T21:55:30Z
```

Capacity attention is raised at database growth of 25% or more, or more than 20 additional image versions since the
previous review. Runtime count drift, warm minimum instances or missing max caps block the review. Growth does not
authorize cleanup; investigate consumers, retention and recovery first.

| Evaluated monthly KRW | State/action |
| ---: | --- |
| below 3,750 | normal |
| 3,750 / 6,750 / 7,500 | early 50/90/100%; inspect growth and attribution |
| 35,000 | guard; stop new backfill and optional high-frequency sources |
| 42,500 | owner approval required for non-essential pipelines |
| 50,000 | ceiling; nominate optional circuits to stop while preserving auth/backup/recovery |
| unknown/stale/incomplete | block new cost-increasing work and obtain current evidence |

These are operating gates, not a claim that billing budgets cap spend automatically.

## Quarterly restore rehearsal

Use the newest immutable private index and verify its exact SHA-256. Download to a fresh local directory:

```bash
uv run python scripts/sync_v2_backup_gcs.py \
  --project grand-forge-279904 \
  --bucket grand-forge-279904-kis-portfolio-private \
  --use-gcloud-token restore \
  --index-uri <immutable-gs-index-uri> \
  --index-sha256 <64-lowercase-hex> \
  /tmp/kis-wi050-restore-YYYYMMDD
```

Restore only into a fresh local database or memory:

```bash
time uv run python scripts/restore_v2_backup.py \
  /tmp/kis-wi050-restore-YYYYMMDD --database :memory:
```

Record backup creation/rehearsal times, object/byte and table counts, migration prefix and warnings. RPO must be at
most 1,440 minutes and RTO at most 14,400 seconds. If restricted object bytes are absent, report `attention` and
separately verify the private content-addressed objects referenced by the manifest before claiming full document
recovery. Never target `md:kis_portfolio`, upload, migrate or overwrite an existing restore path in this rehearsal.

After restoring to a fresh local DuckDB file, hash-verify the separate private objects. Output is aggregate-only:

```bash
uv run python scripts/verify_private_object_recovery.py \
  /tmp/kis-wi050-restored-YYYYMMDD.duckdb \
  --project grand-forge-279904 \
  --bucket grand-forge-279904-kis-portfolio-private \
  --use-gcloud-token
```

## Quarterly source-rights review

Review `governance/catalog/sources.toml`, `collections.toml`, `macro-series.toml` and ETF profiles/routes against current
provider terms and approved DEC/ADR references.

- Every approved source must have known rights and cost. A terms change blocks collection until a versioned contract
  review is accepted.
- Proposed sources remain zero-call. Unknown/unlicensed content remains prohibited.
- Alpha Vantage remains owner-only, normalized, non-redistributed and quarterly/terms-change gated.
- Do not silently promote a provider, broaden retention or add a paid plan; those require a new Work Item and approval.

```bash
python3 .agent/skills/kis-data-governance/scripts/check_data_governance.py
uv run python .agent/skills/kis-warehouse-contract/scripts/check_warehouse_contracts.py
```

## Quarterly IAM and Secret metadata review

List service accounts, project IAM bindings, resource-level Secret/Job/bucket policies and Secret resource metadata.
Do not access Secret versions or payloads. Compare with `docs/security-and-secrets.md`,
`docs/operations/gcp-v2-managed-pipeline-2026-08.md` and WI-046 evidence.

- dedicated Auth, Remote, pipeline and Scheduler identities remain distinct;
- project-level runtime permissions do not exceed the approved datastore role;
- Secret accessor and Job invoker bindings remain resource-scoped;
- no public principal, owner/editor/admin widening, unknown identity or expired exception exists;
- record `secret_payloads_read=false`, `iam_mutated=false`, `secret_mutated=false`.

Any widening is an incident/maintenance intake, not something this review auto-revokes.

## Exceptions, escalation and closeout

Open reconstruction exceptions are governed evidence and are not deleted merely for being old. Report their count and
trend. Every Project OS emergency exception needs an owner, expiry and reconciliation plan; expired or ownerless items
block review completion.

- `pass`: no blocker or follow-up action.
- `attention`: review is complete, but named action remains; it authorizes no production change.
- `blocked`: an SLO, rights, cost, runtime, access or exception gate failed. Preserve evidence and open an appropriate
  incident/correction Work Item before mutation.

Finish with `bash scripts/check.sh full`, commit evidence without secrets or portfolio values, and link the Git SHA and
review result from the Work Item. This runbook is never cleanup, deployment or automation approval.

## 2026-09-14 initial rehearsal

The WI-048 immutable index downloaded 79 objects totaling 14,409,499 bytes. Fresh in-memory restore verified 78 tables
through migration `0019`. Conservative RPO was 522 minutes and download-plus-restore RTO was 8 seconds. MotherDuck was
129.7 MiB; the post-WI-049 registry baseline is 49 versions; 2 services, 6 Jobs and 6 Schedulers remained ready/enabled.
The 19 source contracts reconcile as 13 approved and 6 proposed with no approved unknown-rights/cost source. Current
reconstruction exceptions are 57; owner review and Project OS emergency exception counts are zero.

The separate private-object verification read and hash-checked all 33 referenced objects totaling 3,954,341 bytes,
without exposing their content or identifiers. The final deterministic decision is `pass`; no production resource or
data was changed.
