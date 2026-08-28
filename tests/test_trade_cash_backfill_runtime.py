from __future__ import annotations

from collections import Counter
from datetime import date
from pathlib import Path

import duckdb
import pytest

from kis_portfolio.platform.migrations import MigrationRunner
from kis_portfolio.platform.pipeline import PipelineExecutionError, StageResult
from kis_portfolio.services.trade_cash_backfill import (
    BackfillAccountScope,
    BackfillBudgetExceeded,
    apply_call_budget,
    plan_trade_cash_backfill,
)
from kis_portfolio.services.trade_cash_backfill_runtime import (
    BACKFILL_SLOT,
    PIPELINE_ID,
    WATERMARK_TYPE,
    execute_trade_cash_backfill,
    watermark_partition_key,
)


START = date(2026, 8, 1)
END = date(2026, 8, 5)


def _plan(*, start: date = START, end: date = END):
    return apply_call_budget(
        plan_trade_cash_backfill(
            [BackfillAccountScope("ria", "01")],
            start_date=start,
            end_date=end,
            as_of_date=end,
            partition_days=2,
        )
    )


def _connection(path: Path):
    connection = duckdb.connect(str(path))
    MigrationRunner(connection).apply()
    return connection


def test_failed_partition_resumes_same_run_and_completed_partitions_are_reused(
    tmp_path: Path,
) -> None:
    connection = _connection(tmp_path / "resume.duckdb")
    plan = _plan()
    keys = [item.key for item in plan.source_plan.callable_partitions]
    calls: Counter[str] = Counter()

    def handler(partition, gate, _context):
        calls[partition.key] += 1
        gate.reserve(partition.key)
        if partition.key == keys[1] and calls[partition.key] == 1:
            raise RuntimeError("injected source failure")
        return StageResult(output_count=1, source_calls=1)

    with pytest.raises(PipelineExecutionError, match="injected source failure") as failed:
        execute_trade_cash_backfill(connection, plan, handler)
    failed_run_id = failed.value.run_id

    rows = connection.execute(
        """
        SELECT r.partition_key, r.run_id, r.status, s.source_calls
        FROM control.pipeline_runs r
        JOIN control.pipeline_stage_runs s ON s.run_id=r.run_id
        WHERE r.pipeline_id=? AND s.stage_name='collect-land-normalize'
        ORDER BY r.partition_key
        """,
        [PIPELINE_ID],
    ).fetchall()
    assert rows == [
        (keys[0], rows[0][1], "succeeded", 1),
        (keys[1], failed_run_id, "failed", 1),
    ]
    assert calls == Counter({keys[0]: 1, keys[1]: 1})

    resumed = execute_trade_cash_backfill(connection, plan, handler)
    assert resumed.restored_source_calls == 2
    assert calls == Counter({keys[1]: 2, keys[0]: 1, keys[2]: 1})
    resumed_run = connection.execute(
        "SELECT run_id, status FROM control.pipeline_runs WHERE partition_key=?",
        [keys[1]],
    ).fetchone()
    assert resumed_run == (failed_run_id, "succeeded")
    assert connection.execute(
        """
        SELECT attempt, source_calls FROM control.pipeline_stage_runs
        WHERE run_id=? AND stage_name='collect-land-normalize'
        """,
        [failed_run_id],
    ).fetchone() == (2, 2)

    calls_before_reuse = calls.copy()
    reused = execute_trade_cash_backfill(connection, plan, handler)
    assert calls == calls_before_reuse
    assert all(item.reused for item in reused.partition_outcomes)
    assert [item.run_id for item in reused.partition_outcomes] == [
        item.run_id for item in resumed.partition_outcomes
    ]
    connection.close()


def test_watermark_advances_only_after_publish_and_never_regresses(tmp_path: Path) -> None:
    connection = _connection(tmp_path / "watermark.duckdb")
    plan = _plan()
    partitions = plan.source_plan.callable_partitions
    stream_key = watermark_partition_key(partitions[0])

    def handler(partition, gate, _context):
        gate.reserve(partition.key)
        return StageResult(source_calls=1)

    execute_trade_cash_backfill(connection, plan, handler)
    assert connection.execute(
        """
        SELECT watermark_value FROM control.watermarks
        WHERE pipeline_id=? AND partition_key=? AND watermark_type=?
        """,
        [PIPELINE_ID, stream_key, WATERMARK_TYPE],
    ).fetchone()[0] == END.isoformat()

    older = _plan(start=START, end=date(2026, 8, 3))
    execute_trade_cash_backfill(connection, older, handler)
    assert connection.execute(
        """
        SELECT watermark_value FROM control.watermarks
        WHERE pipeline_id=? AND partition_key=? AND watermark_type=?
        """,
        [PIPELINE_ID, stream_key, WATERMARK_TYPE],
    ).fetchone()[0] == END.isoformat()
    connection.close()


def test_watermark_gap_fails_closed_after_collection_without_advancing(tmp_path: Path) -> None:
    connection = _connection(tmp_path / "gap.duckdb")
    plan = _plan(start=date(2026, 8, 4), end=date(2026, 8, 4))
    partition = plan.source_plan.callable_partitions[0]
    stream_key = watermark_partition_key(partition)
    connection.execute(
        "INSERT INTO control.watermarks VALUES (?, ?, ?, ?, ?, current_timestamp)",
        [PIPELINE_ID, stream_key, WATERMARK_TYPE, "2026-08-01", "fixture-run"],
    )
    invoked = 0

    def handler(current, gate, _context):
        nonlocal invoked
        invoked += 1
        gate.reserve(current.key)
        return StageResult(source_calls=1)

    with pytest.raises(PipelineExecutionError, match="watermark gap"):
        execute_trade_cash_backfill(connection, plan, handler)
    assert invoked == 1
    assert connection.execute(
        """
        SELECT watermark_value FROM control.watermarks
        WHERE pipeline_id=? AND partition_key=? AND watermark_type=?
        """,
        [PIPELINE_ID, stream_key, WATERMARK_TYPE],
    ).fetchone()[0] == "2026-08-01"
    connection.close()


def test_corrupt_persisted_usage_blocks_resume_before_handler(tmp_path: Path) -> None:
    connection = _connection(tmp_path / "budget.duckdb")
    plan = _plan(start=END, end=END)
    partition = plan.source_plan.callable_partitions[0]
    invoked = 0

    def failed_handler(current, gate, _context):
        nonlocal invoked
        invoked += 1
        gate.reserve(current.key)
        raise RuntimeError("fixture failure")

    with pytest.raises(PipelineExecutionError):
        execute_trade_cash_backfill(connection, plan, failed_handler)
    connection.execute(
        """
        UPDATE control.pipeline_stage_runs SET source_calls=4
        WHERE run_id=(SELECT run_id FROM control.pipeline_runs
                      WHERE pipeline_id=? AND logical_date=? AND slot=? AND partition_key=? )
          AND stage_name='collect-land-normalize'
        """,
        [PIPELINE_ID, END, BACKFILL_SLOT, partition.key],
    )

    with pytest.raises(BackfillBudgetExceeded, match="persisted partition usage"):
        execute_trade_cash_backfill(connection, plan, failed_handler)
    assert invoked == 1
    connection.close()
