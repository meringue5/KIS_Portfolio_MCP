# WI-044 isolated Remote MCP V2 client-compatibility verification — 2026-09-11

> Work Item: `WI-044`
> Phase: isolated repository verification
> Production effects: none

## Outcome

The repository now has an executable 35-to-18 migration manifest, a Remote-only client migration guide and three
recorded client request profiles. Each profile starts a fresh inactive stateless transport, performs its observed
discovery or initialize handshake, lists the exact 18-tool catalog and invokes its assigned portfolio, market,
catalog, pipeline-status or journal command. These are protocol-equivalent fixtures, not live client UI evidence.

The full V2 transport builder remains inactive and composes the WI-042 read application with the WI-043 command
application only for local compatibility verification. `kis_portfolio.remote` remains the V1 production composition.

## Compatibility evidence

| Profile | Fresh-instance flow | Representative calls | Result |
| --- | --- | --- | --- |
| recorded Claude web | `server/discover` 2026 profile → `tools/list` | portfolio overview, KR market snapshot | pass |
| recorded ChatGPT web | initialize 2025-06-18 → `tools/list` | data catalog, pipeline status | pass |
| recorded Claude iOS cloud | initialize 2025-06-18 → `tools/list` | owner journal revision | pass |

All responses are JSON, stateless and structured; no MCP session header is required. The server advertises exactly 18
tools. The fixture explicitly marks `not_live_client_evidence` so it cannot be presented as a successful production
connector or client-visible receipt.

## Migration and authorization evidence

- `governance/project/remote-mcp-v2-migration.toml` lists every current V1 tool exactly once and exactly the 18 V2
  tools. Thirty-three V1 tools consolidate or become asynchronous; only the two disabled order stubs are unsupported.
- Unsupported order lookups produce a stable `unsupported_order_authority_absent` response with no replacement tool.
- Default OAuth scope configuration remains `mcp:read offline_access`. The local fixture proves all three business
  scopes can be explicitly advertised while a dynamically registered read client remains read-only; no existing grant
  is expanded.
- The migration guide contains no local product setup command, localhost URL, stdio configuration or desktop config.
  It points users to one OAuth Remote MCP `/mcp` URL and separates settings metadata from new-conversation execution.
- Official OpenAI and Anthropic client documentation is linked directly from the guide. Exact UI availability remains
  account/workspace dependent and is not inferred by the repository.

## Verification evidence

- Focused client compatibility suite: `7 passed`.
- MCP surface plus OAuth/V2 adjacent regression: `77 passed`.
- `bash scripts/check.sh quick`: passed; V1 MCP surface remains exactly `35 tools`.
- `bash scripts/check.sh full`: `597 passed`; Project OS, data governance, architecture, warehouse and MCP gates passed.
- One existing third-party Authlib deprecation warning remained; no new warning was introduced.

## Isolation, rollback and remaining production gate

No public V2 endpoint, connector registration/reconnect, OAuth grant, live DB/KIS request, credential, IAM/Secret,
Cloud Run/Scheduler, deployment, traffic, cutover or external message changed. Rollback is a revert of the inactive
full-transport helper, migration manifest/loader, guide and fixtures; V1 production remains untouched.

The original live-client acceptance is not claimed by this verification. After the production gate opens, WI-046 must
deploy the approved V2 composition and collect actual Claude, ChatGPT and iPhone new-conversation discovery, auth,
tool-call, server-log and client-visible receipt evidence. UI screenshots or HTTP 200 alone are insufficient.
