---
id: WI-047
title: Retire local setup and the V1 public MCP surface
status: closed
type: maintenance
owner: owner
decision_refs: ADR-020, ADR-021, ADR-028
requirement_refs: DEC-034, DEC-047, DEC-056
milestone_ref: MS-004
delivery_refs: V2-W0801, V2-W0802
parent_work_item: none
depends_on: WI-046
execution_scope: isolated
production_effects: none
architecture_impact: removes superseded public adapters after cutover
data_impact: none
security_impact: removes obsolete public capability including order stubs
cost_impact: may reduce deployment and support surface
---

# WI-047 — Retire local setup and the V1 public MCP surface

## Problem and evidence

After V2 cutover, local product setup and the V1 tool catalog would remain a conflicting public surface.

## Classification and contract

- `maintenance` retirement under the approved Remote-only and V2 forward-recovery decisions.

## Scope

- Include setup/connector removal, V1 catalog and disabled order stub retirement, compatibility diagnostics.
- Exclude V1 data or runtime resource deletion.

## Acceptance criteria

- [x] fresh setup exposes only the OAuth Remote V2 registration path and V1 calls receive explicit migration guidance.
- [x] public tool/security/full gates pass.

## Change impact

- Public compatibility change after completed cutover; recovery rolls forward from the last verified V2 image/config.

## Plan

1. Verify zero supported use. 2. Remove public registration. 3. Test explicit migration guidance and V2 forward recovery.

## Sub-items

- `none`.

## Evidence

- Activated 2026-09-13 after DEC-056 owner acceptance closed WI-046/MS-003 and established V2 as the only production
  baseline. This phase is repository/setup/fixture work only; live resource deletion remains outside WI-047.
- `scripts/setup.sh` now validates the canonical HTTPS `/mcp` URL, removes only the exact local `kis-portfolio`
  registration after a timestamped backup, and guides the owner to the `KIS Portfolio` OAuth Remote connector.
- `kis-portfolio-mcp` and root `server.py` now fail closed with `v1_public_surface_retired` migration guidance.
- Remote runtime and deploy workflow default to V2 and reject V1 activation; the public-surface audit verifies the exact
  18-tool catalog and absence of order stubs. Internal V1 migration/data code remains preserved.
- Verification: focused retirement/auth/deploy suites passed; `bash scripts/check.sh quick` passed with 18 public tools;
  `bash scripts/check.sh full` passed with 671 tests and one existing Authlib deprecation warning.

## Closeout

- Result: closed; V1 local/setup/public MCP activation paths are retired without deleting V1 data or runtime resources.
- Remaining risk: hidden local config entries are removed only when `setup.sh` is explicitly run; destructive runtime
  cleanup remains separately gated.
- Follow-up Work Item: WI-048, then WI-049/WI-050 by dependency.
