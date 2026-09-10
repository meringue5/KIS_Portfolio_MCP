from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import duckdb
import pytest

from kis_portfolio.adapters.outbound.dividend_fixtures import (
    normalize_action_fixture,
    normalize_entitlement_fixture,
)
from kis_portfolio.adapters.outbound.dividend_warehouse import DividendWarehouseRepository
from kis_portfolio.adapters.outbound.v2_warehouse import V2WarehouseRepository
from kis_portfolio.modules.market.dividends import (
    CashAmountComponentRevision,
    DividendReceiptLinkRevision,
)
from kis_portfolio.platform.migrations import MigrationRunner
from kis_portfolio.ports.object_store import StoredObject
from kis_portfolio.ports.source import SourceEnvelope
from kis_portfolio.services.dividend_ledger import (
    DividendCallPlan,
    publish_partition_watermark,
    record_partition_quality,
    validate_call_plan,
    validate_capacity,
)
from kis_portfolio.services.v2_recovery import export_v2_backup, restore_v2_backup


BASE = datetime(2026, 9, 10, 3, tzinfo=UTC)


def _connection() -> duckdb.DuckDBPyConnection:
    connection = duckdb.connect(":memory:")
    MigrationRunner(connection).apply()
    return connection


def _observation(
    connection: duckdb.DuckDBPyConnection,
    dataset_id: str,
    source_record_id: str,
    payload: dict,
    *,
    source_id: str = "source.kis-open-api",
    at: datetime = BASE,
) -> str:
    content_hash = hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str).encode()
    ).hexdigest()
    return V2WarehouseRepository(connection).record_observation(
        dataset_id,
        SourceEnvelope(source_id, source_record_id, at, at, payload, content_hash),
        "dividend-fixture-run",
    )


def _foundation(connection: duckdb.DuckDBPyConnection) -> tuple[str, str, str]:
    observation_id = _observation(
        connection,
        "dataset.dividend-source-observation",
        "KR-ACTION-2026-Q3",
        {"fixture": "dividend action"},
    )
    warehouse = V2WarehouseRepository(connection)
    content_hash = connection.execute(
        "SELECT content_hash FROM bronze.source_observations WHERE observation_id=?",
        [observation_id],
    ).fetchone()[0]
    DividendWarehouseRepository(connection).record_source_manifest(
        observation_id=observation_id,
        stored=StoredObject(
            f"fixture-private://dividends/{content_hash}", content_hash, 64,
            "application/json", True,
        ),
        metadata={"fixture": True},
    )
    warehouse.upsert_account({
        "account_id": "account-fixture-a",
        "account_label": "fixture-a",
        "account_type": "brokerage",
        "base_currency": "KRW",
        "as_of": BASE,
    }, observation_id)
    warehouse.upsert_instrument({
        "instrument_id": "instrument-fixture-a",
        "market": "KRX",
        "symbol": "000001",
        "name": "Fixture Equity",
        "asset_type": "equity",
        "currency": "KRW",
        "issuer_id": "issuer-fixture-a",
        "as_of": BASE,
        "classification_quality": "fixture",
    }, observation_id)
    action = normalize_action_fixture({
        "source_action_id": "KR-ACTION-2026-Q3",
        "amount_per_share": "100",
        "currency": "KRW",
        "declaration_date": "20260801",
        "record_date": "20260831",
        "payable_date": "20260910",
    }, source_id="source.kis-open-api", jurisdiction="KR",
       issuer_id="issuer-fixture-a", instrument_id="instrument-fixture-a",
       observed_at=BASE, fetched_at=BASE)
    action_id, revision_id = DividendWarehouseRepository(connection).record_action(
        action, observation_id=observation_id
    )
    return observation_id, action_id, revision_id


def _cash(
    connection: duckdb.DuckDBPyConnection,
    *,
    source_record_id: str = "CASH-DIV-1",
    amount: str = "85",
    event_type: str = "dividend",
    at: datetime = BASE + timedelta(hours=1),
) -> tuple[str, str]:
    observation_id = _observation(
        connection,
        "dataset.cash-transaction-event",
        source_record_id,
        {"fixture": "cash receipt", "amount": amount},
        at=at,
    )
    cash_id = V2WarehouseRepository(connection).record_cash_flow({
        "account_id": "account-fixture-a",
        "event_type": event_type,
        "effective_at": at,
        "settled_at": at,
        "amount": Decimal(amount),
        "currency": "KRW",
        "source_record_id": source_record_id,
        "knowledge_at": at,
        "classification_source": "source",
        "link_quality": "unmatched",
        "quality_status": "pass",
        "provenance": {"fixture": True},
    }, observation_id)
    return observation_id, cash_id


def test_dividend_ledgers_preserve_cash_ssot_and_system_as_of_reversal() -> None:
    connection = _connection()
    observation_id, action_id, _ = _foundation(connection)
    repository = DividendWarehouseRepository(connection)
    entitlement = normalize_entitlement_fixture({
        "basis": "source_confirmed",
        "coverage_status": "source_confirmed",
        "eligibility_date": "20260831",
        "eligible_quantity": "1",
        "rate_per_share": "100",
        "expected_gross": "100",
        "expected_tax": "-15",
        "expected_net": "85",
        "currency": "KRW",
    }, dividend_action_id=action_id, account_id="account-fixture-a",
       knowledge_at=BASE + timedelta(minutes=10), source_observation_id=observation_id)
    entitlement_id, entitlement_revision_id = repository.record_entitlement(entitlement)
    assert repository.record_entitlement(entitlement) == (entitlement_id, entitlement_revision_id)

    cash_observation_id, cash_id = _cash(connection)
    for component_type, amount in (("gross", "100"), ("tax", "-15"), ("net", "85")):
        component = CashAmountComponentRevision(
            cash_flow_event_id=cash_id,
            component_type=component_type,
            amount=Decimal(amount),
            currency="KRW",
            source_id="source.kis-open-api",
            source_observation_id=cash_observation_id,
            knowledge_at=BASE + timedelta(hours=1),
            provenance={"fixture": True},
        )
        assert repository.record_cash_component(component) == repository.record_cash_component(component)

    link = DividendReceiptLinkRevision(
        dividend_action_id=action_id,
        dividend_entitlement_id=entitlement_id,
        cash_flow_event_id=cash_id,
        relation_key="fixture-link-1",
        link_status="exact",
        allocated_receipt_amount=Decimal("85"),
        currency="KRW",
        reason="exact source reference",
        rule_version="fixture-v1",
        knowledge_at=BASE + timedelta(hours=1),
        provenance={"fixture": True},
    )
    link_id, link_revision_id = repository.record_receipt_link(link)
    before = repository.monthly_native_as_of(cutoff_at=BASE + timedelta(hours=2))
    assert before[0]["received_cash_amount"] == Decimal("85.00000000")
    assert before[0]["sourced_gross_amount"] == Decimal("100.00000000")
    assert before[0]["sourced_tax_amount"] == Decimal("-15.00000000")
    assert before[0]["sourced_net_amount"] == Decimal("85.00000000")
    assert before[0]["component_coverage"] == "complete"
    assert before[0]["reconciliation_coverage"] == "complete"
    assert connection.execute(
        "SELECT amount FROM silver.cash_flow_events WHERE cash_flow_event_id=?", [cash_id]
    ).fetchone() == (Decimal("85.00000000"),)

    repository.record_receipt_link(DividendReceiptLinkRevision(
        dividend_action_id=action_id,
        dividend_entitlement_id=entitlement_id,
        cash_flow_event_id=cash_id,
        relation_key="fixture-link-1",
        link_status="reversed",
        allocated_receipt_amount=Decimal("85"),
        currency="KRW",
        reason="later statement disproved the action link",
        rule_version="fixture-v1",
        knowledge_at=BASE + timedelta(hours=3),
        correction_target_revision_id=link_revision_id,
        provenance={"fixture": True},
    ))
    assert repository.monthly_native_as_of(cutoff_at=BASE + timedelta(hours=2)) == before
    assert repository.monthly_native_as_of(cutoff_at=BASE + timedelta(hours=4)) == []
    assert connection.execute("SELECT count(*) FROM gold.dividend_monthly_native").fetchone()[0] == 0
    assert repository.receipt_links_as_of(cutoff_at=BASE + timedelta(hours=2))[0]["link_status"] == "exact"
    assert repository.receipt_links_as_of(cutoff_at=BASE + timedelta(hours=4))[0]["link_status"] == "reversed"
    assert link_id
    connection.close()


def test_dividend_gaps_and_cash_links_fail_closed() -> None:
    connection = _connection()
    _, action_id, _ = _foundation(connection)
    repository = DividendWarehouseRepository(connection)
    with pytest.raises(ValueError, match="cannot invent"):
        repository.record_entitlement(normalize_entitlement_fixture({
            "basis": "manual",
            "coverage_status": "source_gap",
            "expected_net": "1",
        }, dividend_action_id=action_id, account_id="account-fixture-a", knowledge_at=BASE))
    gap = normalize_entitlement_fixture({
        "basis": "manual", "coverage_status": "source_gap",
    }, dividend_action_id=action_id, account_id="account-fixture-a", knowledge_at=BASE)
    gap_id, _ = repository.record_entitlement(gap)
    _, tax_cash_id = _cash(connection, source_record_id="NOT-DIVIDEND", event_type="tax")
    with pytest.raises(ValueError, match="dividend-classified"):
        repository.record_receipt_link(DividendReceiptLinkRevision(
            dividend_action_id=action_id,
            dividend_entitlement_id=gap_id,
            cash_flow_event_id=tax_cash_id,
            relation_key="bad-tax-link",
            link_status="candidate",
            reason="fixture proximity only",
            rule_version="fixture-v1",
            knowledge_at=BASE + timedelta(hours=2),
        ))
    repository.record_receipt_link(DividendReceiptLinkRevision(
        dividend_action_id=action_id,
        dividend_entitlement_id=gap_id,
        relation_key="explicit-gap",
        link_status="source_gap",
        reason="IRP actual receipt source unavailable",
        rule_version="fixture-v1",
        knowledge_at=BASE + timedelta(hours=2),
        quality_status="partial",
    ))
    assert repository.receipt_links_as_of(cutoff_at=BASE + timedelta(hours=3))[0]["link_status"] == "source_gap"

    _, dividend_cash_id = _cash(
        connection, source_record_id="UNALLOCATED-DIVIDEND", event_type="dividend"
    )
    repository.record_receipt_link(DividendReceiptLinkRevision(
        dividend_action_id=action_id,
        cash_flow_event_id=dividend_cash_id,
        relation_key="unallocated-link",
        link_status="exact",
        reason="single action exact source reference",
        rule_version="fixture-v1",
        knowledge_at=BASE + timedelta(hours=2),
    ))
    with pytest.raises(ValueError, match="explicit allocation"):
        repository.record_receipt_link(DividendReceiptLinkRevision(
            dividend_action_id=action_id,
            cash_flow_event_id=dividend_cash_id,
            relation_key="second-link",
            link_status="reconciled",
            allocated_receipt_amount=Decimal("1"),
            currency="KRW",
            reason="would double count an unallocated cash fact",
            rule_version="fixture-v1",
            knowledge_at=BASE + timedelta(hours=2),
        ))
    connection.close()


def test_dividend_silver_publish_requires_private_hash_verified_source() -> None:
    connection = _connection()
    observation_id = _observation(
        connection,
        "dataset.dividend-source-observation",
        "UNVERIFIED-ACTION",
        {"fixture": "unverified action"},
    )
    warehouse = V2WarehouseRepository(connection)
    warehouse.upsert_instrument({
        "instrument_id": "instrument-unverified",
        "market": "KRX",
        "symbol": "000002",
        "name": "Unverified Fixture",
        "asset_type": "equity",
        "currency": "KRW",
        "issuer_id": "issuer-unverified",
        "as_of": BASE,
        "classification_quality": "fixture",
    }, observation_id)
    action = normalize_action_fixture({
        "source_action_id": "UNVERIFIED-ACTION",
        "amount_per_share": "1",
        "currency": "KRW",
    }, source_id="source.kis-open-api", jurisdiction="KR",
       issuer_id="issuer-unverified", instrument_id="instrument-unverified",
       observed_at=BASE, fetched_at=BASE)
    with pytest.raises(ValueError, match="verified private raw object"):
        DividendWarehouseRepository(connection).record_action(action, observation_id=observation_id)
    content_hash = connection.execute(
        "SELECT content_hash FROM bronze.source_observations WHERE observation_id=?", [observation_id]
    ).fetchone()[0]
    with pytest.raises(ValueError, match="credential"):
        DividendWarehouseRepository(connection).record_source_manifest(
            observation_id=observation_id,
            stored=StoredObject(
                "fixture-private://unverified", content_hash, 10, "application/json", True
            ),
            metadata={"nested": {"access_token": "must-not-persist"}},
        )
    connection.close()


def test_dividend_budget_and_capacity_stop_before_execution() -> None:
    plan = DividendCallPlan(
        "routine",
        {"brokerage|KRX|2026-09": 32, "isa|KRX|2026-09": 32},
        {"brokerage|KRX|2026-09": 2, "isa|KRX|2026-09": 1},
    )
    assert validate_call_plan(plan).physical_calls == 64
    assert len(plan.plan_hash) == 64
    with pytest.raises(ValueError, match="physical-call"):
        validate_call_plan(DividendCallPlan("routine", {"x": 65}, {"x": 1}))
    with pytest.raises(ValueError, match="ten-page"):
        validate_call_plan(DividendCallPlan("backfill", {"x": 1}, {"x": 11}))
    validate_capacity(private_object_bytes=1024 * 1024 * 1024, silver_rows=500_000)
    with pytest.raises(ValueError, match="1 GiB"):
        validate_capacity(private_object_bytes=1024 * 1024 * 1024 + 1, silver_rows=0)
    with pytest.raises(ValueError, match="500000"):
        validate_capacity(private_object_bytes=0, silver_rows=500_001)


def test_dividend_watermark_advances_only_after_complete_quality() -> None:
    connection = _connection()
    partition = "brokerage|KRX|2026-09"
    partial = record_partition_quality(
        connection,
        run_id="dividend-partial",
        partition_key=partition,
        status="partial",
        observed_value="1/2",
        expected_value="2/2",
        evaluated_at=BASE,
    )
    assert publish_partition_watermark(
        connection,
        run_id="dividend-partial",
        partition_key=partition,
        watermark_value="2026-09-10",
        quality_result_id=partial,
        observed_at=BASE,
    ) is False
    passed = record_partition_quality(
        connection,
        run_id="dividend-pass",
        partition_key=partition,
        status="pass",
        observed_value="2/2",
        expected_value="2/2",
        evaluated_at=BASE + timedelta(minutes=1),
    )
    assert publish_partition_watermark(
        connection,
        run_id="dividend-pass",
        partition_key=partition,
        watermark_value="2026-09-10",
        quality_result_id=passed,
        observed_at=BASE + timedelta(minutes=1),
    ) is True
    older = record_partition_quality(
        connection,
        run_id="dividend-old",
        partition_key=partition,
        status="pass",
        observed_value="2/2",
        expected_value="2/2",
        evaluated_at=BASE + timedelta(minutes=2),
    )
    with pytest.raises(ValueError, match="cannot move backwards"):
        publish_partition_watermark(
            connection,
            run_id="dividend-old",
            partition_key=partition,
            watermark_value="2026-09-09",
            quality_result_id=older,
            observed_at=BASE + timedelta(minutes=2),
        )
    connection.close()


def test_dividend_tables_round_trip_through_governed_backup(tmp_path: Path) -> None:
    source = duckdb.connect(str(tmp_path / "dividend-source.duckdb"))
    MigrationRunner(source).apply()
    _, action_id, _ = _foundation(source)
    DividendWarehouseRepository(source).record_entitlement(normalize_entitlement_fixture({
        "basis": "manual", "coverage_status": "source_gap",
    }, dividend_action_id=action_id, account_id="account-fixture-a", knowledge_at=BASE))
    backup = tmp_path / "backup"
    manifest = export_v2_backup(source, backup, database="fixture")
    source.close()
    assert manifest["tables"]["silver.dividend_actions"]["rows"] == 1
    assert manifest["tables"]["silver.dividend_entitlement_revisions"]["rows"] == 1
    restored_path = tmp_path / "dividend-restored.duckdb"
    assert restore_v2_backup(backup, restored_path)["status"] == "verified"
    restored = duckdb.connect(str(restored_path), read_only=True)
    assert restored.execute("SELECT count(*) FROM silver.dividend_actions_current").fetchone()[0] == 1
    assert restored.execute("SELECT count(*) FROM silver.dividend_entitlements_current").fetchone()[0] == 1
    restored.close()
