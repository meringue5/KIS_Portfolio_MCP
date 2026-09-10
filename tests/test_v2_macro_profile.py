from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import duckdb
import pytest

from kis_portfolio.adapters.outbound.macro_fixtures import (
    normalize_ecos_fixture,
    normalize_fred_fixture,
)
from kis_portfolio.adapters.outbound.macro_warehouse import MacroWarehouseRepository
from kis_portfolio.platform.macro_registry import load_macro_series_registry
from kis_portfolio.platform.migrations import MigrationRunner
from kis_portfolio.services.macro_profile import (
    BRONZE_STOP_BYTES,
    MacroCallPlan,
    period_delta,
    publish_partition_watermark,
    quarterly_annualized_growth,
    record_partition_quality,
    require_production_activation,
    validate_call_plan,
    validate_capacity,
    vix_regime,
    yield_curve_state,
    yoy_percent_change,
)
from kis_portfolio.services.v2_recovery import export_v2_backup, restore_v2_backup


FIXTURES = Path(__file__).parent / "fixtures" / "v2"


def _fixture(name: str) -> dict[str, object]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@pytest.fixture
def warehouse(tmp_path: Path):
    connection = duckdb.connect(str(tmp_path / "macro.duckdb"))
    MigrationRunner(connection).apply()
    registry = load_macro_series_registry()
    assert registry.project(connection) == 17
    yield connection, registry, MacroWarehouseRepository(connection)
    connection.close()


def test_registry_is_exact_inactive_and_projection_is_immutable(warehouse) -> None:
    connection, registry, _ = warehouse
    assert len(registry.definitions) == 17
    assert {item.source_id for item in registry.definitions} == {
        "source.bok-ecos",
        "source.fred-alfred",
    }
    assert all(item.activation_state == "inactive" for item in registry.definitions)
    assert len(registry.definition_set_hash) == 64
    assert registry.project(connection) == 17
    assert connection.execute(
        "SELECT count(*) FROM control.macro_series_definitions"
    ).fetchone()[0] == 17
    with pytest.raises(RuntimeError, match="production gate"):
        require_production_activation(registry.get("macro.us.effective-fed-funds"))
    with pytest.raises(ValueError, match="not in the exact profile"):
        registry.get("macro.unapproved")


def test_fred_vintages_support_both_labeled_as_of_clocks(warehouse) -> None:
    _, registry, repository = warehouse
    definition = registry.get("macro.us.effective-fed-funds")
    rows = _fixture("macro_fred_synthetic.json")["observations"]
    first = normalize_fred_fixture(
        rows[0],
        definition=definition,
        fetched_at=datetime(2026, 9, 2, 1, tzinfo=UTC),
        knowledge_at=datetime(2026, 9, 2, 1, tzinfo=UTC),
        request_id="fred-fixture-1",
        partition_key="DFF:2026-08",
    )
    revised = normalize_fred_fixture(
        rows[1],
        definition=definition,
        fetched_at=datetime(2026, 9, 6, 1, tzinfo=UTC),
        knowledge_at=datetime(2026, 9, 6, 1, tzinfo=UTC),
        request_id="fred-fixture-2",
        partition_key="DFF:2026-08",
    )
    first_id = repository.record_observation(first, definition=definition)
    assert repository.record_observation(first, definition=definition) == first_id
    revised_id = repository.record_observation(revised, definition=definition)
    assert first_id != revised_id

    system_before = repository.observations_as_of(
        cutoff_at=datetime(2026, 9, 4, tzinfo=UTC),
        series_contract_id=definition.series_contract_id,
    )
    system_after = repository.observations_as_of(
        cutoff_at=datetime(2026, 9, 7, tzinfo=UTC),
        series_contract_id=definition.series_contract_id,
    )
    source_before = repository.observations_as_of(
        cutoff_at=datetime(2026, 9, 4, tzinfo=UTC),
        series_contract_id=definition.series_contract_id,
        query_mode="retrospective_source_as_of",
    )
    assert system_before[0]["native_value"] == Decimal("5.25")
    assert system_after[0]["native_value"] == Decimal("5.24")
    assert source_before[0]["native_value"] == Decimal("5.25")
    assert source_before[0]["query_mode"] == "retrospective_source_as_of"


def test_ecos_observed_content_never_fabricates_source_vintage(warehouse) -> None:
    _, registry, repository = warehouse
    definition = registry.get("macro.kr.cpi-headline")
    rows = _fixture("macro_ecos_synthetic.json")["observations"]
    first = normalize_ecos_fixture(
        rows[0],
        definition=definition,
        fetched_at=datetime(2026, 9, 2, 1, tzinfo=UTC),
        request_id="ecos-fixture-1",
        partition_key="901Y009:2026",
    )
    revised = normalize_ecos_fixture(
        rows[1],
        definition=definition,
        fetched_at=datetime(2026, 9, 6, 1, tzinfo=UTC),
        request_id="ecos-fixture-2",
        partition_key="901Y009:2026",
    )
    repository.record_observation(first, definition=definition)
    repository.record_observation(revised, definition=definition)
    current = repository.observations_as_of(
        cutoff_at=datetime(2026, 9, 7, tzinfo=UTC),
        series_contract_id=definition.series_contract_id,
    )
    retrospective = repository.observations_as_of(
        cutoff_at=datetime(2026, 9, 7, tzinfo=UTC),
        series_contract_id=definition.series_contract_id,
        query_mode="retrospective_source_as_of",
    )
    assert current[0]["native_value"] == Decimal("115.30")
    assert current[0]["source_realtime_start"] is None
    assert current[0]["source_available_at"] is None
    assert retrospective == []
    mismatched = dict(rows[0], unit="percent")
    with pytest.raises(ValueError, match="exact registry"):
        normalize_ecos_fixture(
            mismatched,
            definition=definition,
            fetched_at=datetime(2026, 9, 2, 1, tzinfo=UTC),
            request_id="ecos-invalid",
            partition_key="901Y009:2026",
        )


def test_missing_marker_remains_missing_instead_of_zero(warehouse) -> None:
    _, registry, repository = warehouse
    definition = registry.get("macro.us.effective-fed-funds")
    row = _fixture("macro_fred_synthetic.json")["observations"][2]
    missing = normalize_fred_fixture(
        row,
        definition=definition,
        fetched_at=datetime(2026, 9, 3, tzinfo=UTC),
        knowledge_at=datetime(2026, 9, 3, tzinfo=UTC),
        request_id="fred-missing",
        partition_key="DFF:2026-09",
    )
    repository.record_observation(missing, definition=definition)
    assert missing.native_value is None
    assert missing.missing_reason == "provider_missing"
    assert missing.quality_status == "missing"


def test_five_metrics_have_transparent_boundaries_and_unknowns() -> None:
    assert yoy_percent_change(Decimal("110"), Decimal("100")).value == Decimal("10.0")
    assert yoy_percent_change(Decimal("1"), Decimal("0")).unknown_reason == "zero_denominator"
    assert period_delta(Decimal("5.25"), Decimal("5.50")).value == Decimal("-0.25")
    assert quarterly_annualized_growth(Decimal("102"), Decimal("100")).value == (
        (Decimal("1.02") ** 4) - Decimal(1)
    ) * Decimal(100)
    assert quarterly_annualized_growth(None, Decimal("100")).quality_status == "unknown"
    assert yield_curve_state(Decimal("-0.01")).label == "inverted"
    assert yield_curve_state(Decimal("0")).label == "flat"
    assert yield_curve_state(Decimal("0.01")).label == "positive"
    assert vix_regime(Decimal("19.99")).label == "below_20"
    assert vix_regime(Decimal("20")).label == "20_to_below_30"
    assert vix_regime(Decimal("30")).label == "30_to_below_40"
    assert vix_regime(Decimal("40")).label == "40_or_above"


def test_call_capacity_and_watermark_guardrails_fail_closed(warehouse) -> None:
    connection, _, _ = warehouse
    assert validate_call_plan(
        MacroCallPlan("source.fred-alfred", "routine", {"DFF:2026": 10, "DGS2:2026": 10})
    ).physical_calls == 20
    with pytest.raises(ValueError, match="ten-page"):
        validate_call_plan(MacroCallPlan("source.bok-ecos", "routine", {"722Y001:2026": 11}))
    with pytest.raises(ValueError, match="physical-call budget"):
        validate_call_plan(
            MacroCallPlan("source.bok-ecos", "routine", {"a": 9, "b": 8})
        )
    assert validate_capacity(bronze_bytes=0, silver_rows=0, gold_rows=0) == "pass"
    assert validate_capacity(
        bronze_bytes=(BRONZE_STOP_BYTES * 4 + 4) // 5, silver_rows=0, gold_rows=0
    ) == "review"
    with pytest.raises(ValueError, match="stop line"):
        validate_capacity(bronze_bytes=BRONZE_STOP_BYTES + 1, silver_rows=0, gold_rows=0)

    evaluated_at = datetime(2026, 9, 10, 1, tzinfo=UTC)
    failed_id = record_partition_quality(
        connection,
        run_id="macro-run-1",
        source_id="source.fred-alfred",
        partition_key="DFF:2026",
        rule_id="exact-metadata",
        status="failed",
        observed_value="mismatch",
        expected_value="exact",
        evaluated_at=evaluated_at,
    )
    assert not publish_partition_watermark(
        connection,
        run_id="macro-run-1",
        source_id="source.fred-alfred",
        partition_key="DFF:2026",
        watermark_value="2026-09-10",
        quality_result_id=failed_id,
        observed_at=evaluated_at,
    )
    passed_id = record_partition_quality(
        connection,
        run_id="macro-run-2",
        source_id="source.fred-alfred",
        partition_key="DFF:2026",
        rule_id="exact-metadata",
        status="pass",
        observed_value="exact",
        expected_value="exact",
        evaluated_at=evaluated_at,
    )
    assert publish_partition_watermark(
        connection,
        run_id="macro-run-2",
        source_id="source.fred-alfred",
        partition_key="DFF:2026",
        watermark_value="2026-09-10",
        quality_result_id=passed_id,
        observed_at=evaluated_at,
    )
    with pytest.raises(ValueError, match="backwards"):
        publish_partition_watermark(
            connection,
            run_id="macro-run-2",
            source_id="source.fred-alfred",
            partition_key="DFF:2026",
            watermark_value="2026-09-09",
            quality_result_id=passed_id,
            observed_at=evaluated_at,
        )


def test_profile_snapshot_is_immutable_and_backup_restore_complete(warehouse, tmp_path: Path) -> None:
    connection, registry, repository = warehouse
    evaluation_at = datetime(2026, 9, 10, 1, tzinfo=UTC)
    arguments = {
        "profile_id": "macro_profile_v1",
        "profile_version": "2.0.0",
        "evaluation_at": evaluation_at,
        "metric_set_version": "1.0.0",
        "query_mode": "system_as_of",
        "definition_set_hash": registry.definition_set_hash,
        "series_revision_lineage": [],
        "metric_values": [{"metric_id": "metric.macro-vix-regime", "label": "below_20"}],
        "missing_coverage": [],
        "rights_summary": {"status": "allowed"},
        "attribution": ["Synthetic fixture only"],
        "quality_status": "pass",
    }
    snapshot_id = repository.record_profile_snapshot(**arguments)
    assert repository.record_profile_snapshot(**arguments) == snapshot_id
    with pytest.raises(ValueError, match="immutable evaluation key"):
        repository.record_profile_snapshot(**(arguments | {"quality_status": "partial"}))

    backup = tmp_path / "backup"
    manifest = export_v2_backup(connection, backup, database="macro-fixture")
    assert {"control.macro_series_definitions", "gold.macro_profile_snapshots"} <= set(
        manifest["tables"]
    )
    target = tmp_path / "restored.duckdb"
    restore_v2_backup(backup, target)
    restored = duckdb.connect(str(target), read_only=True)
    assert restored.execute("SELECT count(*) FROM control.macro_series_definitions").fetchone()[0] == 17
    assert restored.execute("SELECT count(*) FROM gold.macro_profile_snapshots").fetchone()[0] == 1
    assert restored.execute("SELECT count(*) FROM silver.macro_observations_current").fetchone()[0] == 0
    restored.close()
