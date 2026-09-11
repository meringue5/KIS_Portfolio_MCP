---
id: WI-044
title: Verify Remote MCP V2 clients and publish the migration guide
status: verified
type: maintenance
owner: owner
decision_refs: ADR-015, ADR-020, ADR-021
requirement_refs: DEC-029, DEC-034
milestone_ref: MS-003
delivery_refs: V2-W0606, V2-W0607
parent_work_item: none
depends_on: WI-042, WI-043
execution_scope: isolated
production_effects: none
architecture_impact: none; verifies approved public boundary
data_impact: none beyond synthetic/read-only smoke
security_impact: real OAuth discovery and scope negative tests
cost_impact: bounded scale-to-zero smoke
---

# WI-044 — Verify Remote MCP V2 clients and publish the migration guide

## Problem and evidence

Transport tests do not prove Claude, ChatGPT and iPhone connector behavior or a safe V1 tool migration path.

## Classification and contract

- `maintenance` compatibility and documentation verification.

## Scope

- Include discovery/auth/tool calls for portfolio, market, catalog, pipeline and journal plus unsupported mapping.
- Exclude production connector cutover.

## Acceptance criteria

- [ ] actual supported clients pass new-conversation calls and scope tests (production exit gate; unchanged).
- [x] recorded actual-client protocol profiles pass fresh inactive transport calls and scope tests.
- [x] every V1 tool has a V2 mapping or explicit unsupported response.
- [x] no local MCP product instruction remains in the migration guide.

## Change impact

- Parallel endpoint only; V1 remains rollback target.

## Plan

1. Build compatibility suite. 2. Run client smokes. 3. Publish migration and gap report.

## Sub-items

- `none`.

## Evidence

- 2026-09-11 isolated activation: WI-042 and WI-043 are verified, MS-003 remains in continuous isolated overlap and
  no other implementation Work Item is in progress. This phase is limited to recorded client-profile protocol
  fixtures, the inactive V2 transport, an exact V1-to-V2 migration manifest/guide and local verification.
- Official OpenAI documentation was refreshed for MCP server testing: Streamable HTTP, per-request authorization,
  public HTTPS or Secure MCP Tunnel for ChatGPT developer-mode testing, a new conversation for tool use and metadata
  refresh after contract changes. Repository guidance will cite the official source rather than preserve local-MCP
  product instructions.
- Activation does not authorize a public V2 endpoint, connector registration/reconnect, OAuth grant expansion,
  Cloud Run/IAM/Secret changes, live DB/KIS calls, deployment, traffic, client cutover or external messages. Actual
  client UI evidence remains an explicit production-gated acceptance item and will not be inferred from fixtures.
- `governance/project/remote-mcp-v2-migration.toml` and its strict loader cover the exact current 35-tool V1 and
  18-tool V2 catalogs. Thirty-three V1 tools have governed consolidated/async destinations; the two disabled order
  stubs return the explicit `unsupported_order_authority_absent` compatibility response.
- `tests/fixtures/remote_v2/client_profiles.json` replays recorded Claude web, ChatGPT web and Claude iOS cloud request
  profiles against a fresh inactive full V2 transport. Discovery/initialize, exact catalog and representative
  portfolio, market, catalog, pipeline and journal calls pass without session state; all results remain labelled
  fixture-only rather than live-client evidence.
- `docs/remote-mcp-v2-migration.md` is the Remote-only guide. It links current official client instructions, requires
  explicit command-scope consent, separates metadata UI from new-conversation execution and contains no local product
  setup command or localhost/stdio configuration.
- Verification: focused `7 passed`; MCP/OAuth/V2 adjacent regression `77 passed`; quick passed; full `597 passed` with
  all Project OS, data governance, architecture, warehouse and MCP gates. See
  `docs/operations/wi-044-isolated-verification-2026-09.md`.

## Closeout

- Result: verified for the isolated repository phase under the MS-003 overlap gate; production effects remain none.
- Remaining risk: actual Claude, ChatGPT and iPhone new-conversation calls and UI caching remain production-gated and
  must be verified separately from HTTP/server logs during WI-046. This result does not satisfy that live exit gate.
- Follow-up Work Item: WI-045.
