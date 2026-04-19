"""Single MCP orchestrator for all configured KIS accounts."""

from __future__ import annotations

import logging

from dotenv import load_dotenv
from mcp.server.fastmcp.server import FastMCP

from kis_mcp_server import db as kisdb
from kis_mcp_server.account_registry import (
    AccountRegistryError,
    get_account,
    load_account_registry,
    scoped_account_env,
)
from kis_mcp_server.analytics.portfolio import (
    get_latest_portfolio_summary as analyze_latest_portfolio_summary,
    get_portfolio_daily_change as analyze_portfolio_daily_change,
)
from kis_mcp_server.auth import get_token_status as inspect_token_status
from kis_mcp_server.kis_balance import fetch_balance_snapshot


logger = logging.getLogger("kis-orchestrator")
load_dotenv()

mcp = FastMCP("KIS Portfolio Orchestrator", dependencies=["httpx", "xmltodict"])


@mcp.tool(
    name="get-configured-accounts",
    description="오케스트레이터에 등록된 KIS 계좌 목록을 반환합니다. 계좌번호와 secret은 마스킹/비노출합니다.",
)
async def get_configured_accounts():
    accounts = load_account_registry()
    return {
        "count": len(accounts),
        "accounts": [account.public_dict() for account in accounts],
    }


@mcp.tool(
    name="get-all-token-statuses",
    description="모든 등록 계좌의 KIS 접근토큰 캐시 상태를 조회합니다. 토큰 값은 반환하지 않습니다.",
)
async def get_all_token_statuses():
    accounts = load_account_registry()
    statuses = []
    for account in accounts:
        with scoped_account_env(account):
            status = inspect_token_status()
        status.pop("token", None)
        statuses.append({
            "account": account.public_dict(),
            "token_status": status,
        })
    return {"count": len(statuses), "accounts": statuses}


@mcp.tool(
    name="get-account-balance",
    description="지정한 계좌 라벨의 현재 잔고를 조회하고 MotherDuck에 스냅샷을 저장합니다.",
)
async def get_account_balance(account_label: str):
    account = get_account(account_label)
    with scoped_account_env(account):
        data = await fetch_balance_snapshot(save_snapshot=True)
    return {
        "account": account.public_dict(),
        "status": "ok",
        "data": data,
    }


@mcp.tool(
    name="refresh-all-account-snapshots",
    description="모든 등록 계좌 잔고를 순차 조회하고 MotherDuck에 스냅샷을 저장합니다. 일부 실패는 계좌별 오류로 반환합니다.",
)
async def refresh_all_account_snapshots():
    accounts = load_account_registry()
    results = []
    for account in accounts:
        try:
            with scoped_account_env(account):
                data = await fetch_balance_snapshot(save_snapshot=True)
            results.append({
                "account": account.public_dict(),
                "status": "ok",
                "data": data,
            })
        except Exception as e:
            logger.warning("Account refresh failed for %s: %s", account.label, e)
            results.append({
                "account": account.public_dict(),
                "status": "error",
                "error": str(e),
            })

    return {
        "count": len(results),
        "success_count": sum(1 for row in results if row["status"] == "ok"),
        "error_count": sum(1 for row in results if row["status"] == "error"),
        "accounts": results,
    }


@mcp.tool(
    name="get-latest-portfolio-summary",
    description="MotherDuck DB의 최신 스냅샷으로 전체/단일 계좌 합산 요약을 반환합니다.",
)
async def get_latest_portfolio_summary(
    account_id: str = "",
    lookback_days: int = 30,
):
    con = kisdb.get_connection()
    return analyze_latest_portfolio_summary(con, account_id, lookback_days)


@mcp.tool(
    name="get-portfolio-daily-change",
    description="MotherDuck DB의 일별 대표 스냅샷으로 전체/단일 계좌 평가금액 변화를 계산합니다.",
)
async def get_portfolio_daily_change(
    account_id: str = "",
    days: int = 14,
):
    con = kisdb.get_connection()
    return analyze_portfolio_daily_change(con, account_id, days)


def main() -> None:
    logger.info("Starting KIS Portfolio Orchestrator MCP server...")
    mcp.run()


if __name__ == "__main__":
    main()
