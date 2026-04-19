# KIS Portfolio Operations

Use this skill when the user asks to inspect, summarize, compare, or explain KIS account and portfolio data through this project's MCP tools.

## Operating Principles

- Treat this project as a read-first portfolio operations console.
- Prefer DB-only tools for historical or aggregate questions before calling live KIS APIs.
- Use live balance tools only when the user asks for current account data or when DB data is stale.
- Never place orders as part of portfolio inspection, rebalancing suggestions, or account summaries.
- Keep account numbers out of prose unless the user explicitly asks for raw account identifiers.
- When totals differ across tools, explain whether the value came from a live API response or a MotherDuck snapshot.

## Preferred Tool Order

1. For latest aggregate state, call `get-latest-portfolio-summary`.
2. For daily movement, call `get-portfolio-daily-change`.
3. For one account's history, call `get-portfolio-history`.
4. For trend or anomaly analysis, call `get-portfolio-trend` or `get-portfolio-anomalies`.
5. For a fresh current balance, call `inquery-balance` on the relevant MCP account instance.

## Standard Account Groups

- `ria`: 위험자산 일임
- `isa`: ISA
- `brokerage`: 일반 위탁
- `irp`: IRP 퇴직연금
- `pension`: 연금저축

## Response Shape

For routine portfolio summaries, include:

- total evaluated amount
- account-type breakdown
- latest snapshot timestamp
- notable daily change when available
- whether the answer is DB-only or includes live KIS API calls

For stale or missing DB data, say so plainly and suggest refreshing balances from Claude Desktop MCP account instances.

## References

- See `references/workflows.md` for common operational workflows.
