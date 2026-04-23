#!/usr/bin/env python3
"""Check high-level architecture contracts for KIS Portfolio Service."""

from __future__ import annotations

import ast
import json
import logging
import re
import sys
import tomllib
from pathlib import Path


def repo_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "pyproject.toml").exists() and (parent / "src").exists():
            return parent
    raise RuntimeError("Could not locate repo root")


ROOT = repo_root()
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
logging.disable(logging.CRITICAL)


def fail(message: str, failures: list[str]) -> None:
    failures.append(message)


def file_text(path: str) -> str:
    return (ROOT / path).read_text()


def main() -> int:
    failures: list[str] = []
    pyproject = tomllib.loads(file_text("pyproject.toml"))

    if pyproject["project"]["name"] != "kis-portfolio":
        fail("pyproject project.name must be kis-portfolio", failures)

    scripts = set(pyproject["project"].get("scripts", {}))
    expected_scripts = {
        "kis-portfolio-auth",
        "kis-portfolio-batch",
        "kis-portfolio-mcp",
        "kis-portfolio-remote",
    }
    if scripts != expected_scripts:
        fail(f"console scripts must be {sorted(expected_scripts)}, got {sorted(scripts)}", failures)

    packages = pyproject["tool"]["hatch"]["build"]["targets"]["wheel"]["packages"]
    if packages != ["src/kis_portfolio"]:
        fail("wheel package must be ['src/kis_portfolio']", failures)

    if (ROOT / "src/kis_mcp_server").exists():
        fail("legacy src/kis_mcp_server directory must not exist", failures)

    for required in [
        "src/kis_portfolio/adapters/batch/cli.py",
        "src/kis_portfolio/adapters/mcp/server.py",
        "src/kis_portfolio/services",
        "src/kis_portfolio/clients",
        "src/kis_portfolio/db",
        "src/kis_portfolio/analytics",
    ]:
        if not (ROOT / required).exists():
            fail(f"missing required path: {required}", failures)

    if "kis_portfolio.adapters.mcp" not in file_text("server.py"):
        fail("root server.py must import kis_portfolio.adapters.mcp", failures)

    setup_text = file_text("scripts/setup.sh")
    if '"kis-portfolio": orchestrator_srv()' not in setup_text:
        fail("scripts/setup.sh must create kis-portfolio MCP server", failures)
    for legacy_server in ["kis-ria", "kis-isa", "kis-irp", "kis-pension", "kis-brokerage", "kis-api-search"]:
        if f'"{legacy_server}"' in setup_text:
            fail(f"scripts/setup.sh must not create {legacy_server}", failures)

    example = json.loads(file_text("docs/examples/claude_desktop_config.example.json"))
    servers = set(example.get("mcpServers", {}))
    if servers != {"kis-portfolio"}:
        fail(f"example Claude config must only contain kis-portfolio, got {sorted(servers)}", failures)

    runtime_files = [
        p for p in ROOT.rglob("*")
        if p.is_file()
        and ".git" not in p.parts
        and ".venv" not in p.parts
        and ".agent" not in p.parts
        and "__pycache__" not in p.parts
        and p.suffix in {".py", ".toml", ".sh", ".md", ".json"}
    ]
    legacy_pattern = re.compile(r"kis_mcp_server|kis-mcp-(server|remote|orchestrator)")
    for path in runtime_files:
        rel = path.relative_to(ROOT)
        text = path.read_text(errors="ignore")
        if legacy_pattern.search(text):
            fail(f"legacy runtime identity found in {rel}", failures)

    try:
        from kis_portfolio.adapters.mcp import mcp
    except Exception as exc:
        fail(f"could not import MCP adapter: {exc}", failures)
    else:
        if mcp.name != "KIS Portfolio Service":
            fail(f"MCP name mismatch: {mcp.name}", failures)
        tool_names = set(mcp._tool_manager._tools)
        if any(name.startswith("inquery-") or name.startswith("order-") for name in tool_names):
            fail("MCP must not expose legacy inquery-* or order-* tool aliases", failures)

    adapter_ast = ast.parse(file_text("src/kis_portfolio/adapters/mcp/server.py"))
    live_order_markers = {"get_hashkey", "ORDER_PATH", "OVERSEAS_ORDER_PATH"}
    adapter_names = {node.id for node in ast.walk(adapter_ast) if isinstance(node, ast.Name)}
    if live_order_markers & adapter_names:
        fail("MCP adapter must not contain live order API markers", failures)

    if failures:
        print("Architecture contract check failed:")
        for item in failures:
            print(f"- {item}")
        return 1

    print("Architecture contract check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
