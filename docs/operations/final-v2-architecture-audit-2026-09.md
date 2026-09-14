# Final V2 Architecture Audit — 2026-09-14

## Outcome

WI-051 repository scope is verified. Five obsolete re-export shims are gone, the production Remote imports only the
V2 adapter, the public MCP surface remains 18 tools, and architecture, warehouse, MCP, release and full gates pass.
The only open production gate is convergence of the eight canonical Cloud Run runtimes on one immutable image.

## Contract audit

| Boundary | Result | Evidence |
|---|---|---|
| Architecture | pass | obsolete shims removed; retired root entrypoint retained only as fail-closed migration diagnostic |
| MCP | pass | production Remote uses V2; public tool count 18 |
| Warehouse | pass with bounded exceptions | no missing managed object; four exact drift fingerprints have owner and 2026-12-14 expiry |
| Security | pass | OAuth trust boundary, unauthenticated `/mcp` 401, scoped runtime identities and secret references verified read-only |
| Cost/capacity | pass | min 0/max 1 service baseline and same-day steady-state cost review remain normal |
| Release | pending one production action | live runtimes are healthy but currently span five image digests |
| Full gate | pass | 716 tests; one existing Authlib deprecation warning |

The detailed machine-readable snapshot is
[`governance/project/evidence/wi051/final-v2-architecture-audit-2026-09-14.json`](../../governance/project/evidence/wi051/final-v2-architecture-audit-2026-09-14.json).

## Prepared production end gate

The protected `wi051-final-audit` workflow target builds once and requires a secret-free rollback manifest before it
updates any runtime. It changes only image and provenance labels for two services and six Jobs. It does not execute a
Job or modify Scheduler, IAM, Secret, database, source activation, command/args, service account or runtime env.
After updates it verifies auth/Remote health, protected-resource metadata and the unauthenticated `/mcp` 401 boundary.

WI-051 remains `in_progress` until the owner explicitly authorizes that production workflow and post-release evidence
shows one digest across all eight canonical runtimes. WI-032 then owns the final documentation truth cutover.

## First-run correction

Owner-approved run `34823473028` succeeded at the workflow level and updated the six Job definitions, but independent
traffic inspection found that Cloud Run retained revision-pinned service traffic. Auth still served its prior stable
revision and Remote still served its prior tagged revision even though each service template pointed at the new
digest. The run was therefore not accepted as completion evidence.

The corrected target records the actual 100% serving revision rather than `latestReadyRevision`, gives each new
service revision a run-scoped suffix, promotes those exact revisions, and restores already-promoted services if a
later promotion or smoke fails. The correction stays within the approved image-only release scope.
