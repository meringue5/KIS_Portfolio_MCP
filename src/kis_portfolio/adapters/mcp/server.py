"""Single public MCP adapter for KIS Portfolio Service."""

from __future__ import annotations

import logging
import time
from typing import Annotated

from dotenv import load_dotenv
from mcp.server import MCPServer
from mcp.types import ToolAnnotations
from pydantic import Field

from kis_portfolio import db as kisdb
from kis_portfolio.account_registry import (
    get_account,
    load_account_registry,
    scoped_account_env,
)
from kis_portfolio.analytics.bollinger import get_bollinger_bands as analyze_bollinger_bands
from kis_portfolio.analytics.asset_overview import (
    get_total_asset_allocation_history as analyze_total_asset_allocation_history,
    get_total_asset_daily_change as analyze_total_asset_daily_change,
    get_total_asset_history as analyze_total_asset_history,
    get_total_asset_trend as analyze_total_asset_trend,
)
from kis_portfolio.analytics.portfolio import (
    get_latest_portfolio_summary as analyze_latest_portfolio_summary,
    get_portfolio_anomalies as analyze_portfolio_anomalies,
    get_portfolio_daily_change as analyze_portfolio_daily_change,
    get_portfolio_trend as analyze_portfolio_trend,
)
from kis_portfolio.auth import get_token_status as inspect_token_status
from kis_portfolio.clients.kis import KISApiError
from kis_portfolio.observability import (
    current_or_new_operation_id,
    log_event,
    operation_context,
)
from kis_portfolio.services import kis_api
from kis_portfolio.services.account import fetch_balance_snapshot, get_latest_balance_fallback
from kis_portfolio.services.overview import build_total_asset_overview
from kis_portfolio.services.order_history import get_domestic_order_history
from kis_portfolio.services.overseas_history import (
    get_overseas_order_history as get_overseas_order_history_service,
    get_overseas_settlement_balance as get_overseas_settlement_balance_service,
    get_overseas_transaction_history as get_overseas_transaction_history_service,
)


logger = logging.getLogger("kis-portfolio-mcp")
load_dotenv()

DEFAULT_ACCOUNT_LABEL = "brokerage"
mcp = MCPServer("KIS Portfolio Service", dependencies=["httpx", "xmltodict"])

READ_ONLY_TOOL = ToolAnnotations(read_only_hint=True)
SAFE_LOCAL_WRITE_TOOL = ToolAnnotations(destructive_hint=False, open_world_hint=False)
NON_DESTRUCTIVE_ACTION_TOOL = ToolAnnotations(destructive_hint=False, open_world_hint=False)

ConfiguredAccountLabel = Annotated[
    str,
    Field(description="Configured KIS account label such as brokerage, ria, isa, irp, or pension."),
]
OptionalAccountFilter = Annotated[
    str,
    Field(description="Optional configured account label. Leave empty to aggregate all configured accounts."),
]
DomesticSymbol = Annotated[
    str,
    Field(description="Domestic KRX stock or ETF code, usually a 6-digit symbol."),
]
InstrumentSymbol = Annotated[
    str,
    Field(description="Instrument symbol or ticker to query."),
]
DateYmd = Annotated[
    str,
    Field(description="Date in YYYYMMDD format accepted by the KIS API."),
]
ExchangeCode = Annotated[
    str,
    Field(description="Exchange code accepted by the KIS API for this tool."),
]
MarketCode = Annotated[
    str,
    Field(description="Market code accepted by the KIS API for overseas quotes."),
]
CurrencyCode = Annotated[
    str,
    Field(description="Currency code such as USD."),
]
OptionalDomesticSymbol = Annotated[
    str,
    Field(description="Optional domestic KRX symbol filter. Leave empty to include all symbols in the date range."),
]
OptionalOverseasSymbol = Annotated[
    str,
    Field(description="Optional overseas ticker/symbol filter. Leave empty to include all symbols in the date range."),
]
OrderHistorySource = Annotated[
    str,
    Field(
        description="Order-history backend strategy: auto prefers saved DB snapshots and falls back to KIS API, db reads only saved snapshots, kis_api forces a fresh KIS API fetch and saves it.",
    ),
]


def register_tools(server: MCPServer) -> None:
    for tool in mcp._tool_manager.list_tools():
        server.add_tool(
            tool.fn,
            name=tool.name,
            description=tool.description,
            annotations=tool.annotations,
        )


def build_mcp_server() -> MCPServer:
    server = MCPServer("KIS Portfolio Service", dependencies=["httpx", "xmltodict"])
    register_tools(server)
    return server


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


def _diagnostics(operation_id: str) -> dict:
    return {"operation_id": operation_id}


def _safe_error_message(error: Exception, accounts=None) -> str:
    message = str(error)
    for account in accounts or []:
        for value in (account.cano, account.app_key, account.app_secret):
            if value:
                message = message.replace(value, "[redacted]")
    return message


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
    description="Use this when you need the list of configured KIS accounts before choosing an account-specific tool. 등록된 계좌 라벨과 마스킹된 계좌번호만 반환하며 원본 계좌번호와 secret은 노출하지 않습니다.",
    annotations=READ_ONLY_TOOL,
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
    description="Use this when you need to check cached KIS token health across all configured accounts without exposing token values. 토큰 원문은 반환하지 않습니다.",
    annotations=READ_ONLY_TOOL,
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
    description="Use this when you need the latest balance for one configured account and want to save a fresh snapshot. 단일 계좌 조회용이며, 전체 자산현황이나 전 계좌 새로고침에는 refresh-all-account-snapshots를 우선 사용하세요.",
    annotations=SAFE_LOCAL_WRITE_TOOL,
)
async def get_account_balance(
    account_label: ConfiguredAccountLabel,
    allow_stale_on_error: Annotated[
        bool,
        Field(description="Return the latest saved balance with status=stale when KIS is temporarily unavailable."),
    ] = False,
):
    operation_id = current_or_new_operation_id("mcp")
    started = time.perf_counter()
    with operation_context(operation_id):
        log_event(
            logger,
            "mcp_tool_start",
            operation_id=operation_id,
            tool="get-account-balance",
            account_label=_account_label(account_label),
        )
        try:
            result = await _get_account_balance_impl(
                account_label,
                operation_id,
                allow_stale_on_error=allow_stale_on_error,
            )
        except Exception as error:
            log_event(
                logger,
                "mcp_tool_failed",
                level=logging.WARNING,
                operation_id=operation_id,
                tool="get-account-balance",
                account_label=_account_label(account_label),
                elapsed_ms=round((time.perf_counter() - started) * 1000, 1),
                error_type=type(error).__name__,
            )
            raise
        log_event(
            logger,
            "mcp_tool_complete",
            operation_id=operation_id,
            tool="get-account-balance",
            account_label=_account_label(account_label),
            elapsed_ms=round((time.perf_counter() - started) * 1000, 1),
            status=result.get("status"),
            snapshot_status=result.get("snapshot_status"),
        )
        return result


async def _get_account_balance_impl(
    account_label: ConfiguredAccountLabel,
    operation_id: str,
    *,
    allow_stale_on_error: bool = False,
):
    account = get_account(account_label)
    try:
        with scoped_account_env(account):
            result = await fetch_balance_snapshot(save_snapshot=True, return_metadata=True)
    except KISApiError as exc:
        if not allow_stale_on_error:
            raise
        fallback = get_latest_balance_fallback(account.cano)
        if fallback is None:
            raise
        payload = _wrap_raw(
            fallback.pop("raw"),
            account=account,
            source=fallback.pop("source"),
            snapshot_status="not_saved",
        )
        payload.update(fallback)
        payload["upstream"] = {
            "status": "unavailable",
            "error_type": type(exc).__name__,
        }
        payload["diagnostics"] = _diagnostics(operation_id)
        return payload
    saved_snapshot_id = result.get("saved_snapshot_id")
    payload = _wrap_raw(
        result["raw"],
        account=account,
        source="kis_api",
        saved_snapshot_id=saved_snapshot_id,
        snapshot_status="saved" if saved_snapshot_id else "not_saved",
    )
    payload["diagnostics"] = _diagnostics(operation_id)
    return payload


@mcp.tool(
    name="refresh-all-account-snapshots",
    description="Use this when you need the latest portfolio state across all configured accounts. 전 계좌를 순차 조회하고 MotherDuck에 스냅샷을 저장하므로 전체 자산현황/내 포트폴리오 요청에 우선 사용하세요.",
    annotations=SAFE_LOCAL_WRITE_TOOL,
)
async def refresh_all_account_snapshots():
    operation_id = current_or_new_operation_id("mcp")
    started = time.perf_counter()
    with operation_context(operation_id):
        log_event(
            logger,
            "mcp_tool_start",
            operation_id=operation_id,
            tool="refresh-all-account-snapshots",
        )
        result = await _refresh_all_account_snapshots_impl(operation_id)
        log_event(
            logger,
            "mcp_tool_complete",
            operation_id=operation_id,
            tool="refresh-all-account-snapshots",
            elapsed_ms=round((time.perf_counter() - started) * 1000, 1),
            success_count=result.get("success_count"),
            error_count=result.get("error_count"),
        )
        return result


async def _refresh_all_account_snapshots_impl(operation_id: str):
    results = []
    accounts = load_account_registry()
    for account in accounts:
        account_started = time.perf_counter()
        log_event(
            logger,
            "account_refresh_start",
            operation_id=operation_id,
            account_label=account.label,
            masked_cano=account.masked_cano,
        )
        try:
            with scoped_account_env(account):
                result = await fetch_balance_snapshot(save_snapshot=True, return_metadata=True)
            saved_snapshot_id = result.get("saved_snapshot_id")
            row = _wrap_raw(
                result["raw"],
                account=account,
                source="kis_api",
                saved_snapshot_id=saved_snapshot_id,
                snapshot_status="saved" if saved_snapshot_id else "not_saved",
            )
            results.append(row)
            log_event(
                logger,
                "account_refresh_complete",
                operation_id=operation_id,
                account_label=account.label,
                masked_cano=account.masked_cano,
                elapsed_ms=round((time.perf_counter() - account_started) * 1000, 1),
                snapshot_status=row.get("snapshot_status"),
            )
        except Exception as e:
            safe_error = _safe_error_message(e, [account])
            log_event(
                logger,
                "account_refresh_failed",
                level=logging.WARNING,
                operation_id=operation_id,
                account_label=account.label,
                masked_cano=account.masked_cano,
                elapsed_ms=round((time.perf_counter() - account_started) * 1000, 1),
                error_type=type(e).__name__,
                error=safe_error,
            )
            failed_row = {
                "source": "kis_api",
                "status": "error",
                "account": account.public_dict(),
                "error": safe_error,
            }
            if isinstance(e, KISApiError):
                fallback = get_latest_balance_fallback(account.cano)
                if fallback is not None:
                    fallback.pop("raw", None)
                    failed_row["fallback"] = fallback
            results.append(failed_row)
    return {
        "source": "kis_api",
        "count": len(results),
        "success_count": sum(1 for row in results if row["status"] == "ok"),
        "error_count": sum(1 for row in results if row["status"] == "error"),
        "accounts": results,
        "diagnostics": _diagnostics(operation_id),
    }


@mcp.tool(
    name="get-total-asset-overview",
    description="Use this when you need the latest combined domestic and overseas asset overview, allocation, and FX-adjusted totals. raw KIS 응답보다 요약과 비중 데이터를 우선 제공하며, 단일 계좌 잔고만 필요하면 get-account-balance를 사용하세요.",
    annotations=SAFE_LOCAL_WRITE_TOOL,
)
async def get_total_asset_overview(
    refresh: Annotated[
        bool,
        Field(description="When true, refresh all configured account snapshots before calculating totals."),
    ] = True,
    save_snapshot: Annotated[
        bool,
        Field(description="When true, save canonical overview snapshots and normalized holding snapshots to MotherDuck."),
    ] = True,
    overseas_account_label: ConfiguredAccountLabel = DEFAULT_ACCOUNT_LABEL,
    top_n: Annotated[
        int,
        Field(description="How many largest holdings to keep in top-holdings style summaries.", ge=1, le=50),
    ] = 10,
    include_raw: Annotated[
        bool,
        Field(description="When true, include raw feeder payloads in the overview response for debugging."),
    ] = False,
):
    operation_id = current_or_new_operation_id("mcp")
    started = time.perf_counter()
    with operation_context(operation_id):
        log_event(
            logger,
            "mcp_tool_start",
            operation_id=operation_id,
            tool="get-total-asset-overview",
            refresh=refresh,
            save_snapshot=save_snapshot,
            overseas_account_label=_account_label(overseas_account_label),
            include_raw=include_raw,
        )
        try:
            result = await _get_total_asset_overview_impl(
                refresh=refresh,
                save_snapshot=save_snapshot,
                overseas_account_label=overseas_account_label,
                top_n=top_n,
                include_raw=include_raw,
                operation_id=operation_id,
            )
        except Exception as error:
            log_event(
                logger,
                "mcp_tool_failed",
                level=logging.WARNING,
                operation_id=operation_id,
                tool="get-total-asset-overview",
                elapsed_ms=round((time.perf_counter() - started) * 1000, 1),
                error_type=type(error).__name__,
            )
            raise
        result["diagnostics"] = _diagnostics(operation_id)
        log_event(
            logger,
            "mcp_tool_complete",
            operation_id=operation_id,
            tool="get-total-asset-overview",
            elapsed_ms=round((time.perf_counter() - started) * 1000, 1),
            status=result.get("status"),
            refresh_error_count=result.get("refresh", {}).get("error_count"),
            snapshot_status=result.get("snapshot_status"),
        )
        return result


async def _get_total_asset_overview_impl(
    *,
    refresh: bool,
    save_snapshot: bool,
    overseas_account_label: str,
    top_n: int,
    include_raw: bool,
    operation_id: str,
):
    accounts = load_account_registry()
    refresh_status = {"requested": refresh}
    if refresh:
        refresh_result = await refresh_all_account_snapshots()
        refresh_status.update({
            "count": refresh_result.get("count", 0),
            "success_count": refresh_result.get("success_count", 0),
            "error_count": refresh_result.get("error_count", 0),
            "snapshot_status_counts": {
                "saved": sum(
                    1 for row in refresh_result.get("accounts", [])
                    if row.get("snapshot_status") == "saved"
                ),
                "not_saved": sum(
                    1 for row in refresh_result.get("accounts", [])
                    if row.get("snapshot_status") == "not_saved"
                ),
            },
        })
        refresh_errors = [
            {
                "account": row.get("account"),
                "error": row.get("error"),
            }
            for row in refresh_result.get("accounts", [])
            if row.get("status") == "error"
        ]
        if refresh_errors:
            refresh_status["errors"] = refresh_errors

    con = kisdb.get_connection()
    portfolio_summary = analyze_latest_portfolio_summary(con, "", 30)
    overseas_account = get_account(_account_label(overseas_account_label), accounts)
    domestic_snapshot_rows = []
    domestic_symbols: list[str] = []
    missing_snapshot_accounts = []
    for account in accounts:
        rows = kisdb.get_portfolio_snapshots(account.cano, limit=1)
        if not rows:
            missing_snapshot_accounts.append(account.public_dict())
            continue
        row = rows[0]
        row["account"] = account.public_dict()
        row["account_label"] = account.label
        domestic_snapshot_rows.append(row)
        for holding in row.get("balance_data", {}).get("output1") or []:
            if isinstance(holding, dict) and holding.get("pdno"):
                domestic_symbols.append(str(holding["pdno"]).strip())
    instrument_map = kisdb.get_instrument_master_map(sorted(set(domestic_symbols)))
    override_map = kisdb.get_classification_override_map(sorted(set(domestic_symbols)))

    errors = []
    overseas_balance = {}
    overseas_deposit = {}
    with scoped_account_env(overseas_account):
        try:
            overseas_balance = await kis_api.inquery_overseas_balance("ALL")
        except Exception as e:
            safe_error = _safe_error_message(e, [overseas_account])
            log_event(
                logger,
                "overview_feeder_failed",
                level=logging.WARNING,
                operation_id=operation_id,
                tool="get-overseas-balance",
                account_label=overseas_account.label,
                masked_cano=overseas_account.masked_cano,
                error_type=type(e).__name__,
                error=safe_error,
            )
            errors.append({"tool": "get-overseas-balance", "error": safe_error})
        try:
            overseas_deposit = await kis_api.inquery_overseas_deposit("01", "000")
        except Exception as e:
            safe_error = _safe_error_message(e, [overseas_account])
            log_event(
                logger,
                "overview_feeder_failed",
                level=logging.WARNING,
                operation_id=operation_id,
                tool="get-overseas-deposit",
                account_label=overseas_account.label,
                masked_cano=overseas_account.masked_cano,
                error_type=type(e).__name__,
                error=safe_error,
            )
            errors.append({"tool": "get-overseas-deposit", "error": safe_error})

    overview = build_total_asset_overview(
        portfolio_summary=portfolio_summary,
        overseas_balance=overseas_balance,
        overseas_deposit=overseas_deposit,
        accounts=accounts,
        overseas_account=overseas_account,
        top_n=top_n,
        include_raw=include_raw,
        domestic_snapshot_rows=domestic_snapshot_rows,
        instrument_map=instrument_map,
        override_map=override_map,
    )
    normalized_holdings = overview.pop("_normalized_holdings", [])
    overview["refresh"] = refresh_status
    overview["status"] = "partial_error" if errors or refresh_status.get("error_count", 0) else "ok"
    if errors:
        overview["errors"] = errors
    if missing_snapshot_accounts:
        overview["missing_snapshot_accounts"] = missing_snapshot_accounts
    if save_snapshot:
        overseas_snapshot_id = kisdb.insert_overseas_asset_snapshot(
            overseas_account.cano,
            overseas_account.label,
            overview["totals"].get("overseas_stock_eval_amt_krw"),
            overview["totals"].get("overseas_cash_amt_krw"),
            overview["totals"].get("overseas_total_asset_amt_krw"),
            overview["overseas"].get("fx_rates"),
            overseas_balance,
            overseas_deposit,
        )
        overview_snapshot_id = kisdb.insert_asset_overview_snapshot(
            overview["totals"],
            overview["allocation"],
            overview["classification_summary"],
            overview,
        )
        holding_count = kisdb.insert_asset_holding_snapshots(overview_snapshot_id, normalized_holdings)
        overview["saved_snapshot_id"] = overview_snapshot_id
        overview["overseas_snapshot_id"] = overseas_snapshot_id
        overview["holding_snapshot_count"] = holding_count
        overview["snapshot_status"] = "saved"
    else:
        overview["snapshot_status"] = "not_saved"
    overview["used_tools"] = [
        "refresh-all-account-snapshots" if refresh else None,
        "get-latest-portfolio-summary",
        "get-overseas-balance",
        "get-overseas-deposit",
    ]
    overview["used_tools"] = [tool for tool in overview["used_tools"] if tool]
    return overview


@mcp.tool(
    name="get-stock-price",
    description="Use this when you need the latest domestic stock price for a KRX symbol. 조회 전용 도구이며 주문, 뉴스 검색, 또는 히스토리 수집에는 사용하지 않습니다.",
    annotations=READ_ONLY_TOOL,
)
async def get_stock_price(
    symbol: DomesticSymbol,
    account_label: ConfiguredAccountLabel = DEFAULT_ACCOUNT_LABEL,
):
    return await _call_for_account(account_label, kis_api.inquery_stock_price, symbol)


@mcp.tool(
    name="get-stock-ask",
    description="Use this when you need the current domestic bid/ask book for a KRX symbol. 단순 현재가는 get-stock-price를, 일별 이력은 get-stock-history를 사용하세요.",
    annotations=READ_ONLY_TOOL,
)
async def get_stock_ask(
    symbol: DomesticSymbol,
    account_label: ConfiguredAccountLabel = DEFAULT_ACCOUNT_LABEL,
):
    return await _call_for_account(account_label, kis_api.inquery_stock_ask, symbol)


@mcp.tool(
    name="get-stock-info",
    description="Use this when you need daily domestic stock base price data for a date range. 실시간 호가나 현재가가 아니라 일별 기본 가격 정보 조회용입니다.",
    annotations=READ_ONLY_TOOL,
)
async def get_stock_info(
    symbol: DomesticSymbol,
    start_date: DateYmd,
    end_date: DateYmd,
    account_label: ConfiguredAccountLabel = DEFAULT_ACCOUNT_LABEL,
):
    return await _call_for_account(account_label, kis_api.inquery_stock_info, symbol, start_date, end_date)


@mcp.tool(
    name="get-stock-history",
    description="Use this when you need domestic stock price history and want it cached in MotherDuck for later analytics. 캐시된 데이터만 필요하면 get-price-from-db를 사용하세요.",
    annotations=SAFE_LOCAL_WRITE_TOOL,
)
async def get_stock_history(
    symbol: DomesticSymbol,
    start_date: DateYmd,
    end_date: DateYmd,
    account_label: ConfiguredAccountLabel = DEFAULT_ACCOUNT_LABEL,
):
    return await _call_for_account(account_label, kis_api.inquery_stock_history, symbol, start_date, end_date)


@mcp.tool(
    name="get-overseas-stock-price",
    description="Use this when you need the latest overseas stock quote for a ticker and market code. 해외 보유잔고 조회에는 get-overseas-balance를 사용하세요.",
    annotations=READ_ONLY_TOOL,
)
async def get_overseas_stock_price(
    symbol: InstrumentSymbol,
    market: MarketCode,
    account_label: ConfiguredAccountLabel = DEFAULT_ACCOUNT_LABEL,
):
    return await _call_for_account(account_label, kis_api.inquery_overseas_stock_price, symbol, market)


@mcp.tool(
    name="get-overseas-balance",
    description="Use this when you need overseas holdings for one configured account. 단순 해외 예수금과 적용환율만 필요하면 get-overseas-deposit를 사용하세요.",
    annotations=READ_ONLY_TOOL,
)
async def get_overseas_balance(
    exchange: ExchangeCode = "ALL",
    account_label: ConfiguredAccountLabel = DEFAULT_ACCOUNT_LABEL,
):
    return await _call_for_account(account_label, kis_api.inquery_overseas_balance, exchange)


@mcp.tool(
    name="get-overseas-deposit",
    description="Use this when you need overseas cash balances and applied FX rates for one configured account. 해외 보유 종목 목록까지 필요하면 get-overseas-balance를 사용하세요.",
    annotations=READ_ONLY_TOOL,
)
async def get_overseas_deposit(
    wcrc_frcr_dvsn_cd: Annotated[
        str,
        Field(description="Foreign currency evaluation mode code accepted by the KIS API."),
    ] = "02",
    natn_cd: Annotated[
        str,
        Field(description="Nation code accepted by the KIS API. Use 000 for all supported nations."),
    ] = "000",
    account_label: ConfiguredAccountLabel = DEFAULT_ACCOUNT_LABEL,
):
    return await _call_for_account(
        account_label,
        kis_api.inquery_overseas_deposit,
        wcrc_frcr_dvsn_cd,
        natn_cd,
    )


@mcp.tool(
    name="get-exchange-rate-history",
    description="Use this when you need exchange-rate history and want it cached in MotherDuck for later analytics. 캐시된 환율만 필요하면 get-exchange-rate-from-db를 사용하세요.",
    annotations=SAFE_LOCAL_WRITE_TOOL,
)
async def get_exchange_rate_history(
    currency: CurrencyCode = "USD",
    start_date: Annotated[
        str,
        Field(description="Optional start date in YYYYMMDD format. Leave empty to use the KIS default range."),
    ] = "",
    end_date: Annotated[
        str,
        Field(description="Optional end date in YYYYMMDD format. Leave empty to use the KIS default range."),
    ] = "",
    period: Annotated[
        str,
        Field(description="Aggregation period code accepted by the KIS API, usually D for daily."),
    ] = "D",
    account_label: ConfiguredAccountLabel = DEFAULT_ACCOUNT_LABEL,
):
    return await _call_for_account(
        account_label,
        kis_api.inquery_exchange_rate_history,
        currency,
        start_date,
        end_date,
        period,
    )


@mcp.tool(
    name="get-overseas-stock-history",
    description="Use this when you need overseas stock price history and want it cached in MotherDuck for later analytics. 최신 해외 시세 한 건만 필요하면 get-overseas-stock-price를 사용하세요.",
    annotations=SAFE_LOCAL_WRITE_TOOL,
)
async def get_overseas_stock_history(
    symbol: InstrumentSymbol,
    exchange: ExchangeCode = "NAS",
    end_date: Annotated[
        str,
        Field(description="Optional end date in YYYYMMDD format. Leave empty to use the KIS default."),
    ] = "",
    period: Annotated[
        str,
        Field(description="Overseas history period code accepted by the KIS API."),
    ] = "0",
    account_label: ConfiguredAccountLabel = DEFAULT_ACCOUNT_LABEL,
):
    return await _call_for_account(
        account_label,
        kis_api.inquery_overseas_stock_history,
        symbol,
        exchange,
        end_date,
        period,
    )


@mcp.tool(
    name="get-period-trade-profit",
    description="Use this when you need domestic trade profit for a date range and want the result stored in MotherDuck. 단순 보유잔고가 아니라 기간별 매매손익 조회용입니다.",
    annotations=SAFE_LOCAL_WRITE_TOOL,
)
async def get_period_trade_profit(
    start_date: DateYmd,
    end_date: DateYmd,
    account_label: ConfiguredAccountLabel = DEFAULT_ACCOUNT_LABEL,
):
    return await _call_for_account(account_label, kis_api.inquery_period_trade_profit, start_date, end_date)


@mcp.tool(
    name="get-overseas-period-profit",
    description="Use this when you need overseas trade profit for a date range and want the result stored in MotherDuck. 단순 해외 보유잔고 조회에는 get-overseas-balance를 사용하세요.",
    annotations=SAFE_LOCAL_WRITE_TOOL,
)
async def get_overseas_period_profit(
    start_date: DateYmd,
    end_date: DateYmd,
    exchange: Annotated[
        str,
        Field(description="Optional overseas exchange code filter accepted by the KIS API."),
    ] = "",
    currency: Annotated[
        str,
        Field(description="Optional currency filter accepted by the KIS API."),
    ] = "",
    account_label: ConfiguredAccountLabel = DEFAULT_ACCOUNT_LABEL,
):
    return await _call_for_account(
        account_label,
        kis_api.inquery_overseas_period_profit,
        start_date,
        end_date,
        exchange,
        currency,
    )


@mcp.tool(
    name="get-overseas-transaction-history",
    description="Use this when you need overseas daily transaction ledger rows for a date range with DB-first caching. 해외주식 일별거래내역 API를 조회해 raw snapshot과 canonical transaction row를 저장하며, 실제 주문 실행에는 사용할 수 없습니다.",
    annotations=SAFE_LOCAL_WRITE_TOOL,
)
async def get_overseas_transaction_history(
    start_date: DateYmd,
    end_date: DateYmd,
    symbol: OptionalOverseasSymbol = "",
    exchange: Annotated[
        str,
        Field(description="Overseas exchange code for the daily transaction API. The official example uses NAS for US/Nasdaq-style queries."),
    ] = "NAS",
    side: Annotated[
        str,
        Field(description="KIS side filter: 00 all, 01 sell, 02 buy."),
    ] = "00",
    source: OrderHistorySource = "auto",
    account_label: ConfiguredAccountLabel = DEFAULT_ACCOUNT_LABEL,
):
    account = get_account(_account_label(account_label))
    with scoped_account_env(account):
        result = await get_overseas_transaction_history_service(
            start_date,
            end_date,
            symbol=symbol,
            exchange=exchange,
            side=side,
            source=source,
            save_history=True,
        )
    result["account"] = account.public_dict()
    return result


@mcp.tool(
    name="get-overseas-order-history",
    description="Use this when you need overseas stock order/execution history for a date range with DB-first caching. 해외주식 주문체결내역 API를 조회해 raw snapshot과 canonical order row를 저장하며, 실제 주문 실행에는 사용할 수 없습니다.",
    annotations=SAFE_LOCAL_WRITE_TOOL,
)
async def get_overseas_order_history(
    start_date: DateYmd,
    end_date: DateYmd,
    symbol: OptionalOverseasSymbol = "",
    exchange: Annotated[
        str,
        Field(description="Overseas exchange filter. Use % for all supported exchanges, or NASD/NYSE/AMEX/SEHK/SHAA/SZAA/TKSE/HASE/VNSE."),
    ] = "%",
    side: Annotated[
        str,
        Field(description="KIS side filter: 00 all, 01 sell, 02 buy."),
    ] = "00",
    fill_status: Annotated[
        str,
        Field(description="KIS fill status filter: 00 all, 01 filled, 02 unfilled."),
    ] = "00",
    source: OrderHistorySource = "auto",
    account_label: ConfiguredAccountLabel = DEFAULT_ACCOUNT_LABEL,
):
    account = get_account(_account_label(account_label))
    with scoped_account_env(account):
        result = await get_overseas_order_history_service(
            start_date,
            end_date,
            symbol=symbol,
            exchange=exchange,
            side=side,
            fill_status=fill_status,
            source=source,
            save_history=True,
        )
    result["account"] = account.public_dict()
    return result


@mcp.tool(
    name="get-overseas-settlement-balance",
    description="Use this when you need overseas settlement-basis balance for one base date and want the raw snapshot saved. 해외주식 결제기준잔고 조회용이며 주문 실행에는 사용할 수 없습니다.",
    annotations=SAFE_LOCAL_WRITE_TOOL,
)
async def get_overseas_settlement_balance(
    base_date: DateYmd,
    wcrc_frcr_dvsn_cd: Annotated[
        str,
        Field(description="Currency evaluation mode: 01 KRW basis, 02 foreign-currency basis."),
    ] = "01",
    inqr_dvsn_cd: Annotated[
        str,
        Field(description="Balance query mode: 00 all, 01 regular, 02 mini-stock."),
    ] = "00",
    account_label: ConfiguredAccountLabel = DEFAULT_ACCOUNT_LABEL,
):
    account = get_account(_account_label(account_label))
    with scoped_account_env(account):
        result = await get_overseas_settlement_balance_service(
            base_date,
            wcrc_frcr_dvsn_cd=wcrc_frcr_dvsn_cd,
            inqr_dvsn_cd=inqr_dvsn_cd,
            save_snapshot=True,
        )
    result["account"] = account.public_dict()
    return result


@mcp.tool(
    name="get-order-list",
    description="Use this when you need domestic order history for a date range and want a DB-first canonical order store with optional KIS API refresh. 기본값은 저장된 snapshot 유무를 확인한 뒤 canonical DB를 우선 읽고, 없으면 KIS API를 조회해 raw snapshot과 canonical order row를 함께 저장합니다. 실제 주문 실행에는 사용할 수 없습니다.",
    annotations=SAFE_LOCAL_WRITE_TOOL,
)
async def get_order_list(
    start_date: DateYmd,
    end_date: DateYmd,
    symbol: OptionalDomesticSymbol = "",
    source: OrderHistorySource = "auto",
    account_label: ConfiguredAccountLabel = DEFAULT_ACCOUNT_LABEL,
):
    account = get_account(_account_label(account_label))
    with scoped_account_env(account):
        result = await get_domestic_order_history(
            start_date,
            end_date,
            symbol=symbol,
            source=source,
            save_history=True,
        )
    result["account"] = account.public_dict()
    return result


@mcp.tool(
    name="get-order-detail",
    description="Use this when you need the details for one domestic order number and date. 실제 주문 실행이나 수정에는 사용하지 않습니다.",
    annotations=READ_ONLY_TOOL,
)
async def get_order_detail(
    order_no: Annotated[str, Field(description="Domestic order number returned by the KIS API.")],
    order_date: DateYmd,
    account_label: ConfiguredAccountLabel = DEFAULT_ACCOUNT_LABEL,
):
    return await _call_for_account(account_label, kis_api.inquery_order_detail, order_no, order_date)


@mcp.tool(
    name="submit-stock-order",
    description="Use this only when you need confirmation that domestic live trading is disabled on this server. 실제 주문 API는 호출하지 않으며 항상 disabled stub를 반환합니다.",
    annotations=NON_DESTRUCTIVE_ACTION_TOOL,
)
async def submit_stock_order(
    symbol: DomesticSymbol,
    quantity: Annotated[int, Field(description="Requested share quantity for the hypothetical order.", ge=1)],
    price: Annotated[int, Field(description="Requested limit price for the hypothetical order.", ge=0)],
    order_type: Annotated[str, Field(description="Hypothetical domestic order type label.")],
):
    return _disabled_order_response("domestic_stock")


@mcp.tool(
    name="submit-overseas-stock-order",
    description="Use this only when you need confirmation that overseas live trading is disabled on this server. 실제 주문 API는 호출하지 않으며 항상 disabled stub를 반환합니다.",
    annotations=NON_DESTRUCTIVE_ACTION_TOOL,
)
async def submit_overseas_stock_order(
    symbol: InstrumentSymbol,
    quantity: Annotated[int, Field(description="Requested share quantity for the hypothetical order.", ge=1)],
    price: Annotated[float, Field(description="Requested limit price for the hypothetical order.", ge=0)],
    order_type: Annotated[str, Field(description="Hypothetical overseas order type label.")],
    market: MarketCode,
):
    return _disabled_order_response("overseas_stock")


@mcp.tool(
    name="get-portfolio-history",
    description="Use this when you need saved domestic or pension feeder snapshot history from MotherDuck and do not want a live KIS API call. 글로벌 총자산 이력에는 get-total-asset-history를 사용하세요.",
    annotations=READ_ONLY_TOOL,
)
async def get_portfolio_history(
    account_label: ConfiguredAccountLabel = DEFAULT_ACCOUNT_LABEL,
    start_date: Annotated[
        str,
        Field(description="Optional start date in YYYYMMDD format for snapshot filtering."),
    ] = "",
    end_date: Annotated[
        str,
        Field(description="Optional end date in YYYYMMDD format for snapshot filtering."),
    ] = "",
    limit: Annotated[
        int,
        Field(description="Maximum number of snapshots to return.", ge=1, le=500),
    ] = 50,
):
    account = get_account(_account_label(account_label))
    rows = kisdb.get_portfolio_snapshots(account.cano, start_date or None, end_date or None, limit)
    return {
        "source": "motherduck",
        "account": account.public_dict(),
        "count": len(rows),
        "snapshots": rows,
    }


@mcp.tool(
    name="get-price-from-db",
    description="Use this when cached price history from MotherDuck is enough and you do not want a live KIS API call. 새 시세를 수집하면서 캐시를 채우려면 get-stock-history 또는 get-overseas-stock-history를 사용하세요.",
    annotations=READ_ONLY_TOOL,
)
async def get_price_from_db(
    symbol: InstrumentSymbol,
    start_date: DateYmd,
    end_date: DateYmd,
    exchange: ExchangeCode = "KRX",
):
    return await kis_api.get_price_from_db(symbol, start_date, end_date, exchange)


@mcp.tool(
    name="get-exchange-rate-from-db",
    description="Use this when cached exchange-rate history from MotherDuck is enough and you do not want a live KIS API call.",
    annotations=READ_ONLY_TOOL,
)
async def get_exchange_rate_from_db(
    currency: CurrencyCode = "USD",
    start_date: Annotated[
        str,
        Field(description="Optional start date in YYYYMMDD format for cached FX history."),
    ] = "",
    end_date: Annotated[
        str,
        Field(description="Optional end date in YYYYMMDD format for cached FX history."),
    ] = "",
    period: Annotated[
        str,
        Field(description="Aggregation period code used when the FX history was cached, usually D for daily."),
    ] = "D",
):
    return await kis_api.get_exchange_rate_from_db(currency, start_date, end_date, period)


@mcp.tool(
    name="get-bollinger-bands",
    description="Use this when you need Bollinger Bands computed from cached price history. 시세 수집 자체는 하지 않으므로 필요한 가격 이력이 없다면 먼저 get-stock-history 또는 get-overseas-stock-history를 사용하세요.",
    annotations=READ_ONLY_TOOL,
)
async def get_bollinger_bands(
    symbol: InstrumentSymbol,
    exchange: ExchangeCode = "KRX",
    window: Annotated[int, Field(description="Rolling window size for the Bollinger Band calculation.", ge=2, le=365)] = 20,
    num_std: Annotated[float, Field(description="Number of standard deviations used for the upper and lower bands.", gt=0, le=10)] = 2.0,
    limit: Annotated[int, Field(description="Maximum number of rows to return from the cached price history.", ge=1, le=500)] = 60,
):
    con = kisdb.get_connection()
    return analyze_bollinger_bands(con, symbol, exchange, window, num_std, limit)


@mcp.tool(
    name="get-latest-portfolio-summary",
    description="Use this when you need the latest combined domestic or pension feeder summary from saved snapshots without a live KIS API call. 글로벌 총자산 요약에는 get-total-asset-overview를 사용하세요.",
    annotations=READ_ONLY_TOOL,
)
async def get_latest_portfolio_summary(
    account_label: OptionalAccountFilter = "",
    lookback_days: Annotated[
        int,
        Field(description="How many recent days of snapshots to scan when finding the latest summary.", ge=1, le=3650),
    ] = 30,
):
    con = kisdb.get_connection()
    return analyze_latest_portfolio_summary(con, _account_id_from_label(account_label), lookback_days)


@mcp.tool(
    name="get-portfolio-daily-change",
    description="Use this when you need daily value changes from saved domestic or pension feeder snapshots. 글로벌 총자산 변화에는 get-total-asset-daily-change를 사용하세요.",
    annotations=READ_ONLY_TOOL,
)
async def get_portfolio_daily_change(
    account_label: OptionalAccountFilter = "",
    days: Annotated[int, Field(description="How many recent days of portfolio changes to calculate.", ge=1, le=3650)] = 14,
):
    con = kisdb.get_connection()
    return analyze_portfolio_daily_change(con, _account_id_from_label(account_label), days)


@mcp.tool(
    name="get-portfolio-anomalies",
    description="Use this when you need anomaly detection on saved daily domestic or pension feeder snapshot values. 실시간 API 조회가 아니라 저장된 스냅샷 분석용입니다.",
    annotations=READ_ONLY_TOOL,
)
async def get_portfolio_anomalies(
    account_label: OptionalAccountFilter = "",
    z_threshold: Annotated[
        float,
        Field(description="Z-score threshold used to classify a daily move as an anomaly.", gt=0, le=10),
    ] = 2.0,
    lookback_days: Annotated[
        int,
        Field(description="How many recent days of snapshots to scan for anomalies.", ge=2, le=3650),
    ] = 90,
    limit: Annotated[int, Field(description="Maximum number of anomalies to return.", ge=1, le=500)] = 20,
):
    con = kisdb.get_connection()
    return analyze_portfolio_anomalies(
        con,
        _account_id_from_label(account_label),
        z_threshold,
        lookback_days,
        limit,
    )


@mcp.tool(
    name="get-portfolio-trend",
    description="Use this when you need moving-average trend analysis on saved domestic or pension feeder snapshots. 실시간 API 조회가 아니라 스냅샷 기반 분석입니다.",
    annotations=READ_ONLY_TOOL,
)
async def get_portfolio_trend(
    account_label: OptionalAccountFilter = "",
    short_window: Annotated[int, Field(description="Short moving-average window length.", ge=1, le=365)] = 7,
    long_window: Annotated[int, Field(description="Long moving-average window length.", ge=2, le=3650)] = 30,
    lookback_days: Annotated[int, Field(description="How many recent days of snapshots to analyze.", ge=2, le=3650)] = 90,
):
    con = kisdb.get_connection()
    return analyze_portfolio_trend(
        con,
        _account_id_from_label(account_label),
        short_window,
        long_window,
        lookback_days,
    )


@mcp.tool(
    name="get-total-asset-history",
    description="Use this when you need canonical total-asset snapshot history from saved overview snapshots without a live KIS API call.",
    annotations=READ_ONLY_TOOL,
)
async def get_total_asset_history(
    days: Annotated[int, Field(description="How many recent days of total-asset history to include.", ge=1, le=3650)] = 30,
    limit: Annotated[int, Field(description="Maximum number of history rows to return.", ge=1, le=500)] = 60,
):
    con = kisdb.get_connection()
    return analyze_total_asset_history(con, days, limit)


@mcp.tool(
    name="get-total-asset-daily-change",
    description="Use this when you need daily value changes from canonical total-asset snapshots without a live KIS API call.",
    annotations=READ_ONLY_TOOL,
)
async def get_total_asset_daily_change(
    days: Annotated[int, Field(description="How many recent days of total-asset changes to calculate.", ge=1, le=3650)] = 14,
):
    con = kisdb.get_connection()
    return analyze_total_asset_daily_change(con, days)


@mcp.tool(
    name="get-total-asset-trend",
    description="Use this when you need moving-average trend analysis on canonical total-asset snapshots without a live KIS API call.",
    annotations=READ_ONLY_TOOL,
)
async def get_total_asset_trend(
    short_window: Annotated[int, Field(description="Short moving-average window length.", ge=1, le=365)] = 7,
    long_window: Annotated[int, Field(description="Long moving-average window length.", ge=2, le=3650)] = 30,
    lookback_days: Annotated[int, Field(description="How many recent days of snapshots to analyze.", ge=2, le=3650)] = 90,
):
    con = kisdb.get_connection()
    return analyze_total_asset_trend(con, short_window, long_window, lookback_days)


@mcp.tool(
    name="get-total-asset-allocation-history",
    description="Use this when you need domestic, overseas, overseas-indirect, and cash allocation history from canonical total-asset snapshots without a live KIS API call.",
    annotations=READ_ONLY_TOOL,
)
async def get_total_asset_allocation_history(
    days: Annotated[int, Field(description="How many recent days of allocation history to return.", ge=1, le=3650)] = 30,
):
    con = kisdb.get_connection()
    return analyze_total_asset_allocation_history(con, days)


def main() -> None:
    logger.info("Starting KIS Portfolio MCP server...")
    build_mcp_server().run()
