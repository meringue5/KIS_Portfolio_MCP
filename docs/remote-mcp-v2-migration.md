# Remote MCP V2 migration guide

> Status: inactive compatibility baseline for WI-044
> Product connection: OAuth Remote MCP only
> Production cutover: not authorized by this guide

## What changes

KIS Portfolio V2 replaces the endpoint-shaped V1 catalog of 35 tools with 18 outcome-shaped tools. Existing V1
connectors remain the rollback target until WI-046 explicitly activates V2. Do not remove or reconnect a working V1
connector merely because this guide exists.

V2 uses three separately consented scopes:

| Scope | Capability |
| --- | --- |
| `mcp:read` | portfolio, market, ledger, analytics, catalog, quality and pipeline-status reads |
| `mcp:collect` | the fixed `portfolio-refresh` managed pipeline request only |
| `mcp:journal.write` | owner-authored journal and typed thread revisions |

Adding command scopes must be an explicit reconnect/consent action. A current read-only grant is not automatically
expanded. V2 exposes no order scope and no order-placement tool.

## Client connection contract

Use the stable public HTTPS Remote MCP URL including `/mcp`. The OAuth authorization server must expose both
`/.well-known/oauth-authorization-server` and `/.well-known/openid-configuration`; the resource server must expose
protected-resource metadata and bind access tokens to the exact MCP resource.

For ChatGPT, follow the current OpenAI developer-mode MCP flow, start a **new conversation** after adding or changing
the connection, and refresh metadata after a deployed tool-contract change. OpenAI's official instructions require a
reachable public HTTPS endpoint or Secure MCP Tunnel for developer-mode testing; a local stdio server is not this
product connection path. See [Build an MCP server](https://developers.openai.com/plugins/build/mcp-server/) and
[Connect and test your plugin](https://developers.openai.com/plugins/deploy/connect-chatgpt/).

For Claude, add the same Remote MCP URL as a custom connector and enable it for the conversation. Anthropic documents
that Claude connects to Remote MCP from cloud infrastructure across claude.ai, Claude Desktop and mobile clients, so
the iPhone does not connect to a Mac-local server. See
[Get started with custom connectors using remote MCP](https://support.claude.com/en/articles/11175166-get-started-with-custom-connectors-using-remote-mcp).

UI metadata and actual execution are separate evidence. Validate discovery, authorization, `tools/list`, and a
representative tool call in a new conversation; do not declare success from a settings-screen tool count alone.

## V1 capability migration

The machine-readable SSOT is
[`governance/project/remote-mcp-v2-migration.toml`](../governance/project/remote-mcp-v2-migration.toml). It lists every
current V1 tool exactly once and is checked against both live builders in the test suite.

| V1 capability group | V2 destination | Migration behavior |
| --- | --- | --- |
| configured accounts, balance, total overview, overseas cash | `get-portfolio-overview` | aliases and canonical total/cash replace endpoint-shaped calls |
| token status and readiness | `get-data-quality` | credential-specific public details are removed |
| refresh all snapshots | `run-managed-pipeline` → `get-pipeline-run` | request `portfolio-refresh`, then poll the returned run ID |
| current domestic/US price and quote | `get-market-snapshot` | select the market explicitly |
| price, FX, instrument and technical history | `get-market-history` | freshness, quality and metric context are returned together |
| order, execution, transaction and settlement evidence | `get-trade-ledger` | canonical ledger replaces broker endpoint variants |
| domestic/overseas profit | `get-performance-history` + `get-trade-ledger` | result and supporting ledger evidence are separate |
| portfolio history, daily change, trend and allocation | `get-performance-history` + `get-portfolio-overview` | historical performance and current snapshot are separate |
| anomaly | `get-signal-status` | versioned signal, inputs and quality replace the V1 anomaly wrapper |
| domestic/overseas submit-order stubs | unsupported | V2 returns `unsupported_order_authority_absent`; use the broker's authorized trading interface |

The V2 catalog also adds governed position/thread, dividend, fundamental outlook, exposure, catalog, review queue and
owner journal commands. Presence in the inactive catalog does not imply that its backing source or production route is
active; inspect `quality` and `missing_coverage` on every read.

## New-conversation smoke matrix

Run this only after an approved V2 endpoint is available. Use synthetic identifiers for command validation and do not
paste account numbers, credentials or bearer tokens into prompts or evidence.

| Client | Required checks |
| --- | --- |
| Claude web/Desktop | discovery or initialize; exactly 18 tools; portfolio overview; KR/US market snapshot; actual call log |
| ChatGPT web | OAuth discovery and dynamic registration; exactly 18 tools in a new conversation; catalog and pipeline-status call |
| iPhone client | enable the existing Remote connector in a new conversation; portfolio read; owner-confirmed journal write with a fresh idempotency key |

Negative checks are mandatory: a read-only token cannot collect or write; a collect token cannot journal; a token for
another resource is rejected; stale expected revisions and reused idempotency keys with different inputs fail closed.

## Rollback and evidence

Before WI-046, rollback means leaving V1 untouched and reverting only the inactive V2 compatibility artifacts. During
an approved cutover, retain the V1 revision and OAuth issuer, record client-visible receipt separately from HTTP 200,
and return traffic to V1 if discovery, authorization, tool listing or representative calls fail.

The WI-044 repository suite is profile-replay evidence, not proof that a live connector or iPhone UI worked. Actual
client screenshots/logs, connector refresh and user-visible calls remain explicit production-gated evidence.
