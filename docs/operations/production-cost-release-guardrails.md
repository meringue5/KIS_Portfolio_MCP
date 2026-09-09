# Production inventory, cost and release guardrails

> Work Item: `WI-035`
> Contract version: v1
> Current execution boundary: isolated repository implementation; no production effects

## Purpose and safety boundary

`scripts/production_guardrails.py` validates versioned JSON evidence and produces deterministic review output. It does
not call Google Cloud, write a database, change IAM or secrets, deploy a service, activate a source, install an Artifact
Registry cleanup policy, delete an image or expose an MCP tool. There is intentionally no apply command. Every cleanup
plan reports `mode=dry_run`, `review_required=true` and `apply_allowed=false`.

Production capture and cleanup apply require the MS-003 production gate, a fresh production inventory and release
manifest, normal release approval and a separately reviewed operator action. A successful local fixture is contract
evidence only; it is not current production evidence.

## Versioned artifacts

The implementation owns four schema identifiers:

| Artifact | Schema identifier | Role |
| --- | --- | --- |
| resource inventory | `kis-portfolio.resource-inventory/v1` | non-secret resource and Artifact Registry version observation |
| cost snapshot | `kis-portfolio.cost-snapshot/v1` | dated actual/forecast input from a manual Billing report or approved export |
| release manifest | `kis-portfolio.release-manifest/v1` | explicit active and target-specific rollback digests plus restore evidence |
| cleanup plan | `kis-portfolio.cleanup-plan/v1` | dry-run review result; never an apply authorization |

Synthetic examples are in `tests/fixtures/wi035/`. They use fake project, digest and Git identifiers and must never be
copied as a production manifest.

### Resource inventory

The inventory records observation time, project, regions, completeness, collection errors, resource rows and Artifact
Registry versions. Resource rows allow only kind/name/region/state, string labels, resolved image digest and a SHA-256
of an allowlisted non-secret configuration projection. Raw environment variables, secret payloads, account identifiers,
IAM credential material and arbitrary provider responses are rejected as unsupported fields.

The capture procedure for an authorized production review is:

1. Read every Cloud Run service and Job, Scheduler job, service account, Secret resource name, GCS bucket, Firestore
   database and Artifact Registry repository in the approved project/regions. Do not read secret versions or payloads.
2. Resolve every Cloud Run service and Job image to `sha256:<64 lowercase hex>` across both the legacy
   `cloud-run-source-deploy` and build-once `kis-portfolio` repositories.
3. List every Artifact Registry package version with repository, package, digest, tags and creation time. Partial pages
   or failed calls go in `collection_errors` and force `complete=false`.
4. Project configuration onto reviewed non-secret fields, serialize JSON with sorted keys and compact separators, then
   record its lowercase SHA-256 as `configuration_sha256`. Never hash a secret-bearing payload as a substitute for
   excluding it.
5. Validate the finished snapshot. Only a complete, error-free inventory can produce a complete cleanup plan.

```bash
uv run python scripts/production_guardrails.py validate-inventory \
  path/to/resource-inventory.json
```

The validator sorts resource and version rows, rejects duplicate identities and fails when an active service or Job has
an unresolved image digest. Missing resources cannot be inferred from the steady-state target list; recovery Jobs,
old revisions, system buckets and the default Firestore database are observations, not implicit deletion candidates.

### Cost snapshot and deterministic actions

Until a separately approved billing export exists, the source is a dated `billing_console_manual` snapshot. An open
billing period requires both actual and forecast KRW; a closed period requires actual KRW. Cost attribution must be
marked complete. Evidence older than 40 days, future-dated evidence or incomplete attribution returns `unknown` and
blocks new cost-increasing work.

The evaluated amount is the higher of actual and forecast:

| State | Boundary | Deterministic action |
| --- | ---: | --- |
| `normal` | below KRW 3,750 | continue inside approved limits |
| `early_50` / `early_90` / `early_100` | KRW 3,750 / 6,750 / 7,500 | inspect retry, image/storage growth and attribution |
| `guard` | KRW 35,000 | stop new backfill and optional high-frequency sources; inspect attribution |
| `approval` | KRW 42,500 | guard actions plus owner approval for non-essential pipelines |
| `ceiling` | KRW 50,000 | nominate optional circuits to open, preserve auth/backup/recovery and ask owner priority |
| `unknown` | missing, stale or incomplete evidence | block new cost-increasing work and obtain current complete evidence |

These are review decisions, not a claim that a Cloud Billing budget automatically caps spend.

```bash
uv run python scripts/production_guardrails.py evaluate-cost \
  path/to/cost-snapshot.json --as-of 2026-09-09T12:00:00Z
```

### Release and rollback manifest

Every active Cloud Run service and Job must have an `active_targets` entry and a target-specific `rollback_targets`
entry. Both point to immutable repository/digest pairs. The manifest also fixes the minimum recent-version floor,
untagged minimum age and rollback/restore evidence retention window. Restore evidence must have a timestamp, durable
reference and `result=pass`.

```bash
uv run python scripts/production_guardrails.py validate-release \
  path/to/release-manifest.json
```

Before a future production cleanup review, the active digest in the manifest must exactly match the fresh resource
inventory, every active and rollback digest must exist in the Artifact Registry version inventory, and restore evidence
must still be inside the configured retention window.

## Cleanup dry-run and review gate

```bash
uv run python scripts/production_guardrails.py plan-cleanup \
  path/to/resource-inventory.json path/to/release-manifest.json \
  --as-of 2026-09-09T12:00:00Z
```

The planner protects, in this order, active manifest digests, rollback manifest digests, `prod-current`,
`prod-previous`, `rollback-*` tags and the configured recent-version floor. Other tagged images are retained. Only an
untagged image older than the configured minimum age can become a `candidate`; each row includes its reason.

Any incomplete inventory, active mismatch, missing active/rollback version, future-dated restore proof or expired
restore proof makes `complete=false` and emits blockers. Candidate rows may still be shown for diagnosis, but they do
not override blockers and never authorize deletion.

## Future production apply checklist

This checklist is intentionally inactive while MS-002 is stabilizing:

1. Confirm MS-002 is `closed` and the MS-003 production gate is satisfied.
2. Obtain owner/release approval for current production inventory capture and cleanup apply.
3. Capture both repositories completely and create a production release/rollback manifest from immutable digests.
4. Rehearse and record restore; validate that its evidence is inside the retention window.
5. Review a fresh dry-run, including every protected reason and candidate, and retain the reviewed output.
6. Implement/approve an apply mechanism in a production-authorized Work Item; do not repurpose this local CLI.
7. Re-inventory active targets and repositories after apply and preserve rollback and audit evidence.
