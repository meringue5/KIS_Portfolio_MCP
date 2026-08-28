from datetime import UTC, datetime, timedelta
from pathlib import Path

import duckdb
import pytest

from kis_portfolio.platform.migrations import MigrationRunner
from kis_portfolio.services.v2_recovery import export_v2_backup, restore_v2_backup


BASE_TIME = datetime(2026, 8, 28, 1, tzinfo=UTC)


def _seed_reconstruction_ledger(connection: duckdb.DuckDBPyConnection) -> None:
    connection.execute(
        """
        INSERT INTO silver.position_episodes(
            episode_id,account_id,opening_instrument_id,opened_at,identity_hash,first_run_id
        ) VALUES ('episode-1','account-1','instrument-1',?,'episode-hash-1','run-1')
        """,
        [BASE_TIME - timedelta(days=30)],
    )
    for revision, status, current_quantity, knowledge_at in (
        (1, "inferred_opening", 5, BASE_TIME),
        (2, "reconstructed", 7, BASE_TIME + timedelta(hours=1)),
    ):
        connection.execute(
            """
            INSERT INTO silver.position_episode_revisions(
                position_episode_revision_id,episode_id,revision,instrument_id,episode_status,
                reconstruction_start_at,reconstruction_cutoff_at,knowledge_at,current_quantity,
                replayed_quantity,inferred_opening_quantity,evidence_provenance,
                reconstruction_status,coverage_quality_result_id,blockers,provenance
            ) VALUES (?,?,?,?,'open',?,?,?,?,?,?,?,?,'coverage-1','[]','{}')
            """,
            [
                f"episode-revision-{revision}", "episode-1", revision, "instrument-1",
                BASE_TIME - timedelta(days=30), BASE_TIME + timedelta(days=1), knowledge_at,
                current_quantity, current_quantity,
                5 if revision == 1 else None,
                "inferred_opening" if revision == 1 else "actual", status,
            ],
        )

    connection.execute(
        """
        INSERT INTO silver.purchase_lot_identities(
            lot_id,episode_id,account_id,opening_instrument_id,opening_trade_event_id,
            opened_at,evidence_provenance,identity_hash,first_run_id
        ) VALUES ('lot-1','episode-1','account-1','instrument-1','trade-buy-1',?,
                  'actual','lot-hash-1','run-1')
        """,
        [BASE_TIME - timedelta(days=20)],
    )
    for revision, remaining, knowledge_at, cause_type, cause_ref in (
        (1, 7, BASE_TIME, "buy_trade", "trade-buy-1"),
        (2, 3, BASE_TIME + timedelta(hours=2), "sell_allocation", "allocation-1|1"),
    ):
        connection.execute(
            """
            INSERT INTO silver.purchase_lot_revisions(
                purchase_lot_revision_id,lot_id,revision,revision_hash,effective_quantity,
                remaining_quantity,effective_unit_cost,currency,reconstruction_status,
                effective_at,knowledge_at,cause_type,cause_ref,quality_status,blockers,provenance
            ) VALUES (?,?,?,?,7,?,100,'KRW','reconstructed',?,?,?,?,'pass','[]','{}')
            """,
            [
                f"lot-revision-{revision}", "lot-1", revision, f"lot-revision-hash-{revision}",
                remaining, knowledge_at, knowledge_at, cause_type, cause_ref,
            ],
        )

    connection.execute(
        """
        INSERT INTO silver.sell_allocation_sets(
            allocation_id,revision,revision_hash,sell_trade_event_id,account_id,instrument_id,
            episode_id,allocation_method,requested_quantity,allocated_quantity,
            unallocated_quantity,allocation_status,knowledge_at,created_by,reason,blockers,provenance
        ) VALUES ('allocation-1',1,'allocation-hash-1','trade-sell-1','account-1','instrument-1',
                  'episode-1','inferred_fifo',4,4,0,'complete',?,'system','initial FIFO','[]','{}')
        """,
        [BASE_TIME + timedelta(hours=2)],
    )
    connection.execute(
        """
        INSERT INTO silver.sell_allocation_revisions(
            allocation_id,revision,sell_trade_event_id,lot_id,allocated_quantity,
            allocation_method,quality_status,created_at
        ) VALUES ('allocation-1',1,'trade-sell-1','lot-1',4,'inferred_fifo','inferred',?)
        """,
        [BASE_TIME + timedelta(hours=2)],
    )

    connection.execute(
        """
        INSERT INTO control.reconstruction_exceptions(
            exception_id,partition_key,episode_id,exception_type,identity_hash,
            first_run_id,first_seen_at
        ) VALUES ('exception-1','partition-hash-1','episode-1','source_gap',
                  'exception-hash-1','run-1',?)
        """,
        [BASE_TIME],
    )
    connection.execute(
        """
        INSERT INTO control.reconstruction_exception_revisions(
            reconstruction_exception_revision_id,exception_id,revision,exception_status,
            reason,evidence_refs,knowledge_at,resolution_ref,provenance
        ) VALUES
          ('exception-revision-1','exception-1',1,'open','source gap','[]',?,NULL,'{}'),
          ('exception-revision-2','exception-1',2,'resolved','later source evidence','[]',?,
           'trade-revision-2','{}')
        """,
        [BASE_TIME, BASE_TIME + timedelta(hours=3)],
    )


def test_reconstruction_schema_preserves_whole_revisions_and_latest_views() -> None:
    connection = duckdb.connect(":memory:")
    MigrationRunner(connection).apply()
    _seed_reconstruction_ledger(connection)

    assert connection.execute(
        "SELECT revision,reconstruction_status,current_quantity FROM silver.position_episodes_current"
    ).fetchone() == (2, "reconstructed", 7)
    assert connection.execute(
        "SELECT revision,instrument_id,remaining_quantity,cause_type "
        "FROM silver.purchase_lot_states_current"
    ).fetchone() == (2, "instrument-1", 3, "sell_allocation")
    assert connection.execute(
        "SELECT revision,lot_id,lot_allocated_quantity FROM silver.sell_allocations_current"
    ).fetchone() == (1, "lot-1", 4)
    assert connection.execute(
        "SELECT revision,exception_status,resolution_ref FROM control.reconstruction_exceptions_current"
    ).fetchone() == (2, "resolved", "trade-revision-2")
    connection.close()


def test_reconstruction_schema_rejects_invalid_lot_and_allocation_states() -> None:
    connection = duckdb.connect(":memory:")
    MigrationRunner(connection).apply()

    with pytest.raises(duckdb.ConstraintException):
        connection.execute(
            """
            INSERT INTO silver.purchase_lot_identities(
                lot_id,episode_id,account_id,opening_instrument_id,opening_trade_event_id,
                opened_at,evidence_provenance,identity_hash,first_run_id
            ) VALUES ('lot-invalid','episode-1','account-1','instrument-1',NULL,?,
                      'actual','lot-invalid-hash','run-1')
            """,
            [BASE_TIME],
        )

    with pytest.raises(duckdb.ConstraintException):
        connection.execute(
            """
            INSERT INTO silver.sell_allocation_sets(
                allocation_id,revision,revision_hash,sell_trade_event_id,account_id,instrument_id,
                episode_id,allocation_method,requested_quantity,allocated_quantity,
                unallocated_quantity,allocation_status,knowledge_at,created_by,reason,blockers,provenance
            ) VALUES ('bad-allocation',1,'bad-hash','sell-1','account-1','instrument-1',
                      'episode-1','inferred_fifo',5,4,2,'reconciliation_exception',?,
                      'system','bad sum','[]','{}')
            """,
            [BASE_TIME],
        )
    connection.close()


def test_reconstruction_ledger_survives_complete_backup_restore(tmp_path: Path) -> None:
    source = duckdb.connect(str(tmp_path / "source.duckdb"))
    MigrationRunner(source).apply()
    _seed_reconstruction_ledger(source)
    backup = tmp_path / "backup"
    manifest = export_v2_backup(source, backup, database="fixture")
    source.close()

    assert manifest["tables"]["silver.position_episode_revisions"]["rows"] == 2
    assert manifest["tables"]["silver.purchase_lot_revisions"]["rows"] == 2
    assert manifest["tables"]["silver.sell_allocation_sets"]["rows"] == 1
    assert manifest["tables"]["control.reconstruction_exception_revisions"]["rows"] == 2

    target = tmp_path / "restored.duckdb"
    result = restore_v2_backup(backup, target)
    assert result["status"] == "verified"
    restored = duckdb.connect(str(target), read_only=True)
    assert restored.execute(
        "SELECT reconstruction_status FROM silver.position_episodes_current"
    ).fetchone()[0] == "reconstructed"
    assert restored.execute(
        "SELECT remaining_quantity FROM silver.purchase_lot_states_current"
    ).fetchone()[0] == 3
    assert restored.execute(
        "SELECT exception_status FROM control.reconstruction_exceptions_current"
    ).fetchone()[0] == "resolved"
    restored.close()
