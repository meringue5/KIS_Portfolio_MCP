from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import duckdb
import pytest

from kis_portfolio.adapters.outbound.thread_risk_review_warehouse import (
    OwnerIntentAuthorizationError,
    OwnerIntentConcurrencyError,
    ThreadRiskReviewWarehouse,
    inspect_thread_review_readiness,
)
from kis_portfolio.db.catalog import v2_backup_table_names, v2_object_by_qualified_name
from kis_portfolio.modules.portfolio.thread_risk import (
    ReviewStatus,
    RiskPlanAuthority,
    ThreadRiskPlanDraft,
)
from kis_portfolio.platform.migrations import MigrationRunner
from kis_portfolio.services.v2_recovery import export_v2_backup, restore_v2_backup


BASE_TIME = datetime(2026, 8, 28, 1, tzinfo=UTC)


def _connection() -> duckdb.DuckDBPyConnection:
    connection = duckdb.connect(":memory:")
    MigrationRunner(connection).apply()
    return connection


def _seed_thread_and_allocation(connection: duckdb.DuckDBPyConnection) -> None:
    connection.execute(
        """
        INSERT INTO silver.trade_threads(
            thread_id,account_id,instrument_id,opened_at,closed_at,title,status,revision,provenance
        ) VALUES ('thread-1','account-1','instrument-1',?,NULL,'owner thread','open',1,'{}')
        """,
        [BASE_TIME - timedelta(days=30)],
    )
    connection.execute(
        """
        INSERT INTO silver.sell_allocation_sets(
            allocation_id,revision,revision_hash,sell_trade_event_id,account_id,instrument_id,
            episode_id,allocation_method,requested_quantity,allocated_quantity,
            unallocated_quantity,allocation_status,knowledge_at,created_by,reason,blockers,provenance
        ) VALUES ('allocation-1',1,'allocation-hash','sell-1','account-1','instrument-1',
                  'episode-1','inferred_fifo',2,2,0,'complete',?,'system','fixture','[]','{}')
        """,
        [BASE_TIME],
    )


def _draft(*, knowledge_at: datetime, reference: str = "100", stop: str = "90") -> ThreadRiskPlanDraft:
    return ThreadRiskPlanDraft(
        thread_id="thread-1",
        reference_price=Decimal(reference),
        stop_price=Decimal(stop),
        currency="krw",
        risk_budget_ratio=Decimal("0.02"),
        effective_at=BASE_TIME,
        knowledge_at=knowledge_at,
        authority_source=RiskPlanAuthority.OWNER_CONFIRMED,
        advice_metadata={"atr_2n_suggested_stop": "88", "authoritative": False},
        provenance={"channel": "owner-review-fixture"},
    )


def test_contract_rejects_invalid_long_stop_and_risk_budget() -> None:
    with pytest.raises(ValueError, match="below reference_price"):
        _draft(knowledge_at=BASE_TIME, stop="100")
    with pytest.raises(ValueError, match="no greater than 0.02"):
        ThreadRiskPlanDraft(
            thread_id="thread-1",
            reference_price=Decimal("100"),
            stop_price=Decimal("90"),
            currency="KRW",
            risk_budget_ratio=Decimal("0.021"),
            effective_at=BASE_TIME,
            knowledge_at=BASE_TIME,
        )


def test_owner_plan_is_point_in_time_immutable_and_optimistically_versioned() -> None:
    connection = _connection()
    _seed_thread_and_allocation(connection)
    repository = ThreadRiskReviewWarehouse(connection)
    first_at = BASE_TIME + timedelta(hours=1)

    with pytest.raises(OwnerIntentAuthorizationError):
        repository.append_risk_plan(
            _draft(knowledge_at=first_at), expected_prior_revision=0, actor_type="assistant"
        )
    assert connection.execute(
        "SELECT count(*) FROM silver.trade_thread_risk_plan_revisions"
    ).fetchone()[0] == 0

    first = repository.append_risk_plan(
        _draft(knowledge_at=first_at), expected_prior_revision=0, actor_type="owner"
    )
    assert first.inserted is True
    assert first.revision == 1
    assert repository.risk_plan_as_of(
        thread_id="thread-1", evaluation_at=first_at - timedelta(seconds=1)
    ) is None
    selected = repository.risk_plan_as_of(thread_id="thread-1", evaluation_at=first_at)
    assert selected is not None
    assert selected["reference_price"] == Decimal("100.00000000")
    assert selected["stop_price"] == Decimal("90.00000000")
    assert selected["authored_by"] == "owner"
    assert selected["authority_source"] == "owner_confirmed"

    replay = repository.append_risk_plan(
        _draft(knowledge_at=first_at), expected_prior_revision=0, actor_type="owner"
    )
    assert replay.inserted is False
    assert replay.risk_plan_revision_id == first.risk_plan_revision_id

    second_at = first_at + timedelta(hours=1)
    second = repository.append_risk_plan(
        _draft(knowledge_at=second_at, reference="105", stop="92"),
        expected_prior_revision=1,
        actor_type="owner",
    )
    assert second.revision == 2
    assert repository.risk_plan_as_of(thread_id="thread-1", evaluation_at=first_at)["revision"] == 1
    assert repository.risk_plan_as_of(thread_id="thread-1", evaluation_at=second_at)["revision"] == 2
    with pytest.raises(OwnerIntentConcurrencyError):
        repository.append_risk_plan(
            _draft(knowledge_at=second_at + timedelta(hours=1), reference="106", stop="93"),
            expected_prior_revision=1,
            actor_type="owner",
        )
    connection.close()


def test_review_discovery_keeps_missing_intent_open_and_owner_resolution_is_audited() -> None:
    connection = _connection()
    _seed_thread_and_allocation(connection)
    repository = ThreadRiskReviewWarehouse(connection)
    opened = repository.discover_review_items(knowledge_at=BASE_TIME)
    assert len(opened) == 3
    assert repository.discover_review_items(knowledge_at=BASE_TIME + timedelta(minutes=1)) == ()
    assert connection.execute(
        "SELECT count(*) FROM silver.trade_thread_risk_plan_revisions"
    ).fetchone()[0] == 0

    open_items = repository.reviews_as_of(evaluation_at=BASE_TIME, status=ReviewStatus.OPEN)
    assert {item["review_type"] for item in open_items} == {
        "missing_thread_risk_plan",
        "missing_trade_journal",
        "sell_allocation_confirmation",
    }
    plan = repository.append_risk_plan(
        _draft(knowledge_at=BASE_TIME + timedelta(hours=1)),
        expected_prior_revision=0,
        actor_type="owner",
    )
    current = repository.reviews_as_of(evaluation_at=BASE_TIME + timedelta(hours=1))
    by_type = {item["review_type"]: item for item in current}
    assert by_type["missing_thread_risk_plan"]["review_status"] == "answered"
    assert plan.risk_plan_revision_id in by_type["missing_thread_risk_plan"]["resolution_ref"]
    assert by_type["missing_trade_journal"]["review_status"] == "open"
    assert by_type["sell_allocation_confirmation"]["review_status"] == "open"

    allocation_review = by_type["sell_allocation_confirmation"]
    with pytest.raises(OwnerIntentAuthorizationError):
        repository.resolve_review_item(
            allocation_review["review_item_id"],
            status=ReviewStatus.ANSWERED,
            resolution_ref="silver.sell_allocation_sets:allocation-1:2",
            knowledge_at=BASE_TIME + timedelta(hours=2),
            expected_prior_revision=1,
            actor_type="system",
        )
    repository.resolve_review_item(
        allocation_review["review_item_id"],
        status=ReviewStatus.ANSWERED,
        resolution_ref="silver.sell_allocation_sets:allocation-1:2",
        knowledge_at=BASE_TIME + timedelta(hours=2),
        expected_prior_revision=1,
        actor_type="owner",
    )
    with pytest.raises(OwnerIntentConcurrencyError):
        repository.resolve_review_item(
            allocation_review["review_item_id"],
            status=ReviewStatus.DISMISSED,
            resolution_ref="owner-dismissal:stale",
            knowledge_at=BASE_TIME + timedelta(hours=3),
            expected_prior_revision=1,
            actor_type="owner",
        )
    connection.close()


def test_thread_risk_and_review_ledgers_survive_complete_backup_restore(tmp_path: Path) -> None:
    source = duckdb.connect(str(tmp_path / "source.duckdb"))
    MigrationRunner(source).apply()
    _seed_thread_and_allocation(source)
    repository = ThreadRiskReviewWarehouse(source)
    repository.discover_review_items(knowledge_at=BASE_TIME)
    repository.append_risk_plan(
        _draft(knowledge_at=BASE_TIME + timedelta(hours=1)),
        expected_prior_revision=0,
        actor_type="owner",
    )
    backup = tmp_path / "backup"
    manifest = export_v2_backup(source, backup, database="fixture")
    source.close()

    assert "silver.trade_thread_risk_plan_revisions" in v2_backup_table_names()
    assert "control.owner_review_items" in v2_backup_table_names()
    assert "control.owner_review_item_revisions" in v2_backup_table_names()
    assert manifest["tables"]["silver.trade_thread_risk_plan_revisions"]["rows"] == 1
    assert manifest["tables"]["control.owner_review_item_revisions"]["rows"] == 4
    catalog = v2_object_by_qualified_name()
    assert catalog["silver.trade_thread_risk_plans_current"].object_type == "view"
    assert catalog["control.owner_review_items_current"].object_type == "view"

    target = tmp_path / "restored.duckdb"
    restored = restore_v2_backup(backup, target)
    assert restored["status"] == "verified"
    check = duckdb.connect(str(target), read_only=True)
    assert check.execute(
        "SELECT revision,stop_price FROM silver.trade_thread_risk_plans_current"
    ).fetchone() == (1, Decimal("90.00000000"))
    assert check.execute(
        "SELECT count(*) FROM control.owner_review_items_current WHERE review_status='open'"
    ).fetchone()[0] == 2
    check.close()


def test_readiness_inspection_is_aggregate_only_and_has_no_side_effects() -> None:
    connection = _connection()
    _seed_thread_and_allocation(connection)
    report = inspect_thread_review_readiness(connection)
    assert report["status"] == "ready"
    assert report["target_objects"] == {"expected": 5, "present": 5, "missing_count": 0}
    assert report["threads"] == {"rows": 1, "open": 1}
    assert report["sell_allocations"]["inferred_fifo"] == 1
    assert report["new_ledger_rows"] == {"risk_plan_revisions": 0, "review_item_revisions": 0}
    assert report["side_effects"] == "none"
    serialized = str(report)
    assert "thread-1" not in serialized
    assert "account-1" not in serialized
    assert connection.execute(
        "SELECT count(*) FROM control.owner_review_items"
    ).fetchone()[0] == 0
    connection.execute("DELETE FROM silver.sell_allocation_sets")
    empty_allocation_report = inspect_thread_review_readiness(connection)
    assert empty_allocation_report["sell_allocations"] == {
        "current_sets": 0,
        "inferred_fifo": 0,
        "reconciliation_exception": 0,
    }
    connection.close()
