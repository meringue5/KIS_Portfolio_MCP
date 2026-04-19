"""Single public MCP adapter for KIS Portfolio Service."""

from __future__ import annotations

import logging

from dotenv import load_dotenv
from mcp.server.fastmcp.server import FastMCP

from kis_portfolio import db as kisdb
from kis_portfolio.account_registry import (
    get_account,
    load_account_registry,
    scoped_account_env,
)
from kis_portfolio.analytics.bollinger import get_bollinger_bands as analyze_bollinger_bands
from kis_portfolio.analytics.portfolio import (
    get_latest_portfolio_summary as analyze_latest_portfolio_summary,
    get_portfolio_anomalies as analyze_portfolio_anomalies,
    get_portfolio_daily_change as analyze_portfolio_daily_change,
    get_portfolio_trend as analyze_portfolio_trend,
)
from kis_portfolio.auth import get_token_status as inspect_token_status
from kis_portfolio.services import kis_api
from kis_portfolio.services.account import fetch_balance_snapshot


logger = logging.getLogger("kis-portfolio-mcp")
load_dotenv()

DEFAULT_ACCOUNT_LABEL = "brokerage"
mcp = FastMCP("KIS Portfolio Service", dependencies=["httpx", "xmltodict"])


def _account_label(label: str = "") -> str:
    return (label or DEFAULT_ACCOUNT_LABEL).strip().lower()


def _account_id_from_label(account_label: str = "") -> str:
    if not account_label:
        return ""
    return get_account(account_label).cano


def _wrap_raw(raw: dict, account=None, source: str = "kis_api", **metadata) -> dict:
    payload = {
        "source": source,
        "status": "ok",
        "raw": raw,
    }
    if account is not None:
        payload["account"] = account.public_dict()
    payload.update({k: v for k, v in metadata.items() if v is not None})
    return payload


async def _call_for_account(account_label: str, func, *args, source: str = "kis_api", **kwargs) -> dict:
    account = get_account(_account_label(account_label))
    with scoped_account_env(account):
        raw = await func(*args, **kwargs)
    return _wrap_raw(raw, account=account, source=source)


def _disabled_order_response(order_kind: str) -> dict:
    return {
        "source": "order_stub",
        "status": "disabled",
        "order_kind": order_kind,
        "message": "주문 기능은 현재 stub입니다. 실제 KIS 주문 API는 호출하지 않습니다.",
    }


@mcp.tool(
    name="get-configured-accounts",
    description="등록된 KIS 계좌 목록을 반환합니다. 계좌번호와 secret은 마스킹/비노출합니다.",
)
async def get_configured_accounts():
    accounts = load_account_registry()
    return {
        "source": "account_registry",
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
        statuses.append({"account": account.public_dict(), "token_status": status})
    return {"source": "token_cache", "count": len(statuses), "accounts": statuses}


@mcp.tool(
    name="get-account-balance",
    description="지정한 계좌 라벨의 현재 잔고를 조회하고 MotherDuck에 스냅샷을 저장합니다.",
)
async def get_account_balance(account_label: str):
    account = get_account(account_label)
    with scoped_account_env(account):
        result = await fetch_balance_snapshot(save_snapshot=True, return_metadata=True)
    return _wrap_raw(
        result["raw"],
        account=account,
        source="kis_api",
        saved_snapshot_id=result.get("saved_snapshot_id"),
    )


@mcp.tool(
    name="refresh-all-account-snapshots",
    description="모든 등록 계좌 잔고를 순차 조회하고 MotherDuck에 스냅샷을 저장합니다.",
)
async def refresh_all_account_snapshots():
    results = []
    for account in load_account_registry():
        try:
            with scoped_account_env(account):
                result = await fetch_balance_snapshot(save_snapshot=True, return_metadata=True)
            results.append(
                _wrap_raw(
                    result["raw"],
                    account=account,
                    source="kis_api",
                    saved_snapshot_id=result.get("saved_snapshot_id"),
                )
            )
        except Exception as e:
            logger.warning("Account refresh failed for %s: %s", account.label, e)
            results.append({
                "source": "kis_api",
                "status": "error",
                "account": account.public_dict(),
                "error": str(e),
            })
    return {
        "source": "kis_api",
        "count": len(results),
        "success_count": sum(1 for row in results if row["status"] == "ok"),
        "error_count": sum(1 for row in results if row["status"] == "error"),
        "accounts": results,
    }


@mcp.tool(name="get-stock-price", description="국내주식 현재가를 조회합니다.")
async def get_stock_price(symbol: str, account_label: str = DEFAULT_ACCOUNT_LABEL):
    return await _call_for_account(account_label, kis_api.inquery_stock_price, symbol)


@mcp.tool(name="get-stock-ask", description="국내주식 호가를 조회합니다.")
async def get_stock_ask(symbol: str, account_label: str = DEFAULT_ACCOUNT_LABEL):
    return await _call_for_account(account_label, kis_api.inquery_stock_ask, symbol)


@mcp.tool(name="get-stock-info", description="국내주식 일별 기본 가격 정보를 조회합니다.")
async def get_stock_info(
    symbol: str,
    start_date: str,
    end_date: str,
    account_label: str = DEFAULT_ACCOUNT_LABEL,
):
    return await _call_for_account(account_label, kis_api.inquery_stock_info, symbol, start_date, end_date)


@mcp.tool(name="get-stock-history", description="국내주식 가격 이력을 조회하고 DB에 캐시합니다.")
async def get_stock_history(
    symbol: str,
    start_date: str,
    end_date: str,
    account_label: str = DEFAULT_ACCOUNT_LABEL,
):
    return await _call_for_account(account_label, kis_api.inquery_stock_history, symbol, start_date, end_date)


@mcp.tool(name="get-overseas-stock-price", description="해외주식 현재가를 조회합니다.")
async def get_overseas_stock_price(
    symbol: str,
    market: str,
    account_label: str = DEFAULT_ACCOUNT_LABEL,
):
    return await _call_for_account(account_label, kis_api.inquery_overseas_stock_price, symbol, market)


@mcp.tool(name="get-overseas-balance", description="해외주식 잔고를 조회합니다.")
async def get_overseas_balance(
    exchange: str = "ALL",
    account_label: str = DEFAULT_ACCOUNT_LABEL,
):
    return await _call_for_account(account_label, kis_api.inquery_overseas_balance, exchange)


@mcp.tool(name="get-overseas-deposit", description="해외주식 예수금과 적용환율을 조회합니다.")
async def get_overseas_deposit(
    wcrc_frcr_dvsn_cd: str = "02",
    natn_cd: str = "000",
    account_label: str = DEFAULT_ACCOUNT_LABEL,
):
    return await _call_for_account(
        account_label,
        kis_api.inquery_overseas_deposit,
        wcrc_frcr_dvsn_cd,
        natn_cd,
    )


@mcp.tool(name="get-exchange-rate-history", description="환율 이력을 조회하고 DB에 캐시합니다.")
async def get_exchange_rate_history(
    currency: str = "USD",
    start_date: str = "",
    end_date: str = "",
    period: str = "D",
    account_label: str = DEFAULT_ACCOUNT_LABEL,
):
    return await _call_for_account(
        account_label,
        kis_api.inquery_exchange_rate_history,
        currency,
        start_date,
        end_date,
        period,
    )


@mcp.tool(name="get-overseas-stock-history", description="해외주식 가격 이력을 조회하고 DB에 캐시합니다.")
async def get_overseas_stock_history(
    symbol: str,
    exchange: str = "NAS",
    end_date: str = "",
    period: str = "0",
    account_label: str = DEFAULT_ACCOUNT_LABEL,
):
    return await _call_for_account(
        account_label,
        kis_api.inquery_overseas_stock_history,
        symbol,
        exchange,
        end_date,
        period,
    )


@mcp.tool(name="get-period-trade-profit", description="국내주식 기간별 매매손익을 조회하고 DB에 저장합니다.")
async def get_period_trade_profit(
    start_date: str,
    end_date: str,
    account_label: str = DEFAULT_ACCOUNT_LABEL,
):
    return await _call_for_account(account_label, kis_api.inquery_period_trade_profit, start_date, end_date)


@mcp.tool(name="get-overseas-period-profit", description="해외주식 기간별 손익을 조회하고 DB에 저장합니다.")
async def get_overseas_period_profit(
    start_date: str,
    end_date: str,
    exchange: str = "",
    currency: str = "",
    account_label: str = DEFAULT_ACCOUNT_LABEL,
):
    return await _call_for_account(
        account_label,
        kis_api.inquery_overseas_period_profit,
        start_date,
        end_date,
        exchange,
        currency,
    )


@mcp.tool(name="get-order-list", description="국내주식 주문 내역을 조회합니다. 주문 실행은 하지 않습니다.")
async def get_order_list(
    start_date: str,
    end_date: str,
    account_label: str = DEFAULT_ACCOUNT_LABEL,
):
    return await _call_for_account(account_label, kis_api.inquery_order_list, start_date, end_date)


@mcp.tool(name="get-order-detail", description="국내주식 주문 상세 내역을 조회합니다. 주문 실행은 하지 않습니다.")
async def get_order_detail(
    order_no: str,
    order_date: str,
    account_label: str = DEFAULT_ACCOUNT_LABEL,
):
    return await _call_for_account(account_label, kis_api.inquery_order_detail, order_no, order_date)


@mcp.tool(name="submit-stock-order", description="국내주식 주문 stub입니다. 실제 주문 API를 호출하지 않습니다.")
async def submit_stock_order(symbol: str, quantity: int, price: int, order_type: str):
    return _disabled_order_response("domestic_stock")


@mcp.tool(name="submit-overseas-stock-order", description="해외주식 주문 stub입니다. 실제 주문 API를 호출하지 않습니다.")
async def submit_overseas_stock_order(
    symbol: str,
    quantity: int,
    price: float,
    order_type: str,
    market: str,
):
    return _disabled_order_response("overseas_stock")


@mcp.tool(name="get-portfolio-history", description="MotherDuck DB에서 계좌 잔고 스냅샷 이력을 조회합니다.")
async def get_portfolio_history(
    account_label: str = DEFAULT_ACCOUNT_LABEL,
    start_date: str = "",
    end_date: str = "",
    limit: int = 50,
):
    account = get_account(_account_label(account_label))
    rows = kisdb.get_portfolio_snapshots(account.cano, start_date or None, end_date or None, limit)
    return {
        "source": "motherduck",
        "account": account.public_dict(),
        "count": len(rows),
        "snapshots": rows,
    }


@mcp.tool(name="get-price-from-db", description="MotherDuck DB에서 캐시된 주가 이력을 조회합니다.")
async def get_price_from_db(
    symbol: str,
    start_date: str,
    end_date: str,
    exchange: str = "KRX",
):
    return await kis_api.get_price_from_db(symbol, start_date, end_date, exchange)


@mcp.tool(name="get-exchange-rate-from-db", description="MotherDuck DB에서 캐시된 환율 이력을 조회합니다.")
async def get_exchange_rate_from_db(
    currency: str = "USD",
    start_date: str = "",
    end_date: str = "",
    period: str = "D",
):
    return await kis_api.get_exchange_rate_from_db(currency, start_date, end_date, period)


@mcp.tool(name="get-bollinger-bands", description="캐시된 주가 이력으로 볼린저 밴드를 계산합니다.")
async def get_bollinger_bands(
    symbol: str,
    exchange: str = "KRX",
    window: int = 20,
    num_std: float = 2.0,
    limit: int = 60,
):
    con = kisdb.get_connection()
    return analyze_bollinger_bands(con, symbol, exchange, window, num_std, limit)


@mcp.tool(name="get-latest-portfolio-summary", description="최신 스냅샷 기준 포트폴리오 합산 요약을 반환합니다.")
async def get_latest_portfolio_summary(
    account_label: str = "",
    lookback_days: int = 30,
):
    con = kisdb.get_connection()
    return analyze_latest_portfolio_summary(con, _account_id_from_label(account_label), lookback_days)


@mcp.tool(name="get-portfolio-daily-change", description="일별 대표 스냅샷 기준 평가금액 변화를 계산합니다.")
async def get_portfolio_daily_change(
    account_label: str = "",
    days: int = 14,
):
    con = kisdb.get_connection()
    return analyze_portfolio_daily_change(con, _account_id_from_label(account_label), days)


@mcp.tool(name="get-portfolio-anomalies", description="일별 평가금액 변동 이상치를 탐지합니다.")
async def get_portfolio_anomalies(
    account_label: str = "",
    z_threshold: float = 2.0,
    lookback_days: int = 90,
    limit: int = 20,
):
    con = kisdb.get_connection()
    return analyze_portfolio_anomalies(
        con,
        _account_id_from_label(account_label),
        z_threshold,
        lookback_days,
        limit,
    )


@mcp.tool(name="get-portfolio-trend", description="일별 평가금액 이동평균과 추세를 계산합니다.")
async def get_portfolio_trend(
    account_label: str = "",
    short_window: int = 7,
    long_window: int = 30,
    lookback_days: int = 90,
):
    con = kisdb.get_connection()
    return analyze_portfolio_trend(
        con,
        _account_id_from_label(account_label),
        short_window,
        long_window,
        lookback_days,
    )


def main() -> None:
    logger.info("Starting KIS Portfolio MCP server...")
    mcp.run()
