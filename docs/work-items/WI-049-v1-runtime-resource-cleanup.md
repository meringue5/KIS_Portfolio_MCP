---
id: WI-049
title: Approve and execute bounded V1 runtime resource cleanup
status: in_progress
type: maintenance
owner: owner
decision_refs: ADR-020, ADR-021
requirement_refs: DEC-034, DEC-041, DEC-047
milestone_ref: MS-004
delivery_refs: V2-W0804
parent_work_item: none
depends_on: WI-047
execution_scope: isolated
production_effects: none; S02 exact Job cleanup completed and S03 remains review-only until separately approved
architecture_impact: removes superseded deployment resources
data_impact: no data deletion
security_impact: obsolete identities/secrets require scoped review
cost_impact: S02 removed obsolete control-plane definitions; S03 may reduce Artifact Registry storage after separate approval
---

# WI-049 — Approve and execute bounded V1 runtime resource cleanup

## Problem and evidence

Past images, Jobs and Schedulers should not remain indefinitely after rollback confidence, but cleanup is destructive.

## Classification and contract

- `maintenance` with target-by-target destructive approval and recovery evidence.

## Scope

- Include exact resource manifest, dependency checks, retained rollback artifacts and bounded removal.
- Exclude databases, backups and active V2 resources.
- Permanently protect canonical total-asset snapshots and holdings, domestic/overseas order and transaction history,
  trade/cash/lot/thread/journal history, V2 Bronze/Silver/Gold/Control objects, local and private-GCS recovery artifacts,
  and every object referenced by a current backup manifest. WI-049 cannot authorize their deletion.

## Acceptance criteria

- [x] owner approves exact targets and recovery artifacts.
- [x] active/rollback/V2 resources cannot match cleanup.
- [x] post-cleanup smoke and S02 cost evidence pass.
- [ ] Artifact Registry versions receive an independent exact-digest retain/delete decision.

## Change impact

- Destructive but recoverable deployment cleanup.

## Plan

1. Freeze read-only inventory, protected history and recovery evidence. 2. Obtain exact-target approval and remove
   only retired one-time Job definitions. 3. Re-inventory and smoke the canonical runtime. 4. Review Artifact Registry
   versions as a separate destructive family; never infer image approval from Job approval.

## Sub-items

- `WI-049-S01` — verified: freeze runtime inventory, history protections and recovery evidence.
- `WI-049-S02` — closed: executed and verified owner-approved one-time Cloud Run Job cleanup.
- `WI-049-S03` — in progress: prepare an exact-digest retain/delete specification in read-only scope; deletion remains
  disabled until separate owner approval.

## Evidence

- Activated 2026-09-13 after WI-048 closed. The current isolated phase is read-only inventory, dependency analysis,
  recovery capture and exact cleanup-manifest generation; production deletion, IAM/Secret mutation and Scheduler or
  Cloud Run changes remain disabled until the owner reviews the exact targets and recovery artifacts.
- Owner reaffirmed that total-asset and trade-history preservation is critical. Repository evidence records only
  aggregate metadata and resource names; portfolio values, holdings, account identifiers and secret values are
  excluded.
- `WI-049-S01` froze 15 protected dataset row-count baselines, 19 protected runtime/storage resources, 11 unscheduled
  one-time Cloud Run Job candidates, their last successful executions, non-secret configuration hashes, deployment
  references and exact recovery references in
  `governance/project/evidence/wi049/runtime-cleanup-readiness-2026-09-13.json`. The review-only schema forces
  `apply_allowed=false`, `owner_approved=false` and denies data, backup, IAM, Secret and Scheduler changes.
- The latest private WI-048 post-backup index exists at its content-addressed URI with SHA-256
  `bc91f37b...68da0`; its production workflow already passed fresh restore. No new backup or database write was needed
  for this read-only phase.
- Artifact Registry inventory found 64 untagged versions older than 30 days in `cloud-run-source-deploy`, but none is
  authorized or nominated by S01. Image cleanup remains S03 because active, forward-recovery and Job-recreation
  digests must be protected independently from Job-definition cleanup.
- Focused guardrail verification passed 23 tests; related guardrail/readiness verification passed 33 tests; the full
  gate passed 682 tests with one existing Authlib deprecation warning. No Cloud Run, Scheduler, IAM, Secret, Firestore,
  MotherDuck, GCS or Artifact Registry mutation occurred.
- On 2026-09-14 the owner approved all 11 exact S02 Job names and reaffirmed the exclusions. The approval artifact
  exactly matches the frozen candidate set and continues to exclude images, backups, data, IAM, Schedulers, Secrets and
  services. S02 production effects are now limited to those exact Job definitions.
- The S02 implementation adds no local apply path: `--apply` fails unless it runs in GitHub Actions from
  `refs/heads/master`. Its live dry-run revalidated all 11 exact image/configuration hashes, found no Scheduler target,
  and confirmed the immutable private backup index still exists; `deleted_names=[]`. The production workflow will
  re-run the same preflight, delete exact names without a wildcard, verify all approved names are absent, preserve all
  six scheduled Jobs and six Schedulers, then smoke Auth/Remote health and the unauthenticated MCP 401 boundary.
- S02 implementation verification passed 92 focused tests and the full 690-test gate with one existing Authlib
  deprecation warning.
- PR #101 merged as `f8920a1`; master workflow run `34781573015` then deleted the exact 11 approved Job definitions.
  The workflow did not deploy or mutate any service, scheduled Job, Scheduler, identity, Secret, database, backup or
  image, and its Auth/Remote health plus unauthenticated MCP 401 smoke passed.
- Post-cleanup inventory found the six protected Cloud Run Jobs ready, all six protected Schedulers enabled and both
  canonical services ready. The private WI-048 backup index remained present at the frozen content address.
- A direct aggregate-only MotherDuck check compared all 15 protected history objects with the S01 baseline. Every
  count was unchanged and none decreased, including total assets, holdings, domestic/overseas transactions, realized
  trades, trade/cash revisions, positions and trade threads. The machine-readable result is
  `governance/project/evidence/wi049/runtime-cleanup-result-2026-09-14.json`.
- S02 is cost-neutral for compute because the deleted one-time definitions were idle. Possible Artifact Registry
  storage savings remain S03 and are not authorized by this closeout.
- WI-049-S03 entered its isolated read-only specification phase on 2026-09-14. Repository work may classify exact
  digests and freeze recovery references, but cannot delete an image or mutate Artifact Registry.
- The fresh S03 inventory corrected the earlier approximate age-eligible count: 108 versions exist across two
  repositories and six packages. The approved WI-035 policy classifies 49 for retention and 59 exact untagged,
  age-eligible versions as removal candidates, representing 5,996,113,502 logical image bytes before shared-layer
  adjustment. All 33 `kis-portfolio` repository versions remain retained. The specification is
  `governance/project/evidence/wi049/artifact-cleanup-spec-2026-09-14.json`; apply and owner approval are false.
- A second live read-only comparison proved the exact retain/removal union equals all 108 current versions with no
  inventory drift, no overlap and no tagged removal candidate. Three focused specification tests and Project OS quick
  passed. No Artifact Registry mutation occurred.

## Closeout

- Result: WI-049-S02 closed; exact-target production cleanup and preservation checks passed. WI-049 remains in
  progress only for the independently gated S03 Artifact Registry decision.
- Remaining risk: the deleted Job execution views now rely on the frozen manifest and GitHub evidence. No image digest
  is approved for deletion; S03 requires a fresh exact-digest review and owner approval or an explicit retain decision.
- Follow-up Work Item: WI-051.
