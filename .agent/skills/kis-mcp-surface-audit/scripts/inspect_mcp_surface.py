#!/usr/bin/env python3
"""Inspect public MCP tool surface for KIS Portfolio Service."""

from __future__ import annotations

import asyncio
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
    "get-configured-accounts",
    "get-all-token-statuses",
    "get-account-balance",
    "refresh-all-account-snapshots",
    "get-total-asset-overview",
    "get-stock-price",
    "get-stock-ask",
    "get-stock-info",
    "get-stock-history",
    "get-overseas-stock-price",
    "get-overseas-balance",
    "get-overseas-deposit",
    "get-exchange-rate-history",
    "get-overseas-stock-history",
    "get-period-trade-profit",
    "get-overseas-period-profit",
    "get-overseas-transaction-history",
    "get-overseas-order-history",
    "get-overseas-settlement-balance",
    "get-order-list",
    "get-order-detail",
    "submit-stock-order",
    "submit-overseas-stock-order",
    "get-portfolio-history",
    "get-price-from-db",
    "get-exchange-rate-from-db",
    "get-bollinger-bands",
    "get-latest-portfolio-summary",
    "get-portfolio-daily-change",
    "get-portfolio-anomalies",
    "get-portfolio-trend",
    "get-total-asset-history",
    "get-total-asset-daily-change",
    "get-total-asset-trend",
    "get-total-asset-allocation-history",
}


async def check_order_stubs(server, failures: list[str]) -> None:
    domestic = await server.submit_stock_order("005930", 1, 0, "buy")
    overseas = await server.submit_overseas_stock_order("AAPL", 1, 100.0, "buy", "NASD")
    for name, result in {
        "submit-stock-order": domestic,
        "submit-overseas-stock-order": overseas,
    }.items():
        if result.get("status") != "disabled":
            failures.append(f"{name} must return status=disabled")
        if result.get("source") != "order_stub":
            failures.append(f"{name} must return source=order_stub")


def main() -> int:
    failures: list[str] = []

    from kis_portfolio.adapters.mcp import server

    tool_names = set(server.mcp._tool_manager._tools)
    missing = EXPECTED_TOOLS - tool_names
    extra = tool_names - EXPECTED_TOOLS
    if missing:
        failures.append(f"missing tools: {sorted(missing)}")
    if extra:
        failures.append(f"unexpected tools: {sorted(extra)}")
    legacy = sorted(name for name in tool_names if name.startswith("inquery-") or name.startswith("order-"))
    if legacy:
        failures.append(f"legacy tool aliases exposed: {legacy}")

    asyncio.run(check_order_stubs(server, failures))

    if failures:
        print("MCP surface check failed:")
        for item in failures:
            print(f"- {item}")
        return 1

    print(f"MCP surface check passed. tools={len(tool_names)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
