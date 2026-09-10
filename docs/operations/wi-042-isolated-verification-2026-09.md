# WI-042 isolated Remote MCP V2 read-surface verification — 2026-09-11

> Work Item: `WI-042`
> Phase: isolated repository verification
> Production effects: none

## Outcome

The repository now contains a parallel, inactive Remote MCP V2 read surface. It registers exactly the approved
15 read tools and leaves the one collect plus two journal commands to WI-043, preserving the total 18-tool budget.
The existing V1 35-tool builder and production `kis_portfolio.remote` composition are unchanged.

The V2 adapter owns bounded input schemas, versioned output-schema references, read-only annotations and the official
stateless JSON transport. The application boundary owns a complete query-handler port, request actor and scope/resource
authorization, safe versioned envelopes, a 256 KiB serialized response ceiling and a maximum 300-second query deadline.

## Verified contracts

- Exact read catalog: portfolio overview, position analysis, performance history, market snapshot/history, trade
  ledger/thread, dividend summary, fundamental outlook, exposure analysis, signal status, data catalog/quality,
  pipeline run and journal review queue.
- Composition fails closed unless all 15 application query handlers are supplied; the MCP handlers delegate typed
  requests instead of returning name-only placeholders or importing the V1 tool registry.
- OAuth context projection retains only actor ID, client ID, normalized scopes, resource and request ID. It does not
  retain the bearer. `mcp:read`, actor and exact resource are checked again at the application boundary.
- Response envelopes require schema version, as-of, source, freshness, quality, missing coverage, lineage reference,
  request ID and data. Raw payload, bearer/token/secret and full account-identifier keys fail closed.
- The official SDK transport is configured with `stateless_http=true`, `json_response=true`, a 4 MiB request-body
  maximum and exact resource/Claude Host-Origin policy. ChatGPT Origin is not guessed or allowlisted.
- Two fresh local transport instances independently returned the same 15-tool catalog without an MCP session header.
  This is deterministic replica-equivalent fixture evidence, not the actual WI-044 two-replica/client smoke.

## Verification evidence

- Focused V2 DTO, authorization, leakage, deadline and transport suite: `19 passed`.
- Remote OAuth, governance read model, production cost/release and deployment contract regression: `136 passed`.
- `bash scripts/check.sh quick`: passed; V1 MCP surface remains exactly `35 tools`.
- `bash scripts/check.sh full`: `575 passed`; Project OS, data governance, architecture, warehouse and MCP gates passed.
- One existing third-party Authlib deprecation warning remained; no new warning was introduced.

## Isolation and rollback

No public endpoint, OAuth grant/scope advertisement, live DB/KIS request, credential, IAM/Secret, Cloud Run/Scheduler,
deployment, traffic, client cutover, V1 retirement or external message was changed. `kis_portfolio.remote` does not
import or activate the V2 module. Rollback is the deletion/revert of the new inactive service, adapter and fixture files;
the V1 runtime remains the operational target throughout.

## Remaining gates

- WI-043 owns `mcp:collect` and `mcp:journal.write` advertisement, authorization and managed commands.
- WI-044 owns actual client protocol behavior, allowed client Origins and real two-replica compatibility evidence.
- WI-045/046 own dual-run readiness, release approval, production composition and traffic cutover.
