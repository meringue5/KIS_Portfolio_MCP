# WI-043 isolated Remote MCP V2 managed-command verification — 2026-09-11

> Work Item: `WI-043`
> Phase: isolated repository verification
> Production effects: none

## Outcome

The inactive Remote MCP V2 builder now contains the exact approved 18-tool budget: the verified 15 reads plus one
managed collection command and two owner journal/thread revision commands. The existing V1 35-tool builder and
production `kis_portfolio.remote` composition remain unchanged.

`run-managed-pipeline` accepts only the public `portfolio-refresh` alias, one logical date, one of the three owned-core
slots and an idempotency key. The application maps this to the fixed `pipeline.owned-portfolio-core-v2` version and
fixed slot-specific Job name, returns a deterministic run ID immediately and exposes no arbitrary command, SQL,
container argument, environment or timeout field. Status polling remains the already verified `get-pipeline-run` read.

`upsert-trade-journal` and `revise-trade-thread` require an owner subject, `mcp:journal.write`, an exact resource,
timezone-aware authorship time, expected revision and idempotency key. Thread changes are a discriminated union of
thread metadata, explicit lot link or explicit sell allocation; untyped patches are not accepted.

## Verified contracts

- `mcp:read`, `mcp:collect` and `mcp:journal.write` are checked per tool and again in the application boundary. A read
  token cannot collect or write, and collect/journal scopes are not interchangeable.
- OAuth projection retains subject, client, normalized scopes, resource and request ID only. A client without an owner
  subject cannot write owner intent, and no bearer value crosses the adapter boundary.
- Firestore-compatible `run_requests` state plus a fenced lease makes command replay deterministic. A repeated key and
  identical request reuses the result; a changed request fails with `idempotency_conflict`; an overlapping request
  fails with `command_in_progress` without dispatching twice.
- The local managed-command port receives only the normalized fixed Job request. The local revision port is atomic,
  append-only and records actor/client/request evidence while rejecting stale expected revisions.
- V2 has no order tool or order scope. Existing OAuth grants were not expanded or changed.

## Verification evidence

- Focused command plus adjacent V2 read surface: `34 passed`.
- `bash scripts/check.sh quick`: passed; V1 MCP surface remains exactly `35 tools`.
- `bash scripts/check.sh full`: `590 passed`; Project OS, data governance, architecture, warehouse and MCP gates passed.
- One existing third-party Authlib deprecation warning remained; no new warning was introduced.

## Isolation and rollback

No OAuth grant/scope advertisement, actual Job execution, live DB/KIS write, migration apply, IAM/Secret,
Cloud Run/Scheduler, deployment, public catalog, client connection, traffic or external message changed. The command
application and local ports are not imported by `kis_portfolio.remote`. Rollback is a revert of the inactive command
service, local fixture port, V2 builder extension and tests; the production V1 runtime and data remain untouched.

## Remaining gates

- WI-044 owns actual Claude/ChatGPT/iPhone discovery, authentication, tool-call compatibility and migration guidance.
- WI-045 owns dual-run recovery and cost readiness.
- WI-046 owns production adapters, OAuth consent/grants, infrastructure, public activation and traffic cutover after
  the production gate opens.
