"""Batch CLI entrypoint for scheduled KIS collection jobs."""

from __future__ import annotations

import argparse
import asyncio
import json

from dotenv import load_dotenv

from kis_portfolio.services.market_calendar import sync_krx_market_calendar_years
from kis_portfolio.services.alerts import notify_batch_failure
from kis_portfolio.services.asset_pipeline import collect_total_asset_overview
from kis_portfolio.services.order_history import collect_domestic_order_history, resolve_yyyymmdd
from kis_portfolio.services.overseas_history import collect_overseas_transaction_history
from kis_portfolio.services.token_warmup import warm_token_cache


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    domestic_orders = subparsers.add_parser(
        "collect-domestic-order-history",
        help="Fetch one-day domestic daily order/execution history for all configured accounts and store it.",
    )
    domestic_orders.add_argument(
        "--date",
        default="today",
        help="Batch date in YYYYMMDD or 'today' resolved in Asia/Seoul. Default: today",
    )

    overseas_transactions = subparsers.add_parser(
        "collect-overseas-transaction-history",
        help="Fetch one-day overseas daily transaction history for one configured account and store it.",
    )
    overseas_transactions.add_argument(
        "--date",
        default="today",
        help="Batch date in YYYYMMDD or 'today' resolved in Asia/Seoul. Default: today",
    )
    overseas_transactions.add_argument(
        "--account-label",
        default="brokerage",
        help="Configured account label to collect. Default: brokerage",
    )
    overseas_transactions.add_argument(
        "--exchange",
        default="NAS",
        help="Overseas exchange code for the KIS daily transaction API. Default: NAS",
    )

    token_warmup = subparsers.add_parser(
        "warm-token-cache",
        help="Inspect or refresh KIS API access-token cache before a target wall-clock time.",
    )
    token_warmup.add_argument(
        "--account-label",
        default="all",
        help="Configured account label to warm, or 'all'. Default: all",
    )
    token_warmup.add_argument(
        "--valid-through",
        default="16:30",
        help="HH:MM Asia/Seoul time the token should remain safely valid through. Default: 16:30",
    )
    token_warmup.add_argument(
        "--dry-run",
        action="store_true",
        help="Only report which accounts would refresh; do not call the KIS token endpoint.",
    )
    token_warmup.add_argument(
        "--warm-service-health",
        action="store_true",
        help="Also GET auth/remote /health endpoints to wake Cloud Run services.",
    )

    market_calendar = subparsers.add_parser(
        "sync-market-calendar",
        help="Generate and upsert KRX market calendar rows for one or more years.",
    )
    market_calendar.add_argument(
        "years",
        nargs="+",
        type=int,
        help="Calendar years to generate, for example: 2026 2027",
    )

    asset_snapshot = subparsers.add_parser(
        "collect-asset-overview-snapshot",
        help="Refresh all balances, resolve FX, and store one canonical total-asset snapshot.",
    )
    asset_snapshot.add_argument(
        "--overseas-account-label",
        default="brokerage",
        help="Configured account used for overseas holdings. Default: brokerage",
    )
    asset_snapshot.add_argument(
        "--top-n",
        type=int,
        default=10,
        help="Number of overseas holdings kept in summary chart data. Default: 10",
    )
    return parser


async def _run_collect_domestic_order_history(args: argparse.Namespace) -> int:
    result = await collect_domestic_order_history(resolve_yyyymmdd(args.date))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["error_count"] == 0 else 1


async def _run_collect_overseas_transaction_history(args: argparse.Namespace) -> int:
    result = await collect_overseas_transaction_history(
        resolve_yyyymmdd(args.date),
        account_label=args.account_label,
        exchange=args.exchange,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "ok" else 1


async def _run_warm_token_cache(args: argparse.Namespace) -> int:
    result = await warm_token_cache(
        account_label=args.account_label,
        valid_through=args.valid_through,
        dry_run=args.dry_run,
        warm_service_health_checks=args.warm_service_health,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "ok" else 1


def _run_sync_market_calendar(args: argparse.Namespace) -> int:
    result = sync_krx_market_calendar_years(args.years)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


async def _run_collect_asset_overview_snapshot(args: argparse.Namespace) -> int:
    try:
        result = await collect_total_asset_overview(
            refresh=True,
            save_snapshot=True,
            overseas_account_label=args.overseas_account_label,
            top_n=args.top_n,
            include_raw=False,
        )
    except Exception as error:
        alert = await notify_batch_failure(
            "collect-asset-overview-snapshot",
            "error",
            f"{type(error).__name__}: canonical asset snapshot failed",
        )
        print(json.dumps({
            "status": "error",
            "error_type": type(error).__name__,
            "alert": alert,
        }, ensure_ascii=False, indent=2))
        return 1

    if result.get("status") != "ok" or result.get("snapshot_status") != "saved":
        result["alert"] = await notify_batch_failure(
            "collect-asset-overview-snapshot",
            result.get("status", "error"),
            "Canonical asset snapshot completed with degraded or incomplete data.",
        )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("status") == "ok" and result.get("snapshot_status") == "saved" else 1


def main() -> None:
    load_dotenv()
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "collect-domestic-order-history":
        raise SystemExit(asyncio.run(_run_collect_domestic_order_history(args)))
    if args.command == "collect-overseas-transaction-history":
        raise SystemExit(asyncio.run(_run_collect_overseas_transaction_history(args)))
    if args.command == "warm-token-cache":
        raise SystemExit(asyncio.run(_run_warm_token_cache(args)))
    if args.command == "sync-market-calendar":
        raise SystemExit(_run_sync_market_calendar(args))
    if args.command == "collect-asset-overview-snapshot":
        raise SystemExit(asyncio.run(_run_collect_asset_overview_snapshot(args)))

    parser.print_help()
    raise SystemExit(2)
