#!/usr/bin/env python3
"""Check high-level architecture contracts for KIS Portfolio Service."""

from __future__ import annotations

import ast
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

    script_entries = pyproject["project"].get("scripts", {})
    scripts = set(script_entries)
    expected_scripts = {
        "kis-portfolio-auth",
        "kis-portfolio-batch",
        "kis-portfolio-mcp",
        "kis-portfolio-migrate",
        "kis-portfolio-remote",
    }
    if scripts != expected_scripts:
        fail(f"console scripts must be {sorted(expected_scripts)}, got {sorted(scripts)}", failures)
    if script_entries.get("kis-portfolio-mcp") != "kis_portfolio.legacy_entrypoint:main":
        fail("kis-portfolio-mcp must be the retired V1 diagnostic entrypoint", failures)

    packages = pyproject["tool"]["hatch"]["build"]["targets"]["wheel"]["packages"]
    if packages != ["src/kis_portfolio"]:
        fail("wheel package must be ['src/kis_portfolio']", failures)

    if (ROOT / "src/kis_mcp_server").exists():
        fail("legacy src/kis_mcp_server directory must not exist", failures)

    obsolete_shims = [
        "src/kis_portfolio/app.py",
        "src/kis_portfolio/orchestrator.py",
        "src/kis_portfolio/kis_token_crypto.py",
        "src/kis_portfolio/db/utils.py",
        "src/kis_portfolio/adapters/auth/crypto.py",
    ]
    for shim in obsolete_shims:
        if (ROOT / shim).exists():
            fail(f"obsolete compatibility shim must not exist: {shim}", failures)

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

    if "kis_portfolio.legacy_entrypoint" not in file_text("server.py"):
        fail("root server.py must import the retired V1 diagnostic", failures)

    remote_text = file_text("src/kis_portfolio/remote.py")
    if "kis_portfolio.adapters.mcp.v2" not in remote_text:
        fail("Remote MCP must build the canonical V2 adapter", failures)
    for obsolete_import in [
        "kis_portfolio.adapters.mcp.server",
        "kis_portfolio.app",
        "kis_portfolio.orchestrator",
    ]:
        if obsolete_import in remote_text:
            fail(f"Remote MCP must not import obsolete runtime path: {obsolete_import}", failures)

    setup_text = file_text("scripts/setup.sh")
    if "retire_local_claude_config.py" not in setup_text:
        fail("scripts/setup.sh must remove the exact retired local MCP registration", failures)
    if "KIS_RESOURCE_SERVER_URL" not in setup_text or "OAuth Remote MCP" not in setup_text:
        fail("scripts/setup.sh must guide the canonical OAuth Remote MCP connection", failures)
    if "orchestrator_srv" in setup_text:
        fail("scripts/setup.sh must not create a local MCP server", failures)
    for legacy_server in ["kis-ria", "kis-isa", "kis-irp", "kis-pension", "kis-brokerage", "kis-api-search"]:
        if f'"{legacy_server}"' in setup_text:
            fail(f"scripts/setup.sh must not create {legacy_server}", failures)

    if (ROOT / "docs/examples/claude_desktop_config.example.json").exists():
        fail("retired local Claude Desktop config example must not exist", failures)

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
        from kis_portfolio.adapters.mcp.v2 import COMMAND_TOOL_CONTRACTS, TOOL_CONTRACTS
    except Exception as exc:
        fail(f"could not import V2 MCP adapter: {exc}", failures)
    else:
        tool_names = {item.name for item in TOOL_CONTRACTS + COMMAND_TOOL_CONTRACTS}
        if len(tool_names) != 18:
            fail(f"V2 public MCP catalog must contain 18 tools, got {len(tool_names)}", failures)
        if {"submit-stock-order", "submit-overseas-stock-order"} & tool_names:
            fail("V2 public MCP catalog must not expose order stubs", failures)

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
