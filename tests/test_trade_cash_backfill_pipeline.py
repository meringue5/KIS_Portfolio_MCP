from __future__ import annotations

from collections import Counter
from datetime import UTC, date, datetime
from pathlib import Path

import duckdb
import pytest

from kis_portfolio.platform.migrations import MigrationRunner
from kis_portfolio.platform.pipeline import PipelineExecutionError
from kis_portfolio.services.trade_cash_backfill import (
    DOMESTIC_ORDER_HISTORY,
    OVERSEAS_ORDER_HISTORY,
    OVERSEAS_TRANSACTION_HISTORY,
    BackfillAccountScope,
    apply_call_budget,
    plan_trade_cash_backfill,
)
from kis_portfolio.services.trade_cash_backfill_pipeline import (
    BackfillSourcePage,
    FetchedBackfillPartition,
    build_trade_cash_partition_handler,
)
from kis_portfolio.services.trade_cash_backfill_runtime import (
    PIPELINE_ID,
    execute_trade_cash_backfill,
)


DAY = date(2026, 8, 28)
FETCHED = datetime(2026, 8, 28, 9, tzinfo=UTC)


def _connection(path: Path):
    connection = duckdb.connect(str(path))
    MigrationRunner(connection).apply()
    return connection


def _plan(*, overseas: bool = False):
    return apply_call_budget(
        plan_trade_cash_backfill(
            [
                BackfillAccountScope(
                    "brokerage" if overseas else "ria",
                    "01",
                    overseas_exchanges=("NAS",) if overseas else (),
                )
            ],
            start_date=DAY,
            end_date=DAY,
            as_of_date=DAY,
        )
    )


def test_fixture_pages_reconcile_trade_cash_without_creating_lots(tmp_path: Path) -> None:
    connection = _connection(tmp_path / "fixture-reconciliation.duckdb")
    plan = _plan(overseas=True)
    invocations: Counter[str] = Counter()

    def fetch(partition, gate):
        invocations[partition.source_operation] += 1
        gate.reserve(partition.key)
        if partition.source_operation == DOMESTIC_ORDER_HISTORY:
            payload = {
                "output1": [
                    {
                        "ord_dt": "20260828", "ord_tmd": "101500", "pdno": "005930",
                        "odno": "D-1", "ord_gno_brno": "01", "sll_buy_dvsn_cd": "02",
                        "tot_ccld_qty": "2", "avg_prvs": "70000",
                    },
                    {
                        "ord_dt": "20260828", "pdno": "000660", "odno": "D-2",
                        "sll_buy_dvsn_cd": "02", "tot_ccld_qty": "0", "avg_prvs": "100000",
                    },
                ]
            }
        elif partition.source_operation == OVERSEAS_ORDER_HISTORY:
            payload = {
                "output": [{
                    "ord_dt": "20260828", "ord_tmd": "103000", "ovrs_pdno": "AAPL",
                    "odno": "O-1", "ord_gno_brno": "02", "sll_buy_dvsn_cd": "01",
                    "ft_ccld_qty": "1", "ft_ccld_unpr3": "220", "tr_crcy_cd": "USD",
                }]
            }
        else:
            payload = {
                "output1": [{
                    "erlm_dt": "20260828", "pdno": "AAPL", "odno": "O-1",
                    "sll_buy_dvsn_cd": "01", "tr_qty": "1", "ft_ccld_unpr2": "220",
                    "sttl_amt": "218", "frcr_fee1": "1", "dmst_frcr_fee1": "1800", "tax": "1",
                    "sttl_dt": "20260830", "tr_crcy_cd": "USD", "trad_dvsn_cd": "SELL",
                }]
            }
        return FetchedBackfillPartition((BackfillSourcePage(payload, FETCHED),), True)

    handler = build_trade_cash_partition_handler(connection, fetch)
    first = execute_trade_cash_backfill(connection, plan, handler)

    assert len(first.partition_outcomes) == 3
    assert invocations == Counter({
        DOMESTIC_ORDER_HISTORY: 1,
        OVERSEAS_ORDER_HISTORY: 1,
        OVERSEAS_TRANSACTION_HISTORY: 1,
    })
    assert connection.execute("SELECT count(*) FROM silver.trade_events").fetchone()[0] == 2
    assert connection.execute("SELECT side, count(*) FROM silver.trade_events GROUP BY side ORDER BY side").fetchall() == [
        ("buy", 1), ("sell", 1),
    ]
    assert connection.execute("SELECT count(*) FROM silver.purchase_lots").fetchone()[0] == 0
    assert connection.execute(
        "SELECT event_type, amount, currency FROM silver.cash_flow_events_current "
        "ORDER BY event_type, amount, currency"
    ).fetchall() == [
        ("fee", -1800, "KRW"),
        ("fee", -1, "USD"),
        ("tax", -1, "USD"),
        ("trade_settlement_in", 218, "USD"),
    ]
    assert connection.execute(
        "SELECT count(*) FROM bronze.source_observations WHERE quality_status='candidate'"
    ).fetchone()[0] == 1
    assert connection.execute(
        "SELECT count(*) FROM control.quality_results WHERE status='pass'"
    ).fetchone()[0] == 6

    reused = execute_trade_cash_backfill(connection, plan, handler)
    assert all(item.reused for item in reused.partition_outcomes)
    assert invocations == Counter({
        DOMESTIC_ORDER_HISTORY: 1,
        OVERSEAS_ORDER_HISTORY: 1,
        OVERSEAS_TRANSACTION_HISTORY: 1,
    })
    assert connection.execute("SELECT count(*) FROM silver.trade_events").fetchone()[0] == 2
    assert connection.execute("SELECT count(*) FROM silver.cash_flow_events").fetchone()[0] == 4
    connection.close()


def test_incomplete_pagination_lands_observation_but_blocks_silver_and_watermark(
    tmp_path: Path,
) -> None:
    connection = _connection(tmp_path / "incomplete.duckdb")
    plan = _plan()

    def fetch(partition, gate):
        gate.reserve(partition.key)
        return FetchedBackfillPartition(
            (
                BackfillSourcePage(
                    {
                        "output1": [{
                            "ord_dt": "20260828", "ord_tmd": "101500", "pdno": "005930",
                            "odno": "D-1", "sll_buy_dvsn_cd": "02",
                            "tot_ccld_qty": "1", "avg_prvs": "70000",
                        }]
                    },
                    FETCHED,
                ),
            ),
            False,
            "continuation remained after approved page limit",
        )

    handler = build_trade_cash_partition_handler(connection, fetch)
    with pytest.raises(PipelineExecutionError, match="pagination incomplete"):
        execute_trade_cash_backfill(connection, plan, handler)

    assert connection.execute("SELECT count(*) FROM bronze.source_observations").fetchone()[0] == 1
    assert connection.execute("SELECT count(*) FROM silver.trade_events").fetchone()[0] == 0
    assert connection.execute("SELECT count(*) FROM control.watermarks").fetchone()[0] == 0
    assert connection.execute(
        "SELECT status, source_calls FROM control.pipeline_stage_runs WHERE stage_name='collect-land-normalize'"
    ).fetchone() == ("failed", 1)
    assert connection.execute(
        "SELECT status FROM control.pipeline_runs WHERE pipeline_id=?", [PIPELINE_ID]
    ).fetchone()[0] == "failed"
    connection.close()
