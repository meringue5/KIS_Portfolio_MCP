from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import duckdb

from kis_portfolio.platform.migrations import MigrationRunner
from kis_portfolio.services.position_reconstruction_runtime import (
    build_reconstruction_execution_plan,
)


START = datetime(2023, 8, 28, tzinfo=UTC)
CUTOFF = datetime(2026, 8, 28, 23, 59, tzinfo=UTC)


def _connection(*, through: str | None = None) -> duckdb.DuckDBPyConnection:
    connection = duckdb.connect(":memory:")
    MigrationRunner(connection).apply(through=through)
    return connection


def _seed_trade(
    connection: duckdb.DuckDBPyConnection,
    *,
    event_id: str,
    side: str,
    quantity: int,
    day: int,
) -> None:
    connection.execute(
        """
        INSERT INTO silver.trade_event_revisions(
            trade_event_revision_id,source_trade_event_id,account_id,market,product_code,
            instrument_id,broker_order_id,executed_at,execution_sequence,revision,side,
            quantity,price,currency,knowledge_at,source_observation_id,correction_reason,
            quality_status,metadata
        ) VALUES (?,?,?,?,?,?,?,?,?,1,?,?,?,?,?,?,?,?,?)
        """,
        [event_id, f"source-{event_id}", "account-1", "KRX", "01", "instrument-1",
         f"order-{event_id}", START + timedelta(days=day), "1", side, quantity, 100,
         "KRW", CUTOFF - timedelta(hours=1), f"observation-{event_id}", "fixture",
         "pass", "{}"],
    )


def _seed_position(connection: duckdb.DuckDBPyConnection, quantity: int = 3) -> None:
    connection.execute(
        """
        INSERT INTO silver.position_snapshots(
            account_id,instrument_id,as_of,quantity,average_cost,cost_currency,
            source_observation_id,quality_status
        ) VALUES ('account-1','instrument-1',?, ?,100,'KRW','position-observation','pass')
        """,
        [CUTOFF - timedelta(hours=2), quantity],
    )


def _seed_coverage(connection: duckdb.DuckDBPyConnection) -> None:
    connection.execute(
        """
        INSERT INTO control.quality_results(
            quality_result_id,run_id,dataset_id,rule_id,status,observed_value,
            expected_value,details,evaluated_at
        ) VALUES ('coverage-1','run-coverage','dataset.corporate-action-event',
                  'held_instrument_date_range_coverage','pass','complete','complete',?,?)
        """,
        [json.dumps({
            "instrument_id": "instrument-1",
            "start_date": START.date().isoformat(),
            "end_date": CUTOFF.date().isoformat(),
        }), CUTOFF - timedelta(minutes=1)],
    )


def test_read_only_dry_run_without_action_coverage_is_exception_only_and_stable() -> None:
    connection = _connection(through="0008")
    _seed_position(connection)
    _seed_trade(connection, event_id="buy-1", side="buy", quantity=5, day=1)
    _seed_trade(connection, event_id="sell-1", side="sell", quantity=2, day=2)
    before = connection.execute(
        "SELECT count(*) FROM silver.trade_event_revisions"
    ).fetchone()[0]

    first = build_reconstruction_execution_plan(connection, start_at=START, cutoff_at=CUTOFF)
    second = build_reconstruction_execution_plan(connection, start_at=START, cutoff_at=CUTOFF)
    report = first.public_report()

    assert first.execution_hash == second.execution_hash
    assert report["partition_count"] == 1
    assert report["status_counts"] == {"not_assessed": 1}
    assert report["eligible_projection_partitions"] == 0
    assert report["projected_exception_identities"] == 1
    assert report["source_calls"] == report["warehouse_writes"] == 0
    assert report["s06_ready"] is True
    assert connection.execute(
        "SELECT count(*) FROM silver.trade_event_revisions"
    ).fetchone()[0] == before
    connection.close()


def test_passing_coverage_projects_reconciled_episode_lot_and_allocation() -> None:
    connection = _connection()
    _seed_position(connection)
    _seed_trade(connection, event_id="buy-1", side="buy", quantity=5, day=1)
    _seed_trade(connection, event_id="sell-1", side="sell", quantity=2, day=2)
    _seed_coverage(connection)

    plan = build_reconstruction_execution_plan(connection, start_at=START, cutoff_at=CUTOFF)
    report = plan.public_report()

    assert report["status_counts"] == {"reconstructed": 1}
    assert report["eligible_projection_partitions"] == 1
    assert report["projected_episode_identities"] == 1
    assert report["projected_lot_identities"] == 1
    assert report["projected_allocation_revisions"] == 1
    assert report["projected_allocation_slices"] == 1
    assert report["projected_exception_identities"] == 0
    connection.close()


def test_trade_only_scope_without_current_account_snapshot_remains_provisional() -> None:
    connection = _connection()
    _seed_trade(connection, event_id="buy-1", side="buy", quantity=5, day=1)
    _seed_coverage(connection)

    report = build_reconstruction_execution_plan(
        connection, start_at=START, cutoff_at=CUTOFF
    ).public_report()

    assert report["trade_only_partition_count"] == 1
    assert report["status_counts"] == {"provisional": 1}
    assert report["blocker_counts"] == {"missing_current_account_snapshot": 1}
    assert report["projected_exception_identities"] == 1
    connection.close()


def test_public_report_contains_no_confidential_partition_identity() -> None:
    connection = _connection(through="0008")
    _seed_position(connection)
    _seed_trade(connection, event_id="buy-1", side="buy", quantity=3, day=1)

    report_text = json.dumps(build_reconstruction_execution_plan(
        connection, start_at=START, cutoff_at=CUTOFF
    ).public_report(), sort_keys=True)

    assert "account-1" not in report_text
    assert "instrument-1" not in report_text
    assert "buy-1" not in report_text
    assert "position-observation" not in report_text
    connection.close()
