---
id: WI-051
title: Remove obsolete shims and complete the final V2 architecture audit
status: closed
type: architecture
owner: owner
decision_refs: ADR-021, ADR-022, ADR-023
requirement_refs: DEC-033..041, DEC-047
milestone_ref: MS-004
delivery_refs: V2-W0806
parent_work_item: none
depends_on: WI-047, WI-048, WI-049, WI-050
execution_scope: isolated
production_effects: none
architecture_impact: establishes the implemented final V2 boundary
data_impact: verifies warehouse contract and drift; no silent deletion
security_impact: verifies trust boundaries and obsolete privileges
cost_impact: verifies final steady-state forecast
---

# WI-051 — Remove obsolete shims and complete the final V2 architecture audit

## Problem and evidence

After retirement work, obsolete code/shims and cross-document drift may still contradict the implemented V2 system.

## Classification and contract

- `architecture` final implementation audit before documentation canonicalization.

## Scope

- Include obsolete package/shim removal and architecture, MCP, warehouse, security, release and cost audit.
- Exclude rewriting historical evidence or deleting data without approval.

## Acceptance criteria

- [x] no obsolete runtime path or unauthorized dependency remains.
- [x] architecture, warehouse, MCP, security, release and full gates pass with live evidence.
- [x] residual exceptions have owners and expiry.

## Change impact

- Final code boundary cleanup with prior release as rollback.

## Plan

1. Inventory residuals. 2. Remove bounded shims. 3. Run all audits and live smokes.

## Sub-items

- `none`.

## Evidence

- Activated 2026-09-14 from master `9bf78a9` after WI-047 through WI-050 closed. The active phase is limited to
  repository inventory, bounded removal of proven-obsolete code/shims, deterministic audit tooling, read-only live
  inspection and local verification. It does not rewrite historical evidence, delete data, deploy, change IAM or
  Secrets, activate sources, mutate production, or perform the WI-032 documentation truth cutover.
- Removed five proven-obsolete re-export shims while preserving the retired root diagnostic and internal V1 fixture
  surface. Focused architecture/security tests and the quick gate pass.
- Live read-only warehouse inventory has no missing managed object. Its three retained V1 objects and one managed
  column fingerprint match four exact non-authorizing exceptions owned by `owner`, expiring 2026-12-14.
- The release audit found canonical runtime image drift: auth, Remote/core, domestic history, overseas history and
  token warm-up were healthy but did not share the architecture-approved single digest. The repository now has a
  protected `wi051-final-audit` target that builds once, captures a secret-free rollback manifest, updates only the
  image/provenance of two services and six Jobs, executes no Job and changes no Scheduler/IAM/Secret/DB/source. Its
  66 focused deployment tests, CLI flag inspection, local dry-run and quick gate pass. Production execution remains
  deliberately pending explicit owner authorization.
- Full gate passed 716 tests with one existing Authlib deprecation warning. The repository/live pre-release audit is
  recorded in `governance/project/evidence/wi051/final-v2-architecture-audit-2026-09-14.json`; WI-051 stays in progress
  until the protected release runs and all eight canonical runtimes are verified on one digest.
- First production run `34823473028` built once and updated all desired images, but independent inspection found the
  two services still pinned traffic to older revisions. The initial manifest also recorded latest-ready rather than
  the actual 100% serving revision. WI-051 therefore remained open. The correction records actual serving traffic,
  creates predictable run-scoped revisions, explicitly promotes those revisions and automatically restores prior
  traffic on promotion/smoke failure; focused deployment tests increased to 67 passing.
- Corrected owner-approved run `34824514114` from master `e458ba5` built immutable digest
  `sha256:31f8fed5b2ef9527272634a93d8608fa215dc16a95c813381fd94ad8409c10b0`, updated all six canonical Jobs and
  deployed run-scoped auth/Remote revisions. Workflow and independent evidence show 100% traffic on
  `kis-portfolio-auth-wi051-34824514114` and `kis-portfolio-remote-wi051-34824514114`. Public post-release smoke
  returned 200 for both health endpoints and both OAuth metadata endpoints, and 401 for unauthenticated `/mcp`.
- Rollback artifact `wi051-rollback-manifest-34824514114` (artifact `10340250702`, 30-day retention) preserves the
  actual prior 100% serving revisions and prior immutable digest for all six Jobs. No Job was executed and every
  unrelated deploy stage was skipped; Scheduler, IAM, Secret, database and source activation remained unchanged.
- Final repository gate passed 717 tests with the same existing Authlib deprecation warning.

## Closeout

- Result: closed on corrected production convergence and post-release boundary verification.
- Remaining risk: documentation truth cutover belongs to WI-032.
- Follow-up Work Item: WI-032.
