# Final V2 Architecture Audit — 2026-09-14

## Outcome

WI-051 is closed. Five obsolete re-export shims are gone, the production Remote imports only the V2 adapter, the
public MCP surface remains 18 tools, and architecture, warehouse, MCP, release and full gates pass. The eight
canonical Cloud Run runtimes converged on one immutable image in corrected production run `34824514114`.

## Contract audit

| Boundary | Result | Evidence |
|---|---|---|
| Architecture | pass | obsolete shims removed; retired root entrypoint retained only as fail-closed migration diagnostic |
| MCP | pass | production Remote uses V2; public tool count 18 |
| Warehouse | pass with bounded exceptions | no missing managed object; four exact drift fingerprints have owner and 2026-12-14 expiry |
| Security | pass | OAuth trust boundary, unauthenticated `/mcp` 401, scoped runtime identities and secret references verified read-only |
| Cost/capacity | pass | min 0/max 1 service baseline and same-day steady-state cost review remain normal |
| Release | pass | two services and six Jobs use `sha256:31f8fed...c10b0`; exact new service revisions receive 100% traffic |
| Full gate | pass | 717 tests; one existing Authlib deprecation warning |

The detailed machine-readable snapshot is
[`governance/project/evidence/wi051/final-v2-architecture-audit-2026-09-14.json`](../../governance/project/evidence/wi051/final-v2-architecture-audit-2026-09-14.json).

## Prepared production end gate

The protected `wi051-final-audit` workflow target builds once and requires a secret-free rollback manifest before it
updates any runtime. It changes only image and provenance labels for two services and six Jobs. It does not execute a
Job or modify Scheduler, IAM, Secret, database, source activation, command/args, service account or runtime env.
After updates it verifies auth/Remote health, protected-resource metadata and the unauthenticated `/mcp` 401 boundary.

The owner authorized the production workflow. Corrected run `34824514114` completed successfully from master
`e458ba5`, and WI-032 now owns the final documentation truth cutover.

## First-run correction

Owner-approved run `34823473028` succeeded at the workflow level and updated the six Job definitions, but independent
traffic inspection found that Cloud Run retained revision-pinned service traffic. Auth still served its prior stable
revision and Remote still served its prior tagged revision even though each service template pointed at the new
digest. The run was therefore not accepted as completion evidence.

The corrected target records the actual 100% serving revision rather than `latestReadyRevision`, gives each new
service revision a run-scoped suffix, promotes those exact revisions, and restores already-promoted services if a
later promotion or smoke fails. The correction stays within the approved image-only release scope.

## Corrected production evidence

Corrected run `34824514114` built digest
`sha256:31f8fed5b2ef9527272634a93d8608fa215dc16a95c813381fd94ad8409c10b0` once, updated the six canonical Job
definitions, created run-scoped auth and Remote revisions, and routed each service 100% to its exact new revision.
All unrelated workflow stages were skipped and no Job was executed.

Post-release HTTP verification returned 200 for auth health and authorization-server metadata, 200 for Remote health
and protected-resource metadata, and 401 for unauthenticated `/mcp`. The protected-resource metadata still names the
canonical `/mcp` resource and auth server. Artifact `wi051-rollback-manifest-34824514114` (ID `10340250702`, 30-day
retention) records the actual prior 100% serving revisions plus the prior immutable image for all six Jobs. Scheduler,
IAM, Secret, database and source activation were not changed.
