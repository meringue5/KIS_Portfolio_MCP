from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import duckdb
import pytest

from kis_portfolio.adapters.outbound.position_reconstruction_warehouse import (
    PositionReconstructionWarehouseRepository,
    ReconstructionPersistenceError,
)
from kis_portfolio.modules.portfolio.reconstruction import CorporateActionCoverage
from kis_portfolio.platform.migrations import MigrationRunner
from kis_portfolio.services.position_replay import ReplayRequest, ReplayTrade, replay_position
from kis_portfolio.services.v2_recovery import export_v2_backup, restore_v2_backup


START = datetime(2023, 1, 1, tzinfo=UTC)
CUTOFF = datetime(2026, 1, 1, tzinfo=UTC)
INSTRUMENT = "KRX:005930"


def _connection(path: str = ":memory:") -> duckdb.DuckDBPyConnection:
    connection = duckdb.connect(path)
    MigrationRunner(connection).apply()
    return connection


def _request(
    quantity: str,
    coverage: CorporateActionCoverage = CorporateActionCoverage.PASS,
) -> ReplayRequest:
    return ReplayRequest(
        account_id="account-ria",
        target_instrument_id=INSTRUMENT,
        lineage_instrument_ids=(INSTRUMENT,),
        start_at=START,
        cutoff_at=CUTOFF,
        current_quantity=Decimal(quantity),
        corporate_action_coverage=coverage,
        coverage_quality_result_id="quality-actions-20260101",
    )


def _trade(
    event_id: str,
    day: int,
    side: str,
    quantity: str,
    price: str,
) -> ReplayTrade:
    return ReplayTrade(
        trade_event_id=event_id,
        account_id="account-ria",
        instrument_id=INSTRUMENT,
        side=side,
        executed_at=START + timedelta(days=day),
        execution_sequence="1",
        quantity=Decimal(quantity),
        price=Decimal(price),
        currency="KRW",
    )


def _reconciled_fixture():
    request = _request("3")
    plan = replay_position(
        request,
        (
            _trade("buy-a", 1, "buy", "5", "100"),
            _trade("buy-b", 2, "buy", "4", "110"),
            _trade("sell-a", 3, "sell", "6", "120"),
        ),
    )
    return request, plan


def test_persist_reconciled_plan_is_atomic_append_only_and_idempotent() -> None:
    connection = _connection()
    repository = PositionReconstructionWarehouseRepository(connection)
    request, plan = _reconciled_fixture()

    first = repository.persist(
        request=request,
        plan=plan,
        run_id="run-1",
        knowledge_at=CUTOFF + timedelta(hours=1),
    )
    second = repository.persist(
        request=request,
        plan=plan,
        run_id="run-2",
        knowledge_at=CUTOFF + timedelta(hours=2),
    )

    assert first.outcome == "published"
    assert first.episode_identities_inserted == 1
    assert first.episode_revisions_inserted == 1
    assert first.lot_identities_inserted == 2
    assert first.lot_revisions_inserted == 2
    assert first.allocation_revisions_inserted == 1
    assert first.allocation_slices_inserted == 2
    assert second.outcome == "reused"
    assert second.inserted_revision_count == 0
    assert connection.execute("SELECT count(*) FROM silver.position_episode_revisions").fetchone()[0] == 1
    assert connection.execute("SELECT count(*) FROM silver.purchase_lot_revisions").fetchone()[0] == 2
    assert connection.execute("SELECT count(*) FROM silver.sell_allocation_sets").fetchone()[0] == 1
    assert connection.execute("SELECT count(*) FROM silver.sell_allocation_revisions").fetchone()[0] == 2
    assert connection.execute(
        "SELECT sum(remaining_quantity) FROM silver.purchase_lot_states_current"
    ).fetchone()[0] == 3
    connection.close()


def test_changed_governed_inputs_append_new_whole_revisions() -> None:
    connection = _connection()
    repository = PositionReconstructionWarehouseRepository(connection)
    first_request, first_plan = _reconciled_fixture()
    repository.persist(
        request=first_request,
        plan=first_plan,
        run_id="run-1",
        knowledge_at=CUTOFF + timedelta(hours=1),
    )

    second_request = _request("4")
    second_plan = replay_position(
        second_request,
        (
            _trade("buy-a", 1, "buy", "5", "100"),
            _trade("buy-b", 2, "buy", "4", "110"),
            _trade("sell-a", 3, "sell", "6", "120"),
            _trade("buy-c", 4, "buy", "1", "130"),
        ),
    )
    result = repository.persist(
        request=second_request,
        plan=second_plan,
        run_id="run-2",
        knowledge_at=CUTOFF + timedelta(hours=2),
    )

    assert result.outcome == "published"
    assert connection.execute(
        "SELECT max(revision),current_quantity FROM silver.position_episodes_current GROUP BY current_quantity"
    ).fetchone() == (2, Decimal("4"))
    assert connection.execute(
        "SELECT max(revision) FROM silver.sell_allocation_sets"
    ).fetchone()[0] == 2
    assert connection.execute(
        "SELECT count(*) FROM silver.purchase_lot_identities"
    ).fetchone()[0] == 3
    connection.close()


def test_blocked_plan_records_control_exception_and_passing_plan_resolves_it() -> None:
    connection = _connection()
    repository = PositionReconstructionWarehouseRepository(connection)
    blocked_request = _request("0", CorporateActionCoverage.NOT_ASSESSED)
    blocked_plan = replay_position(blocked_request, ())

    blocked = repository.persist(
        request=blocked_request,
        plan=blocked_plan,
        run_id="run-blocked",
        knowledge_at=CUTOFF + timedelta(hours=1),
    )

    assert blocked.outcome == "exception_recorded"
    assert connection.execute(
        "SELECT exception_status FROM control.reconstruction_exceptions_current"
    ).fetchone()[0] == "open"
    assert connection.execute("SELECT count(*) FROM silver.position_episodes").fetchone()[0] == 0

    repeated = repository.persist(
        request=blocked_request,
        plan=blocked_plan,
        run_id="run-blocked-retry",
        knowledge_at=CUTOFF + timedelta(hours=1, minutes=30),
    )
    assert repeated.outcome == "reused"
    assert repeated.inserted_revision_count == 0

    passing_request = _request("0", CorporateActionCoverage.PASS)
    passing_plan = replay_position(passing_request, ())
    passing = repository.persist(
        request=passing_request,
        plan=passing_plan,
        run_id="run-passing",
        knowledge_at=CUTOFF + timedelta(hours=2),
    )

    assert passing.exceptions_resolved == 1
    assert connection.execute(
        "SELECT revision,exception_status,resolution_ref "
        "FROM control.reconstruction_exceptions_current"
    ).fetchone() == (2, "resolved", passing_plan.replay_hash)
    connection.close()


def test_inferred_opening_persists_without_fabricated_cost() -> None:
    connection = _connection()
    repository = PositionReconstructionWarehouseRepository(connection)
    request = _request("5")
    plan = replay_position(
        request,
        (
            _trade("sell-old", 1, "sell", "10", "90"),
            _trade("buy-new", 2, "buy", "5", "100"),
        ),
    )

    repository.persist(
        request=request,
        plan=plan,
        run_id="run-inferred",
        knowledge_at=CUTOFF + timedelta(hours=1),
    )

    inferred = connection.execute(
        """
        SELECT evidence_provenance,effective_unit_cost,currency,reconstruction_status
        FROM silver.purchase_lot_states_current
        WHERE evidence_provenance='inferred_opening'
        """
    ).fetchone()
    assert inferred == ("inferred_opening", None, "UNKNOWN", "inferred_opening")
    assert connection.execute(
        """
        SELECT reconstruction_status,current_quantity
        FROM silver.position_episodes_current ORDER BY opened_at
        """
    ).fetchall() == [("inferred_opening", Decimal("0")), ("reconstructed", Decimal("5"))]
    connection.close()


def test_slice_conflict_rolls_back_every_new_candidate_row() -> None:
    connection = _connection()
    repository = PositionReconstructionWarehouseRepository(connection)
    request, plan = _reconciled_fixture()
    allocation = plan.allocations[0]
    first_slice = allocation.plan.slices[0]
    connection.execute(
        """
        INSERT INTO silver.sell_allocation_revisions(
            allocation_id,revision,sell_trade_event_id,lot_id,allocated_quantity,
            allocation_method,quality_status,created_at
        ) VALUES (?,?,?,?,?,?,?,?)
        """,
        [allocation.allocation_id, 1, allocation.sell_trade_event_id, first_slice.lot_id,
         first_slice.allocated_quantity, allocation.plan.method.value, "fixture-conflict", CUTOFF],
    )

    with pytest.raises(duckdb.ConstraintException):
        repository.persist(
            request=request,
            plan=plan,
            run_id="run-conflict",
            knowledge_at=CUTOFF + timedelta(hours=1),
        )

    assert connection.execute("SELECT count(*) FROM silver.position_episodes").fetchone()[0] == 0
    assert connection.execute("SELECT count(*) FROM silver.purchase_lot_identities").fetchone()[0] == 0
    assert connection.execute("SELECT count(*) FROM silver.sell_allocation_sets").fetchone()[0] == 0
    assert connection.execute("SELECT count(*) FROM silver.sell_allocation_revisions").fetchone()[0] == 1
    connection.close()


def test_tampered_plan_is_rejected_before_any_warehouse_write() -> None:
    connection = _connection()
    repository = PositionReconstructionWarehouseRepository(connection)
    request, plan = _reconciled_fixture()
    bad_episode = replace(plan.episodes[0], current_quantity=Decimal("99"))
    tampered = replace(plan, episodes=(bad_episode,))

    with pytest.raises(ReconstructionPersistenceError, match="projection hash"):
        repository.persist(
            request=request,
            plan=tampered,
            run_id="run-tampered",
            knowledge_at=CUTOFF + timedelta(hours=1),
        )

    assert connection.execute("SELECT count(*) FROM silver.position_episodes").fetchone()[0] == 0
    connection.close()


def test_persisted_reconstruction_survives_complete_v2_backup_restore(tmp_path: Path) -> None:
    source = _connection(str(tmp_path / "source.duckdb"))
    repository = PositionReconstructionWarehouseRepository(source)
    request, plan = _reconciled_fixture()
    repository.persist(
        request=request,
        plan=plan,
        run_id="run-backup",
        knowledge_at=CUTOFF + timedelta(hours=1),
    )
    backup = tmp_path / "backup"
    manifest = export_v2_backup(source, backup, database="fixture")
    source.close()

    assert manifest["tables"]["silver.position_episode_revisions"]["rows"] == 1
    assert manifest["tables"]["silver.purchase_lot_revisions"]["rows"] == 2
    assert manifest["tables"]["silver.sell_allocation_sets"]["rows"] == 1

    target = tmp_path / "restored.duckdb"
    assert restore_v2_backup(backup, target)["status"] == "verified"
    restored = duckdb.connect(str(target), read_only=True)
    assert restored.execute(
        "SELECT current_quantity FROM silver.position_episodes_current"
    ).fetchone()[0] == 3
    assert restored.execute(
        "SELECT sum(remaining_quantity) FROM silver.purchase_lot_states_current"
    ).fetchone()[0] == 3
    assert restored.execute(
        "SELECT count(*) FROM silver.sell_allocations_current"
    ).fetchone()[0] == 2
    restored.close()
