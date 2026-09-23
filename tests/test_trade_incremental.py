from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

import duckdb
import pytest

from kis_portfolio.account_registry import AccountConfig
from kis_portfolio.platform.migrations import MigrationRunner
from kis_portfolio.platform.pipeline import PipelineExecutionError
from kis_portfolio.services.trade_cash_backfill_pipeline import (
    BackfillSourcePage,
    FetchedBackfillPartition,
)
from kis_portfolio.services.trade_incremental import (
    PIPELINE_ID,
    QUERY_COVERAGE_WATERMARK_TYPE,
    resolve_incremental_start,
    run_trade_incremental,
)


DAY = date(2026, 9, 24)
FETCHED = datetime(2026, 9, 24, 8, tzinfo=UTC)


def _connection(path: Path):
    connection = duckdb.connect(str(path))
    MigrationRunner(connection).apply()
    return connection


def _account(label: str = "brokerage") -> AccountConfig:
    return AccountConfig(
        label, label.upper(), label, "fixture-key", "fixture-secret",
        "12345678", "01", "REAL",
    )


def test_incremental_empty_pages_publish_scoped_coverage_and_reuse(tmp_path: Path) -> None:
    connection = _connection(tmp_path / "incremental.duckdb")
    calls = []

    def fetch(partition, gate):
        calls.append(partition.key)
        gate.reserve(partition.key)
        row_key = "output" if partition.source_operation == "overseas-order-history" else "output1"
        return FetchedBackfillPartition(
            (BackfillSourcePage({row_key: []}, FETCHED),),
            True,
        )

    first = run_trade_incremental(
        connection,
        [_account()],
        start_date=DAY,
        end_date=DAY,
        fetch_partition=fetch,
    )
    second = run_trade_incremental(
        connection,
        [_account()],
        start_date=DAY,
        end_date=DAY,
        fetch_partition=fetch,
    )

    assert first["status"] == "succeeded"
    assert first["coverage_accounts"] == ["brokerage"]
    assert first["trade_gap_partitions"] == []
    assert first["coverage_markets"] == ["brokerage:KRX", "brokerage:NAS"]
    assert second["reused_partition_count"] == first["partition_count"]
    assert len(calls) == first["partition_count"]
    assert connection.execute(
        """SELECT partition_key, watermark_value FROM control.watermarks
           WHERE pipeline_id=? AND watermark_type=? ORDER BY partition_key""",
        [PIPELINE_ID, QUERY_COVERAGE_WATERMARK_TYPE],
    ).fetchall() == [
        ("account:brokerage", DAY.isoformat()),
        ("account:brokerage|market:KRX", DAY.isoformat()),
        ("account:brokerage|market:NAS", DAY.isoformat()),
        ("all-accounts", DAY.isoformat()),
    ]
    assert connection.execute(
        "SELECT count(*) FROM control.quality_results WHERE dataset_id='dataset.trade-event'"
    ).fetchone()[0] == first["partition_count"] * 2
    connection.close()


def test_incremental_failure_keeps_query_coverage_unpublished(tmp_path: Path) -> None:
    connection = _connection(tmp_path / "failure.duckdb")

    def fetch(partition, gate):
        gate.reserve(partition.key)
        return FetchedBackfillPartition(
            (BackfillSourcePage({"output1": []}, FETCHED),),
            False,
            "fixture continuation",
        )

    with pytest.raises(PipelineExecutionError, match="pagination incomplete"):
        run_trade_incremental(
            connection,
            [_account("ria")],
            start_date=DAY,
            end_date=DAY,
            overseas_account_labels=(),
            fetch_partition=fetch,
        )

    assert connection.execute(
        """SELECT count(*) FROM control.watermarks
           WHERE pipeline_id=? AND watermark_type=?""",
        [PIPELINE_ID, QUERY_COVERAGE_WATERMARK_TYPE],
    ).fetchone()[0] == 0
    assert connection.execute(
        "SELECT count(*) FROM bronze.source_observations"
    ).fetchone()[0] == 0
    connection.close()


def test_incremental_start_rejects_skipped_and_unbounded_windows(tmp_path: Path) -> None:
    connection = _connection(tmp_path / "start.duckdb")
    connection.execute(
        """INSERT INTO control.watermarks VALUES (
           'pipeline.trade-incremental-v2','account:brokerage',
           'source_end_date_v1','2026-09-20','run-1',current_timestamp)"""
    )

    assert resolve_incremental_start(connection, end_date=DAY) == date(2026, 9, 21)
    with pytest.raises(ValueError, match="skip governed coverage"):
        resolve_incremental_start(
            connection,
            end_date=DAY,
            requested_start=date(2026, 9, 22),
        )
    with pytest.raises(ValueError, match="exceeds 120 days"):
        resolve_incremental_start(
            connection,
            end_date=DAY,
            requested_start=date(2026, 1, 1),
        )
    connection.close()
