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


def test_corrected_venue_pipeline_reprocesses_old_empty_success_without_duplicates(tmp_path, monkeypatch):
    import kis_portfolio.services.trade_incremental as incremental
    from kis_portfolio.services import kis_api

    connection = _connection(tmp_path / 'sor-recovery.duckdb')

    def empty(partition, gate):
        gate.reserve(partition.key)
        return FetchedBackfillPartition((BackfillSourcePage({'output1': []}, FETCHED),), True)

    monkeypatch.setattr(incremental, 'PIPELINE_VERSION', '1.0.0')
    old = incremental.run_trade_incremental(connection, [_account()], start_date=DAY, end_date=DAY, scope='domestic', fetch_partition=empty)
    assert old['status'] == 'succeeded'

    async def source(path, tr_id, params, **kwargs):
        assert params['EXCG_ID_DVSN_CD'] == 'ALL'
        kwargs['before_request'](1)
        return {'captured_pages': [{'rt_cd': '0', 'output1': [
            {'ord_dt': '20260924', 'ord_tmd': '101500', 'pdno': '005930', 'odno': 'SOR-FIXTURE', 'ord_gno_brno': '01', 'sll_buy_dvsn_cd': '02', 'tot_ccld_qty': '3', 'avg_prvs': '70000', 'excg_id_dvsn_cd': 'SOR'},
        ]}]}

    monkeypatch.setattr(kis_api, '_get_paginated_kis_json', source)
    monkeypatch.setattr(incremental, 'PIPELINE_VERSION', '1.0.1')
    corrected = incremental.run_trade_incremental(connection, [_account()], start_date=DAY, end_date=DAY, scope='domestic')
    assert corrected['reused_partition_count'] == 0
    assert connection.execute('select count(*), sum(quantity) from silver.trade_events_current').fetchone() == (1, 3)
    assert connection.execute("select json_extract_string(payload, '$.excg_id_dvsn_cd') from bronze.source_observations").fetchone() == ('SOR',)
    repeated = incremental.run_trade_incremental(connection, [_account()], start_date=DAY, end_date=DAY, scope='domestic')
    assert repeated['reused_partition_count'] == corrected['partition_count']
    assert connection.execute('select count(*) from silver.trade_events_current').fetchone()[0] == 1
    assert connection.execute('select distinct pipeline_version from control.pipeline_runs order by 1').fetchall() == [('1.0.0',), ('1.0.1',)]
    connection.close()


def test_start_uses_complete_scoped_query_coverage_and_preserves_gap_guards(tmp_path):
    connection = _connection(tmp_path / 'query-coverage.duckdb')
    def watermark(key, kind, value):
        connection.execute('INSERT INTO control.watermarks VALUES (?,?,?,?,?,current_timestamp)', [PIPELINE_ID,key,kind,value,'fixture'])
    watermark('historical-domestic-route', 'source_end_date_v1', '2026-07-14')
    watermark('account:brokerage|market:KRX', QUERY_COVERAGE_WATERMARK_TYPE, '2026-10-13')
    watermark('account:brokerage|market:NAS', QUERY_COVERAGE_WATERMARK_TYPE, '2026-07-14')
    keys = ('account:brokerage|market:KRX',)
    assert resolve_incremental_start(connection, end_date=date(2026,10,14), coverage_keys=keys) == date(2026,10,14)
    assert resolve_incremental_start(connection, end_date=date(2026,10,14), requested_start=date(2026,10,7), coverage_keys=keys) == date(2026,10,7)
    with pytest.raises(ValueError, match='skip governed coverage'):
        resolve_incremental_start(connection, end_date=date(2026,10,16), requested_start=date(2026,10,15), coverage_keys=keys)
    with pytest.raises(ValueError, match='skip governed coverage'):
        resolve_incremental_start(connection, end_date=date(2026,10,14), requested_start=date(2026,10,7), coverage_keys=keys+('account:ria|market:KRX',))
    with pytest.raises(ValueError, match='skip governed coverage'):
        resolve_incremental_start(connection, end_date=date(2026,10,14), requested_start=date(2026,10,7), coverage_keys=('account:brokerage|market:NAS',))
    with pytest.raises(ValueError, match='exceeds 120 days'):
        resolve_incremental_start(connection, end_date=date(2026,10,14), requested_start=date(2026,1,1), coverage_keys=keys)
    connection.close()
