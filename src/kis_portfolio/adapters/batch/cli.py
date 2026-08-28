"""Batch CLI entrypoint for scheduled KIS collection jobs."""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import duckdb
from dotenv import load_dotenv

from kis_portfolio.account_registry import load_account_registry
from kis_portfolio.config import (
    get_db_mode,
    get_motherduck_database,
    get_motherduck_token,
)
from kis_portfolio.db.connection import get_connection
from kis_portfolio.platform.migrations import MigrationRunner
from kis_portfolio.services.market_calendar import sync_krx_market_calendar_years
from kis_portfolio.services.order_history import collect_domestic_order_history, resolve_yyyymmdd
from kis_portfolio.services.overseas_history import collect_overseas_transaction_history
from kis_portfolio.services.price_history import run_held_price_backfill
from kis_portfolio.services.position_reconstruction_runtime import (
    build_reconstruction_execution_plan,
)
from kis_portfolio.services.trade_cash_backfill import (
    DEFAULT_PARTITION_DAYS,
    DOMESTIC_ORDER_HISTORY,
    OVERSEAS_ORDER_HISTORY,
    OVERSEAS_TRANSACTION_HISTORY,
    BackfillBudgetPolicy,
    account_scopes_from_registry,
    apply_call_budget,
    plan_trade_cash_backfill,
)
from kis_portfolio.services.trade_cash_backfill_pipeline import build_trade_cash_partition_handler
from kis_portfolio.services.trade_cash_backfill_runtime import execute_trade_cash_backfill
from kis_portfolio.services.trade_cash_backfill_source import KisTradeCashBackfillSource
from kis_portfolio.services.token_warmup import warm_token_cache
from kis_portfolio.services.v2_collection import ALLOWED_SLOTS, run_owned_portfolio_pipeline
from kis_portfolio.services.wi021_s06 import WI021S06Config, run_wi021_s06
from kis_portfolio.services.wi022_s06 import WI022S06Config, WI022S06PhaseError, run_wi022_s06


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

    trade_cash_plan = subparsers.add_parser(
        "plan-trade-cash-backfill-v2",
        help="Print the deterministic trade/cash backfill partition plan without calls or writes.",
    )
    trade_cash_plan.add_argument("--start-date", help="YYYYMMDD; default is three calendar years before end date")
    trade_cash_plan.add_argument("--end-date", default="today", help="YYYYMMDD or today")
    trade_cash_plan.add_argument(
        "--as-of-date",
        default="today",
        help="YYYYMMDD or today; fixes the domestic old/recent source boundary",
    )
    trade_cash_plan.add_argument(
        "--partition-days",
        type=int,
        default=DEFAULT_PARTITION_DAYS,
        choices=range(1, 91),
    )
    trade_cash_plan.add_argument(
        "--overseas-account-label",
        action="append",
        dest="overseas_account_labels",
        help="Repeat for each account with overseas history. Default: brokerage",
    )
    trade_cash_plan.add_argument(
        "--exchange",
        action="append",
        dest="overseas_exchanges",
        help="Repeat for each KIS overseas exchange code. Default: NAS",
    )
    trade_cash_plan.add_argument("--max-physical-calls", type=int, default=400)
    trade_cash_plan.add_argument(
        "--domestic-order-pages", type=int, default=3, choices=range(1, 11),
    )
    trade_cash_plan.add_argument(
        "--overseas-order-pages", type=int, default=3, choices=range(1, 11),
    )
    trade_cash_plan.add_argument(
        "--overseas-transaction-pages", type=int, default=2, choices=range(1, 11),
    )

    trade_cash_execute = subparsers.add_parser(
        "backfill-trade-cash-history-v2",
        help="Preflight or execute the fixed-scope governed trade/cash backfill.",
    )
    trade_cash_execute.add_argument("--start-date", required=True, help="Exact YYYYMMDD")
    trade_cash_execute.add_argument("--end-date", required=True, help="Exact YYYYMMDD")
    trade_cash_execute.add_argument("--as-of-date", required=True, help="Exact YYYYMMDD")
    trade_cash_execute.add_argument("--partition-days", type=int, default=DEFAULT_PARTITION_DAYS, choices=range(1, 91))
    trade_cash_execute.add_argument("--overseas-account-label", action="append", dest="overseas_account_labels")
    trade_cash_execute.add_argument("--exchange", action="append", dest="overseas_exchanges")
    trade_cash_execute.add_argument("--max-physical-calls", type=int, default=400)
    trade_cash_execute.add_argument("--domestic-order-pages", type=int, default=3, choices=range(1, 11))
    trade_cash_execute.add_argument("--overseas-order-pages", type=int, default=3, choices=range(1, 11))
    trade_cash_execute.add_argument("--overseas-transaction-pages", type=int, default=2, choices=range(1, 11))
    trade_cash_execute.add_argument("--expected-plan-hash")
    trade_cash_execute.add_argument("--expected-budget-hash")
    trade_cash_execute.add_argument("--pre-backup-manifest")
    trade_cash_execute.add_argument(
        "--apply",
        action="store_true",
        help="Perform guarded KIS reads and MotherDuck writes after all immutable preconditions match.",
    )

    wi021_s06 = subparsers.add_parser(
        "run-wi021-s06",
        help="Run the fixed-hash one-off trade/cash backfill with private recovery verification.",
    )
    wi021_s06.add_argument("--start-date", required=True, help="Exact YYYYMMDD")
    wi021_s06.add_argument("--end-date", required=True, help="Exact YYYYMMDD")
    wi021_s06.add_argument(
        "--as-of-date",
        help="Exact YYYYMMDD; defaults to --end-date for the fixed historical backfill",
    )
    wi021_s06.add_argument("--expected-plan-hash", required=True)
    wi021_s06.add_argument("--expected-budget-hash", required=True)
    wi021_s06.add_argument("--project", required=True)
    wi021_s06.add_argument("--bucket", required=True)

    reconstruction_plan = subparsers.add_parser(
        "plan-position-reconstruction-v2",
        help="Read production governed facts and print an aggregate-only reconstruction dry-run.",
    )
    reconstruction_plan.add_argument(
        "--start-at", required=True,
        help="Timezone-aware ISO-8601 reconstruction start, for example 2023-08-28T00:00:00+09:00",
    )
    reconstruction_plan.add_argument(
        "--cutoff-at", required=True,
        help="Timezone-aware ISO-8601 reconstruction cutoff.",
    )
    wi022_s06 = subparsers.add_parser(
        "run-wi022-s06",
        help="Apply the exact reviewed reconstruction with private recovery verification.",
    )
    wi022_s06.add_argument("--start-at", required=True, help="Timezone-aware ISO-8601 start")
    wi022_s06.add_argument("--cutoff-at", required=True, help="Timezone-aware ISO-8601 cutoff")
    wi022_s06.add_argument("--expected-execution-hash", required=True)
    wi022_s06.add_argument("--project", required=True)
    wi022_s06.add_argument("--bucket", required=True)
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


def _build_trade_cash_backfill_plan(args: argparse.Namespace):
    today = datetime.now(ZoneInfo("Asia/Seoul")).date()
    end_date = today if args.end_date == "today" else datetime.strptime(args.end_date, "%Y%m%d").date()
    as_of_date = (
        today if args.as_of_date == "today" else datetime.strptime(args.as_of_date, "%Y%m%d").date()
    )
    start_date = (
        datetime.strptime(args.start_date, "%Y%m%d").date()
        if args.start_date else None
    )
    scopes = account_scopes_from_registry(
        load_account_registry(),
        overseas_account_labels=args.overseas_account_labels or ("brokerage",),
        overseas_exchanges=args.overseas_exchanges or ("NAS",),
    )
    source_plan = plan_trade_cash_backfill(
        scopes,
        start_date=start_date,
        end_date=end_date,
        as_of_date=as_of_date,
        partition_days=args.partition_days,
    )
    plan = apply_call_budget(
        source_plan,
        policy=BackfillBudgetPolicy(
            max_physical_calls=args.max_physical_calls,
            page_limits=(
                (DOMESTIC_ORDER_HISTORY, args.domestic_order_pages),
                (OVERSEAS_ORDER_HISTORY, args.overseas_order_pages),
                (OVERSEAS_TRANSACTION_HISTORY, args.overseas_transaction_pages),
            ),
        ),
    )
    return plan


def _run_trade_cash_backfill_plan(args: argparse.Namespace) -> int:
    plan = _build_trade_cash_backfill_plan(args)
    print(json.dumps(plan.public_dict(), ensure_ascii=False, indent=2))
    return 0


def _run_trade_cash_backfill(args: argparse.Namespace) -> int:
    plan = _build_trade_cash_backfill_plan(args)
    preflight = {
        "status": "ready" if args.apply else "preflight",
        "side_effects": "enabled" if args.apply else "none",
        "plan_id": plan.source_plan.plan_id,
        "plan_version": plan.source_plan.plan_version,
        "plan_hash": plan.source_plan.plan_hash,
        "budget_hash": plan.budget_hash,
        "callable_partition_count": len(plan.source_plan.callable_partitions),
        "known_gap_count": len(plan.source_plan.known_gaps),
        "reserved_call_ceiling": plan.reserved_call_ceiling,
        "max_physical_calls": plan.policy.max_physical_calls,
        "database_mode": get_db_mode(),
    }
    if not args.apply:
        print(json.dumps(preflight, ensure_ascii=False, indent=2))
        return 0

    if args.expected_plan_hash != plan.source_plan.plan_hash:
        raise RuntimeError("expected plan hash does not match the deterministic preflight")
    if args.expected_budget_hash != plan.budget_hash:
        raise RuntimeError("expected budget hash does not match the deterministic preflight")
    if get_db_mode() != "motherduck":
        raise RuntimeError("production trade/cash backfill requires KIS_DB_MODE=motherduck")
    if not args.pre_backup_manifest:
        raise RuntimeError("production trade/cash backfill requires --pre-backup-manifest")
    manifest_path = Path(args.pre_backup_manifest).expanduser().resolve()
    if not manifest_path.is_file():
        raise RuntimeError("pre-backup manifest does not exist")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    required_backup_tables = {
        "bronze.source_observations",
        "silver.trade_events",
        "silver.trade_event_revisions",
        "silver.cash_flow_events",
        "silver.cash_flow_event_revisions",
        "control.pipeline_runs",
        "control.pipeline_stage_runs",
        "control.watermarks",
    }
    if not required_backup_tables.issubset(set(manifest.get("tables", {}))):
        raise RuntimeError("pre-backup manifest is missing required trade/cash recovery tables")

    accounts = load_account_registry()
    connection = get_connection()
    MigrationRunner(connection).require("0008")
    source = KisTradeCashBackfillSource(accounts)
    handler = build_trade_cash_partition_handler(connection, source.fetch)
    outcome = execute_trade_cash_backfill(connection, plan, handler)
    result = {
        **preflight,
        "status": "succeeded",
        "partition_count": len(outcome.partition_outcomes),
        "reused_partition_count": sum(1 for item in outcome.partition_outcomes if item.reused),
        "source_calls": sum(item.source_calls for item in outcome.partition_outcomes),
        "restored_source_calls": outcome.restored_source_calls,
        "pre_backup_manifest": manifest_path.name,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def _run_wi021_s06(args: argparse.Namespace) -> int:
    try:
        as_of_date = args.as_of_date or args.end_date
        result = run_wi021_s06(WI021S06Config(
            start_date=datetime.strptime(args.start_date, "%Y%m%d").date(),
            end_date=datetime.strptime(args.end_date, "%Y%m%d").date(),
            as_of_date=datetime.strptime(as_of_date, "%Y%m%d").date(),
            expected_plan_hash=args.expected_plan_hash,
            expected_budget_hash=args.expected_budget_hash,
            project=args.project,
            bucket=args.bucket,
        ))
    except Exception as exc:
        print(json.dumps({
            "status": "failed",
            "error_type": type(exc).__name__,
            "detail": "redacted; inspect aggregate control evidence before a deliberate resume",
        }))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def _run_position_reconstruction_plan(args: argparse.Namespace) -> int:
    if get_db_mode() != "motherduck":
        raise RuntimeError("production reconstruction dry-run requires KIS_DB_MODE=motherduck")
    token = get_motherduck_token()
    if not token:
        raise RuntimeError("production reconstruction dry-run requires MOTHERDUCK_TOKEN")
    start_at = datetime.fromisoformat(args.start_at)
    cutoff_at = datetime.fromisoformat(args.cutoff_at)
    connection = duckdb.connect(
        f"md:{get_motherduck_database()}?motherduck_token={token}",
        read_only=True,
    )
    try:
        report = build_reconstruction_execution_plan(
            connection,
            start_at=start_at,
            cutoff_at=cutoff_at,
        ).public_report()
    finally:
        connection.close()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


def _run_wi022_s06(args: argparse.Namespace) -> int:
    try:
        result = run_wi022_s06(WI022S06Config(
            start_at=datetime.fromisoformat(args.start_at),
            cutoff_at=datetime.fromisoformat(args.cutoff_at),
            expected_execution_hash=args.expected_execution_hash,
            project=args.project,
            bucket=args.bucket,
        ))
    except Exception as exc:
        failure = {
            "status": "failed",
            "error_type": type(exc).__name__,
            "detail": "redacted; inspect aggregate recovery evidence before deliberate resume",
        }
        if isinstance(exc, WI022S06PhaseError):
            failure["phase"] = exc.phase
            failure["cause_type"] = exc.cause_type
        print(json.dumps(failure))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


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
    if args.command == "plan-trade-cash-backfill-v2":
        raise SystemExit(_run_trade_cash_backfill_plan(args))
    if args.command == "backfill-trade-cash-history-v2":
        raise SystemExit(_run_trade_cash_backfill(args))
    if args.command == "run-wi021-s06":
        raise SystemExit(_run_wi021_s06(args))
    if args.command == "plan-position-reconstruction-v2":
        raise SystemExit(_run_position_reconstruction_plan(args))
    if args.command == "run-wi022-s06":
        raise SystemExit(_run_wi022_s06(args))

    parser.print_help()
    raise SystemExit(2)
