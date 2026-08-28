---
id: WI-032
title: Consolidate V1 documentation and establish V2 as the canonical baseline
status: proposed
type: governance
owner: owner
decision_refs: DEC-047
requirement_refs: DEC-034, DEC-045, DEC-047, GOV-003, GOV-007
milestone_ref: MS-004
delivery_refs: V2-W0807
parent_work_item: none
depends_on: WI-051
architecture_impact: final documentation cutover makes the implemented V2 architecture canonical and retires conflicting V1 guidance
data_impact: reconciles catalog and migration documentation; no data deletion is implied
security_impact: security and secrets documentation must remain canonical and must not expose values
cost_impact: repository-local documentation work; no runtime cost
---

# WI-032 — Consolidate V1 documentation and establish V2 as the canonical baseline

## Problem and evidence

V2 is being implemented alongside retained V1 code, objects and historical documents. At final cutover, leaving both
generations as apparently current guidance would create multiple SSOTs for setup, architecture, MCP surface, data,
deployment and operations. The owner requires the final project milestone to clean up the V1-era documentation and
make V2 the canonical baseline.

## Classification and contract

- Classification: `governance` and documentation cutover.
- Compared contracts: DEC-034 Remote MCP SSOT, DEC-045 preservation-first migration, Project OS decision ownership,
  V2 delivery Wave 8 and current root/docs navigation.
- Contract result: approved addition. Historical evidence is preserved, while current instructions and decision links
  must resolve to one V2 canonical set.
- Approval: planning is approved; actual retirement runs only in MS-004 after MS-003 cutover evidence.

## Scope

- Include: inventory all V1/current docs, classify keep/rewrite/archive/remove-link, update root navigation and
  onboarding, reconcile SPEC/ARCHITECTURE/requirements/design/catalog/pipeline/security/deployment/runbooks, add clear
  supersession markers and validate links/commands against the final V2 runtime.
- Include: preserve decision and migration history in an archive or explicit historical section rather than deleting
  evidence merely because it is V1.
- Exclude: destructive deletion of live data/resources, rewriting Git history, or claiming V2 canonical before cutover
  and verification are complete.

## Acceptance criteria

- [ ] Every tracked V1-era document is classified as canonical V2, retained historical evidence, superseded redirect,
  or approved deletion candidate.
- [ ] One canonical V2 path exists for architecture, requirements/decisions, MCP surface, data catalog/pipeline,
  security/secrets, deployment, backup/restore, cost and onboarding.
- [ ] Fresh-clone and iPhone/Remote MCP instructions contain no local MCP product-path ambiguity.
- [ ] Commands, links, object names and service names in canonical docs match the verified final implementation.
- [ ] Historical decisions, migration mappings and evidence remain discoverable and are not silently overwritten.
- [ ] Architecture, MCP surface, warehouse, release and Project OS full gates pass.

## Change impact

- Architecture: documentation becomes the final V2 architectural SSOT.
- Data/schema/backup: catalog and recovery instructions are reconciled; no physical deletion in this WI without a
  separately approved destructive sub-item or Work Item.
- Security/privacy: preserve least-privilege and Secret Manager policy; scan outputs for secret/account leakage.
- MCP/API compatibility: V1 aliases and local setup are documented only as historical/transition material after cutover.
- Deployment/rollback: retain the pre-retirement doc manifest/tag so redirects and prior instructions can be restored.
- Cost/SLO: no runtime cost; verify the monthly-cost and operational-SLO docs remain current.

## Plan

1. Generate a complete document inventory and ownership/classification matrix.
2. Verify the implemented V2 runtime, schema, deployment and public MCP surface.
3. Rewrite canonical documents and add explicit supersession/archive links for historical V1 material.
4. Run link, command, architecture, warehouse, release and full repository gates.

## Sub-items

- `none` at baseline. Newly discovered documents stay within this outcome as stable sub-items; independent destructive
  resource retirement remains a separate Work Item.

## Evidence

- Commands/tests: pending MS-004 execution.
- Operating evidence: pending V2 cutover and final audit.

## Closeout

- Result: proposed.
- Remaining risk: cannot start until MS-003 cutover evidence establishes what V2 actually is.
- Follow-up Work Item: none allocated.
