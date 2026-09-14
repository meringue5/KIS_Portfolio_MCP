# Expected Architecture Contracts

## Runtime Identity

- Project package: `kis_portfolio`
- Distribution name: `kis-portfolio`
- Runtime console scripts: `kis-portfolio-auth`, `kis-portfolio-batch`, `kis-portfolio-mcp`, `kis-portfolio-remote`
- Administrative console script: `kis-portfolio-migrate` (explicit only; never runtime startup)
- Public MCP name: `KIS Portfolio Service`

## Important Paths

- Production Remote MCP entrypoint: `src/kis_portfolio/remote.py`
- Public V2 MCP adapter: `src/kis_portfolio/adapters/mcp/v2.py`
- Batch adapter: `src/kis_portfolio/adapters/batch/cli.py`
- Remote adapter: `src/kis_portfolio/remote.py`
- Core services: `src/kis_portfolio/services/`
- KIS client helpers: `src/kis_portfolio/clients/`
- DB package: `src/kis_portfolio/db/`
- Analytics package: `src/kis_portfolio/analytics/`

## Must Not Regress

- Do not recreate `src/kis_mcp_server/`.
- Do not recreate the retired compatibility re-export shims `app.py`, `orchestrator.py`, `kis_token_crypto.py`,
  `db/utils.py`, or `adapters/auth/crypto.py`.
- Do not add `kis-mcp-*` console scripts.
- Do not add `kis-ria`, `kis-isa`, `kis-irp`, `kis-pension`, or `kis-brokerage` to default setup.
- Do not expose `inquery-*` or `order-*` MCP tool aliases.
- Do not make submit-order tools call live KIS order APIs.
