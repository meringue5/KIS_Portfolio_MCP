"""Batch CLI entrypoint for scheduled KIS collection jobs."""

from __future__ import annotations

import argparse
import asyncio
import json

from dotenv import load_dotenv

from kis_portfolio.services.market_calendar import sync_krx_market_calendar_years
from kis_portfolio.services.order_history import collect_domestic_order_history, resolve_yyyymmdd


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
    return parser


async def _run_collect_domestic_order_history(args: argparse.Namespace) -> int:
    result = await collect_domestic_order_history(resolve_yyyymmdd(args.date))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["error_count"] == 0 else 1


def _run_sync_market_calendar(args: argparse.Namespace) -> int:
    result = sync_krx_market_calendar_years(args.years)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def main() -> None:
    load_dotenv()
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "collect-domestic-order-history":
        raise SystemExit(asyncio.run(_run_collect_domestic_order_history(args)))
    if args.command == "sync-market-calendar":
        raise SystemExit(_run_sync_market_calendar(args))

    parser.print_help()
    raise SystemExit(2)
