"""Independent bounded incremental trade/cash collection.

This producer deliberately shares the existing source and normalization code
without joining the owned-portfolio core run or failure state.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Iterable

import duckdb

from kis_portfolio.account_registry import AccountConfig
from kis_portfolio.services.trade_cash_backfill import (
    DOMESTIC_ORDER_HISTORY,
    OVERSEAS_ORDER_HISTORY,
    OVERSEAS_TRANSACTION_HISTORY,
    BackfillBudgetPolicy,
    account_scopes_from_registry,
    apply_call_budget,
    plan_trade_cash_backfill,
)
from kis_portfolio.services.trade_cash_backfill_pipeline import (
    PartitionFetcher,
    build_trade_cash_partition_handler,
)
from kis_portfolio.services.trade_cash_backfill_runtime import (
    PIPELINE_ID as BACKFILL_PIPELINE_ID,
    WATERMARK_TYPE,
    execute_trade_cash_backfill,
)
from kis_portfolio.services.trade_cash_backfill_source import KisTradeCashBackfillSource


PIPELINE_ID = "pipeline.trade-incremental-v2"
PIPELINE_VERSION = "1.0.0"
INCREMENTAL_SLOT = "daily"
MAX_REPLAY_DAYS = 120
MAX_PHYSICAL_CALLS = 48
QUERY_COVERAGE_WATERMARK_TYPE = "trade_query_coverage_v1"


def _minimum_watermark(
    connection: duckdb.DuckDBPyConnection,
    pipeline_id: str,
) -> date | None:
    row = connection.execute(
        """
        SELECT min(try_cast(watermark_value AS DATE))
        FROM control.watermarks
        WHERE pipeline_id=? AND watermark_type=?
        """,
        [pipeline_id, WATERMARK_TYPE],
    ).fetchone()
    return None if row is None or row[0] is None else row[0]


def resolve_incremental_start(
    connection: duckdb.DuckDBPyConnection,
    *,
    end_date: date,
    requested_start: date | None = None,
) -> date:
    """Resolve a bounded contiguous start without silently skipping a gap."""

    incremental = _minimum_watermark(connection, PIPELINE_ID)
    predecessor = _minimum_watermark(connection, BACKFILL_PIPELINE_ID)
    coverage = incremental or predecessor
    start = requested_start or (coverage + timedelta(days=1) if coverage else end_date)
    if start > end_date:
        return end_date
    if (end_date - start).days + 1 > MAX_REPLAY_DAYS:
        raise ValueError(
            f"incremental replay exceeds {MAX_REPLAY_DAYS} days; "
            "run a reviewed bounded recovery window"
        )
    if coverage is not None and start > coverage + timedelta(days=1):
        raise ValueError(
            f"incremental replay would skip governed coverage after {coverage.isoformat()}"
        )
    return start


def run_trade_incremental(
    connection: duckdb.DuckDBPyConnection,
    accounts: Iterable[AccountConfig],
    *,
    end_date: date,
    start_date: date | None = None,
    overseas_account_labels: tuple[str, ...] = ("brokerage",),
    overseas_exchanges: tuple[str, ...] = ("NAS",),
    scope: str = "all",
    fetch_partition: PartitionFetcher | None = None,
) -> dict[str, Any]:
    """Collect one bounded current/recovery window with isolated run state."""

    account_list = list(accounts)
    resolved_start = resolve_incremental_start(
        connection,
        end_date=end_date,
        requested_start=start_date,
    )
    if scope not in {"all", "domestic", "overseas"}:
        raise ValueError("scope must be all, domestic or overseas")
    account_scopes = account_scopes_from_registry(
            account_list,
            overseas_account_labels=overseas_account_labels,
            overseas_exchanges=overseas_exchanges,
        )
    source_plan = plan_trade_cash_backfill(
        account_scopes,
        start_date=resolved_start,
        end_date=end_date,
        as_of_date=end_date,
        partition_days=90,
        include_domestic=scope in {"all", "domestic"},
        include_overseas=scope in {"all", "overseas"},
    )
    plan = apply_call_budget(
        source_plan,
        policy=BackfillBudgetPolicy(
            policy_id="budget.trade-incremental-v2",
            policy_version="1.0.0",
            max_physical_calls=MAX_PHYSICAL_CALLS,
            page_limits=(
                (DOMESTIC_ORDER_HISTORY, 3),
                (OVERSEAS_ORDER_HISTORY, 3),
                (OVERSEAS_TRANSACTION_HISTORY, 2),
            ),
        ),
    )
    source = KisTradeCashBackfillSource(account_list)
    handler = build_trade_cash_partition_handler(
        connection,
        fetch_partition or source.fetch,
    )
    outcome = execute_trade_cash_backfill(
        connection,
        plan,
        handler,
        pipeline_id=PIPELINE_ID,
        pipeline_version=PIPELINE_VERSION,
        slot=f"{INCREMENTAL_SLOT}-{scope}",
        predecessor_pipeline_id=BACKFILL_PIPELINE_ID,
    )
    outcomes_by_partition = dict(zip(
        plan.source_plan.callable_partitions,
        outcome.partition_outcomes,
        strict=True,
    ))
    trade_gap_markets = {
        (partition.account_label, partition.exchange or "KRX")
        for partition in plan.source_plan.known_gaps
        if "dataset.trade-event" in partition.output_dataset_ids
    }
    expected_markets = {
        account_scope.label: {"KRX", *account_scope.overseas_exchanges}
        for account_scope in account_scopes
    }
    published_markets: list[str] = []
    for account_label, market in sorted({
        (partition.account_label, partition.exchange or "KRX")
        for partition in plan.source_plan.callable_partitions
        if "dataset.trade-event" in partition.output_dataset_ids
    } - trade_gap_markets):
        market_outcomes = [
            outcomes_by_partition[partition]
            for partition in plan.source_plan.callable_partitions
            if partition.account_label == account_label
            and (partition.exchange or "KRX") == market
            and "dataset.trade-event" in partition.output_dataset_ids
        ]
        if not market_outcomes or any(item.status != "succeeded" for item in market_outcomes):
            continue
        connection.execute(
            """
            INSERT INTO control.watermarks VALUES (?, ?, ?, ?, ?, current_timestamp)
            ON CONFLICT(pipeline_id, partition_key, watermark_type) DO UPDATE SET
                watermark_value=excluded.watermark_value,
                run_id=excluded.run_id,
                updated_at=excluded.updated_at
            """,
            [
                PIPELINE_ID,
                f"account:{account_label}|market:{market}",
                QUERY_COVERAGE_WATERMARK_TYPE,
                end_date.isoformat(),
                market_outcomes[-1].run_id,
            ],
        )
        published_markets.append(f"{account_label}:{market}")

    published_accounts: list[str] = []
    for account_label, markets in sorted(expected_markets.items()):
        if any((account_label, market) in trade_gap_markets for market in markets):
            continue
        market_rows = connection.execute(
            """SELECT partition_key, try_cast(watermark_value AS DATE), run_id
               FROM control.watermarks
               WHERE pipeline_id=? AND watermark_type=?
                 AND partition_key LIKE ?""",
            [PIPELINE_ID, QUERY_COVERAGE_WATERMARK_TYPE, f"account:{account_label}|market:%"],
        ).fetchall()
        values = {
            row[0].split("|market:", 1)[1]: (row[1], row[2])
            for row in market_rows
        }
        if not markets.issubset(values) or any(values[market][0] is None for market in markets):
            continue
        coverage = min(values[market][0] for market in markets)
        run_id = sorted((values[market][1] for market in markets))[-1]
        connection.execute(
            """
            INSERT INTO control.watermarks VALUES (?, ?, ?, ?, ?, current_timestamp)
            ON CONFLICT(pipeline_id, partition_key, watermark_type) DO UPDATE SET
                watermark_value=excluded.watermark_value,
                run_id=excluded.run_id,
                updated_at=excluded.updated_at
            """,
            [
                PIPELINE_ID,
                f"account:{account_label}",
                QUERY_COVERAGE_WATERMARK_TYPE,
                coverage.isoformat(),
                run_id,
            ],
        )
        published_accounts.append(account_label)
    all_accounts = sorted(expected_markets)
    if not trade_gap_markets and published_accounts == all_accounts:
        connection.execute(
            """
            INSERT INTO control.watermarks VALUES (?, 'all-accounts', ?, ?, ?, current_timestamp)
            ON CONFLICT(pipeline_id, partition_key, watermark_type) DO UPDATE SET
                watermark_value=excluded.watermark_value,
                run_id=excluded.run_id,
                updated_at=excluded.updated_at
            """,
            [
                PIPELINE_ID,
                QUERY_COVERAGE_WATERMARK_TYPE,
                end_date.isoformat(),
                outcome.partition_outcomes[-1].run_id,
            ],
        )
    return {
        "status": "succeeded",
        "pipeline_id": PIPELINE_ID,
        "pipeline_version": PIPELINE_VERSION,
        "scope": scope,
        "start_date": resolved_start.isoformat(),
        "end_date": end_date.isoformat(),
        "partition_count": len(outcome.partition_outcomes),
        "known_gap_count": len(plan.source_plan.known_gaps),
        "reused_partition_count": sum(item.reused for item in outcome.partition_outcomes),
        "source_calls": sum(item.source_calls for item in outcome.partition_outcomes),
        "reserved_call_ceiling": plan.reserved_call_ceiling,
        "coverage_accounts": published_accounts,
        "coverage_markets": published_markets,
        "trade_gap_partitions": [f"{account}:{market}" for account, market in sorted(trade_gap_markets)],
    }
