"""Adapter-neutral orchestration for canonical total-asset snapshots."""

from __future__ import annotations

import os
from typing import Any, Awaitable, Callable

from kis_portfolio import db as kisdb
from kis_portfolio.account_registry import get_account, load_account_registry, scoped_account_env
from kis_portfolio.analytics.portfolio import get_latest_portfolio_summary
from kis_portfolio.services import kis_api
from kis_portfolio.services.account import refresh_configured_balance_snapshots
from kis_portfolio.services.overview import (
    build_cached_fx_fallback,
    build_fx_rates,
    build_total_asset_overview,
    overseas_holding_currencies,
)


def _safe_error_message(error: Exception, accounts: list | None = None) -> str:
    message = str(error)
    for account in accounts or []:
        for value in (account.cano, account.app_key, account.app_secret):
            if value:
                message = message.replace(value, "[redacted]")
    return message


async def collect_total_asset_overview(
    *,
    refresh: bool = True,
    save_snapshot: bool = True,
    overseas_account_label: str = "brokerage",
    top_n: int = 10,
    include_raw: bool = False,
    refresh_runner: Callable[[], Awaitable[dict]] | None = None,
    summary_runner: Callable[..., dict] = get_latest_portfolio_summary,
    overseas_balance_fetcher: Callable[..., Awaitable[dict]] = kis_api.inquery_overseas_balance,
    overseas_deposit_fetcher: Callable[..., Awaitable[dict]] = kis_api.inquery_overseas_deposit,
    exchange_rate_history_fetcher: Callable[..., Awaitable[dict]] = kis_api.inquery_exchange_rate_history,
    refresh_fx_cache: bool = True,
    db_module: Any = kisdb,
) -> dict:
    """Collect feeders, resolve FX, build quality metadata, and persist snapshots."""
    accounts = load_account_registry()
    refresh_status: dict[str, Any] = {"requested": refresh}
    if refresh:
        refresh_result = await (
            refresh_runner() if refresh_runner else refresh_configured_balance_snapshots()
        )
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
            {"account": row.get("account"), "error": row.get("error")}
            for row in refresh_result.get("accounts", [])
            if row.get("status") == "error"
        ]
        if refresh_errors:
            refresh_status["errors"] = refresh_errors

    con = db_module.get_connection()
    portfolio_summary = summary_runner(con, "", 30)
    overseas_account = get_account(overseas_account_label.strip().lower(), accounts)
    domestic_snapshot_rows = []
    domestic_symbols: list[str] = []
    missing_snapshot_accounts = []
    for account in accounts:
        rows = db_module.get_portfolio_snapshots(account.cano, limit=1)
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

    instrument_map = db_module.get_instrument_master_map(sorted(set(domestic_symbols)))
    override_map = db_module.get_classification_override_map(sorted(set(domestic_symbols)))
    errors = []
    overseas_balance: dict = {}
    overseas_deposit: dict = {}
    with scoped_account_env(overseas_account):
        try:
            overseas_balance = await overseas_balance_fetcher("ALL")
        except Exception as error:
            errors.append({
                "tool": "get-overseas-balance",
                "error": _safe_error_message(error, [overseas_account]),
            })
        try:
            overseas_deposit = await overseas_deposit_fetcher("01", "000")
        except Exception as error:
            errors.append({
                "tool": "get-overseas-deposit",
                "error": _safe_error_message(error, [overseas_account]),
            })

    required_currencies = overseas_holding_currencies(overseas_balance)
    deposit_fx_rates = build_fx_rates(overseas_deposit)
    fx_refresh_errors = []
    refreshed_currencies = []
    with scoped_account_env(overseas_account):
        for currency in required_currencies:
            if currency in deposit_fx_rates or not refresh_fx_cache:
                continue
            try:
                await exchange_rate_history_fetcher(currency, "", "", "D")
                refreshed_currencies.append(currency)
            except Exception as error:
                fx_refresh_errors.append({
                    "currency": currency,
                    "error_type": type(error).__name__,
                })

    fallback_fx_rates = build_cached_fx_fallback(
        required_currencies,
        db_module.get_latest_exchange_rate,
        stale_after_days=max(1, int(os.environ.get("KIS_FX_FALLBACK_STALE_AFTER_DAYS", "7"))),
    )
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
        fallback_fx_rates=fallback_fx_rates,
    )
    normalized_holdings = overview.pop("_normalized_holdings", [])
    overview["refresh"] = refresh_status
    if errors or refresh_status.get("error_count", 0):
        overview["status"] = "partial_error"
        overview.setdefault("data_quality", {})["status"] = "partial_error"
        overview["data_quality"]["is_complete"] = False
        overview["data_quality"].setdefault("flags", []).append({
            "code": "feeder_partial_error",
            "severity": "error",
            "message": "하나 이상의 계좌 또는 해외 feeder 조회가 실패했습니다.",
        })
        overview["data_quality"]["error_count"] = (
            overview["data_quality"].get("error_count", 0) + 1
        )
    elif missing_snapshot_accounts:
        overview["status"] = "degraded"
    else:
        overview["status"] = overview.get("data_quality", {}).get("status", "ok")
    if errors:
        overview["errors"] = errors
    if fx_refresh_errors:
        overview.setdefault("data_quality", {}).setdefault("flags", []).append({
            "code": "fx_rate_live_refresh_failed",
            "severity": "warning",
            "currencies": [row["currency"] for row in fx_refresh_errors],
            "message": "실시간 환율 cache refresh가 실패해 기존 DB fallback을 사용했습니다.",
        })
        overview["data_quality"]["warning_count"] = (
            overview["data_quality"].get("warning_count", 0) + 1
        )
    if missing_snapshot_accounts:
        overview["missing_snapshot_accounts"] = missing_snapshot_accounts
        overview.setdefault("data_quality", {}).setdefault("flags", []).append({
            "code": "domestic_snapshot_missing",
            "severity": "error",
            "accounts": [row.get("label") for row in missing_snapshot_accounts],
            "message": "일부 국내/연금 계좌의 스냅샷이 없어 총자산이 불완전할 수 있습니다.",
        })
        overview["data_quality"]["status"] = "degraded"
        overview["data_quality"]["is_complete"] = False

    if save_snapshot:
        overseas_snapshot_id = db_module.insert_overseas_asset_snapshot(
            overseas_account.cano,
            overseas_account.label,
            overview["totals"].get("overseas_stock_eval_amt_krw"),
            overview["totals"].get("overseas_cash_amt_krw"),
            overview["totals"].get("overseas_total_asset_amt_krw"),
            overview["overseas"].get("fx_rates"),
            overseas_balance,
            overseas_deposit,
        )
        overview_snapshot_id = db_module.insert_asset_overview_snapshot(
            overview["totals"],
            overview["allocation"],
            overview["classification_summary"],
            overview,
        )
        holding_count = db_module.insert_asset_holding_snapshots(
            overview_snapshot_id,
            normalized_holdings,
        )
        overview["saved_snapshot_id"] = overview_snapshot_id
        overview["overseas_snapshot_id"] = overseas_snapshot_id
        overview["holding_snapshot_count"] = holding_count
        overview["snapshot_status"] = "saved"
    else:
        overview["snapshot_status"] = "not_saved"
    used_db_fx = any(
        rate.get("source") == "db_cache"
        for rate in overview.get("overseas", {}).get("fx_rates", {}).values()
    )
    overview["used_tools"] = [
        tool for tool in [
            "refresh-all-account-snapshots" if refresh else None,
            "get-latest-portfolio-summary",
            "get-overseas-balance",
            "get-overseas-deposit",
            "get-exchange-rate-from-db" if used_db_fx else None,
            "get-exchange-rate-history" if refreshed_currencies else None,
        ]
        if tool
    ]
    return overview
