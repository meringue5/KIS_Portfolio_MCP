---
name: kis-architecture-audit
description: Use when checking whether KIS Portfolio Service implementation, package boundaries, MCP exposure, CLI scripts, and docs still match SPEC.md, ARCHITECTURE.md, AGENTS.md, and the agreed service architecture.
---

# KIS Architecture Audit

Use this skill before and after structural refactors, package renames, MCP exposure changes, or documentation updates.

## Workflow

1. Read the relevant contract docs: `SPEC.md`, `ARCHITECTURE.md`, `AGENTS.md`, `docs/api-capability-map.md`.
2. Run:

   ```bash
   uv run python .agent/skills/kis-architecture-audit/scripts/check_architecture_contracts.py
   ```

3. Run the normal verification set:

   ```bash
   uv run pytest
   bash -n scripts/setup.sh
   python3 -m json.tool docs/examples/claude_desktop_config.example.json >/dev/null
   git diff --check
   ```

4. If the script fails, fix either the implementation or the docs. Do not silently widen the contract.

## Contract Focus

- Package/import identity is `kis_portfolio`; runtime `kis_mcp_server` imports must not return.
- Public CLI scripts are `kis-portfolio-auth`, `kis-portfolio-batch`, `kis-portfolio-mcp`, and `kis-portfolio-remote`.
- Public MCP is the single `kis-portfolio` service.
- Root `server.py` is a compatibility shim to `kis_portfolio.adapters.mcp`.
- `scripts/setup.sh` creates only `kis-portfolio` in Claude config.
- MCP adapter registers tools and delegates core logic to `services/`.
- Orders remain disabled stubs.

## References

- Read `references/expected-contracts.md` for the current architecture contract.
