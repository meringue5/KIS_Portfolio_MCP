#!/usr/bin/env python3
"""Inspect public MCP tool surface for KIS Portfolio Service."""

from __future__ import annotations

import logging
import sys
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


EXPECTED_TOOLS = {
    "get-portfolio-overview",
    "get-position-analysis",
    "get-performance-history",
    "get-market-snapshot",
    "get-market-history",
    "get-trade-ledger",
    "get-trade-thread",
    "get-dividend-summary",
    "get-fundamental-outlook",
    "get-exposure-analysis",
    "get-signal-status",
    "get-data-catalog",
    "get-data-quality",
    "get-pipeline-run",
    "get-journal-review-queue",
    "run-managed-pipeline",
    "upsert-trade-journal",
    "revise-trade-thread",
}


def main() -> int:
    failures: list[str] = []

    from kis_portfolio.adapters.mcp.v2 import COMMAND_TOOL_CONTRACTS, TOOL_CONTRACTS

    contracts = TOOL_CONTRACTS + COMMAND_TOOL_CONTRACTS
    tool_names = {item.name for item in contracts}
    missing = EXPECTED_TOOLS - tool_names
    extra = tool_names - EXPECTED_TOOLS
    if missing:
        failures.append(f"missing tools: {sorted(missing)}")
    if extra:
        failures.append(f"unexpected tools: {sorted(extra)}")
    legacy = sorted(
        name for name in tool_names
        if name.startswith("inquery-") or name.startswith("order-") or name.startswith("submit-")
    )
    if legacy:
        failures.append(f"legacy tool aliases exposed: {legacy}")

    if failures:
        print("MCP surface check failed:")
        for item in failures:
            print(f"- {item}")
        return 1

    print(f"MCP surface check passed. tools={len(tool_names)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
