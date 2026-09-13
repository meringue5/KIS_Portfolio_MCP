"""Fail-closed guidance for retired local V1 MCP entrypoints."""

from __future__ import annotations

import json
import os
import sys
from typing import NoReturn


EXIT_CODE = 2


def retirement_notice() -> dict[str, object]:
    resource_url = os.environ.get("KIS_RESOURCE_SERVER_URL", "").strip()
    return {
        "status": "retired",
        "reason_code": "v1_public_surface_retired",
        "message": (
            "The local KIS Portfolio V1 MCP server has been retired. "
            "Connect the OAuth Remote MCP named 'KIS Portfolio' instead."
        ),
        "remote_mcp_url": resource_url or None,
        "required_transport": "streamable-http",
        "required_auth": "oauth",
        "migration_guide": "docs/remote-mcp-v2-migration.md",
    }


def main() -> NoReturn:
    print(json.dumps(retirement_notice(), ensure_ascii=False), file=sys.stderr)
    raise SystemExit(EXIT_CODE)


if __name__ == "__main__":
    main()
