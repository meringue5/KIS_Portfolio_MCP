# KIS Portfolio documentation map

> Status: canonical V2 documentation index
> Product baseline: OAuth Remote MCP `KIS Portfolio`, Firestore operational state, MotherDuck V2 data plane

This index is the single navigation entrypoint for current implementation and operations. A document may mention V1
as migration or forensic history without becoming a current runtime instruction. The machine-readable disposition is
[`governance/project/v1-document-disposition.toml`](../governance/project/v1-document-disposition.toml), and
`scripts/check_v2_documentation.py` fails when a newly tracked V1-era Markdown document has no classification.

## Canonical V2 paths

| Concern | Canonical owner |
| --- | --- |
| Product purpose and decisions | [`SPEC.md`](../SPEC.md), [`requirements/`](requirements/) |
| Implemented architecture and package boundaries | [`ARCHITECTURE.md`](../ARCHITECTURE.md) |
| Public MCP tools and capability boundary | [`api-capability-map.md`](api-capability-map.md), [`design/kis-portfolio-v2-system-design.md`](design/kis-portfolio-v2-system-design.md) |
| Client onboarding and connector recovery | [`remote-mcp-v2-migration.md`](remote-mcp-v2-migration.md) |
| Data object and pipeline contracts | [`data-catalog.md`](data-catalog.md), [`data-pipeline.md`](data-pipeline.md), [`governance/data-governance-harness.md`](governance/data-governance-harness.md) |
| Security and secrets | [`security-and-secrets.md`](security-and-secrets.md) |
| Deployment and rollback | [`deployment.md`](deployment.md) |
| Backup, restore, cost and routine operations | [`backup.md`](backup.md), [`operations/steady-state-operations-runbook.md`](operations/steady-state-operations-runbook.md), [`operations/production-cost-release-guardrails.md`](operations/production-cost-release-guardrails.md) |
| Project workflow and traceability | [`governance/project-operating-system.md`](governance/project-operating-system.md), [`traceability.md`](traceability.md), [`milestones/README.md`](milestones/README.md) |

## Current product baseline

- The only user-facing product connection is the stable HTTPS `/mcp` custom connector named `KIS Portfolio`.
- `kis-portfolio-mcp` and root `server.py` are fail-closed migration diagnostics, not alternate servers.
- Production auth and Remote use OAuth with separate Cloud Run identities. Firestore `kis-portfolio-state` owns
  operational OAuth/KIS-token/lease/run-request state; MotherDuck owns analytical Bronze/Silver/Gold/Control data.
- The public catalog contains 18 V2 tools and no order tool. Managed writes require their dedicated OAuth scopes and
  fixed governed commands.
- Recovery rolls forward to the last verified immutable V2 image/config. Retained V1 artifacts are not traffic or
  data recovery targets.

## Historical material

Work Items, dated design/operations evidence and prior milestone records remain discoverable in place. They describe
what was known or permitted at their recorded time and do not override this index or the canonical owners above.
`remote-mcp-v2-migration.md` is the sole supersession redirect retained for users who still encounter a local V1
connector. WI-032 approves no documentation deletion candidate and no production mutation.
