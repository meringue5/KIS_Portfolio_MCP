"""Batch CLI entrypoint for scheduled KIS collection jobs."""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

from kis_portfolio.services.market_calendar import sync_krx_market_calendar_years
from kis_portfolio.services.order_history import collect_domestic_order_history, resolve_yyyymmdd
from kis_portfolio.services.overseas_history import collect_overseas_transaction_history
from kis_portfolio.services.price_history import run_held_price_backfill
from kis_portfolio.services.token_warmup import warm_token_cache
from kis_portfolio.services.v2_collection import ALLOWED_SLOTS, run_owned_portfolio_pipeline
from kis_portfolio.db.connection import get_connection


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

    managed = subparsers.add_parser(
        "collect-owned-portfolio-v2",
        help="Run the approved governed V2 owned-portfolio pipeline with fixed slot/date arguments.",
    )
    managed.add_argument("--date", default="today", help="YYYYMMDD or today in Asia/Seoul")
    managed.add_argument("--slot", required=True, choices=sorted(ALLOWED_SLOTS))
    managed.add_argument("--partition-key", default="all-accounts", choices=("all-accounts",))

    price_backfill = subparsers.add_parser(
        "backfill-held-price-history-v2",
        help="Plan or execute the governed held-instrument dual-basis price backfill.",
    )
    price_backfill.add_argument("--start-date", help="YYYYMMDD; default is three years before end date")
    price_backfill.add_argument("--end-date", default="today", help="YYYYMMDD or today")
    price_backfill.add_argument(
        "--execute", action="store_true",
        help="Perform KIS reads and writes. Without this flag the command is a read-only dry-run.",
    )
    price_backfill.add_argument("--max-pages-per-partition", type=int, default=10, choices=range(1, 11))
    price_backfill.add_argument("--max-physical-calls", type=int, default=400)
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


def _run_owned_portfolio_v2(args: argparse.Namespace) -> int:
    logical_date = (
        datetime.now(ZoneInfo("Asia/Seoul")).date()
        if args.date == "today" else datetime.strptime(args.date, "%Y%m%d").date()
    )
    result = run_owned_portfolio_pipeline(
        get_connection(), logical_date=logical_date, slot=args.slot, partition_key=args.partition_key,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] in {"succeeded", "skipped", "in_progress"} else 1


def _run_price_backfill(args: argparse.Namespace) -> int:
    end_date = (
        datetime.now(ZoneInfo("Asia/Seoul")).date()
        if args.end_date == "today" else datetime.strptime(args.end_date, "%Y%m%d").date()
    )
    start_date = (
        datetime.strptime(args.start_date, "%Y%m%d").date()
        if args.start_date else end_date - timedelta(days=365 * 3)
    )
    result = run_held_price_backfill(
        get_connection(),
        start_date=start_date,
        end_date=end_date,
        dry_run=not args.execute,
        max_pages_per_partition=args.max_pages_per_partition,
        max_physical_calls=args.max_physical_calls,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] in {"dry_run", "succeeded", "skipped"} else 1


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
    if args.command == "collect-owned-portfolio-v2":
        raise SystemExit(_run_owned_portfolio_v2(args))
    if args.command == "backfill-held-price-history-v2":
        raise SystemExit(_run_price_backfill(args))

    parser.print_help()
    raise SystemExit(2)
