# Expected Architecture Contracts

## Runtime Identity

- Project package: `kis_portfolio`
- Distribution name: `kis-portfolio`
- Console scripts: `kis-portfolio-auth`, `kis-portfolio-batch`, `kis-portfolio-mcp`, `kis-portfolio-remote`
- Public MCP name: `KIS Portfolio Service`

## Important Paths

- MCP adapter: `src/kis_portfolio/adapters/mcp/server.py`
- Batch adapter: `src/kis_portfolio/adapters/batch/cli.py`
- Remote adapter: `src/kis_portfolio/remote.py`
- Core services: `src/kis_portfolio/services/`
- KIS client helpers: `src/kis_portfolio/clients/`
- DB package: `src/kis_portfolio/db/`
- Analytics package: `src/kis_portfolio/analytics/`

## Must Not Regress

- Do not recreate `src/kis_mcp_server/`.
- Do not add `kis-mcp-*` console scripts.
- Do not add `kis-ria`, `kis-isa`, `kis-irp`, `kis-pension`, or `kis-brokerage` to default setup.
- Do not expose `inquery-*` or `order-*` MCP tool aliases.
- Do not make submit-order tools call live KIS order APIs.
