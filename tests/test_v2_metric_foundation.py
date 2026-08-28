from __future__ import annotations

import json
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import duckdb
import pytest

from kis_portfolio.adapters.outbound.metric_warehouse import (
    MetricValueConflictError,
    MetricWarehouseRepository,
)
from kis_portfolio.db.catalog import v2_backup_table_names
from kis_portfolio.modules.monitoring import (
    FutureMetricInputError,
    MetricDefinition,
    MetricFormulaRegistry,
    MetricInput,
    PointInTimeMetricEngine,
    sum_decimal_inputs,
)
from kis_portfolio.platform.metric_contracts import load_metric_registry
from kis_portfolio.platform.migrations import MigrationRunner


def _engine():
    definitions = load_metric_registry()
    formulas = MetricFormulaRegistry()
    formulas.register("formula.portfolio-value-krw.v1", sum_decimal_inputs)
    return definitions, PointInTimeMetricEngine(definitions, formulas)


def _input(ref: str, value: str, at: datetime) -> MetricInput:
    return MetricInput(
        ref=ref,
        value=Decimal(value),
        effective_at=at,
        knowledge_at=at,
        quality_status="pass",
        lineage_hash=f"hash-{ref}",
    )


def test_governed_metric_contract_evaluates_point_in_time_and_is_idempotent(tmp_path: Path) -> None:
    definitions, engine = _engine()
    definition = definitions.get("metric.portfolio-value-krw", "1.0.0")
    assert definition.point_in_time is True
    evaluation_at = datetime(2026, 8, 28, 7, tzinfo=UTC)
    inputs = (
        _input("gold.portfolio_daily_state:position-a", "730000", evaluation_at - timedelta(minutes=1)),
        _input("gold.portfolio_daily_state:cash-a", "270000", evaluation_at - timedelta(minutes=2)),
    )
    value = engine.evaluate(
        metric_id=definition.metric_id,
        version=definition.version,
        subject_type="portfolio",
        subject_id="owner",
        evaluation_at=evaluation_at,
        evaluation_slot="kr-1600",
        inputs=inputs,
        evaluation_run_id="fixture-metric-run",
    )
    assert value.value == Decimal("1000000")
    assert value.knowledge_cutoff_at == evaluation_at

    con = duckdb.connect(str(tmp_path / "metric.duckdb"))
    MigrationRunner(con).apply()
    repository = MetricWarehouseRepository(con)
    assert repository.write_value(value) is True
    replay = engine.evaluate(
        metric_id=definition.metric_id,
        version=definition.version,
        subject_type="portfolio",
        subject_id="owner",
        evaluation_at=evaluation_at,
        evaluation_slot="kr-1600",
        inputs=inputs,
        evaluation_run_id="fixture-metric-rerun",
    )
    assert repository.write_value(replay) is False
    assert repository.count_values() == 1
    assert con.execute("SELECT count(*) FROM control.metric_definitions").fetchone()[0] == 1
    con.close()


def test_metric_engine_rejects_future_knowledge() -> None:
    definitions, engine = _engine()
    definition = definitions.get("metric.portfolio-value-krw", "1.0.0")
    evaluation_at = datetime(2026, 8, 28, 7, tzinfo=UTC)
    future = _input("future-row", "1", evaluation_at + timedelta(seconds=1))

    with pytest.raises(FutureMetricInputError, match="effective_at"):
        engine.evaluate(
            metric_id=definition.metric_id,
            version=definition.version,
            subject_type="portfolio",
            subject_id="owner",
            evaluation_at=evaluation_at,
            evaluation_slot="kr-1600",
            inputs=(future,),
            evaluation_run_id="future-run",
        )

    knowledge_from_future = MetricInput(
        ref="later-revision",
        value=Decimal("1"),
        effective_at=evaluation_at - timedelta(days=1),
        knowledge_at=evaluation_at + timedelta(seconds=1),
        quality_status="pass",
        lineage_hash="hash-later-revision",
    )
    with pytest.raises(FutureMetricInputError, match="knowledge_at"):
        engine.evaluate(
            metric_id=definition.metric_id,
            version=definition.version,
            subject_type="portfolio",
            subject_id="owner",
            evaluation_at=evaluation_at,
            evaluation_slot="kr-1600",
            inputs=(knowledge_from_future,),
            evaluation_run_id="future-knowledge-run",
        )


def test_metric_repository_rejects_conflicting_replay_and_in_place_definition_change(tmp_path: Path) -> None:
    definitions, engine = _engine()
    definition = definitions.get("metric.portfolio-value-krw", "1.0.0")
    evaluation_at = datetime(2026, 8, 28, 7, tzinfo=UTC)
    first = engine.evaluate(
        metric_id=definition.metric_id,
        version=definition.version,
        subject_type="portfolio",
        subject_id="owner",
        evaluation_at=evaluation_at,
        evaluation_slot="kr-1600",
        inputs=(_input("row-a", "10", evaluation_at),),
        evaluation_run_id="run-a",
    )
    conflicting = engine.evaluate(
        metric_id=definition.metric_id,
        version=definition.version,
        subject_type="portfolio",
        subject_id="owner",
        evaluation_at=evaluation_at,
        evaluation_slot="kr-1600",
        inputs=(_input("row-b", "11", evaluation_at),),
        evaluation_run_id="run-b",
    )
    con = duckdb.connect(str(tmp_path / "conflict.duckdb"))
    MigrationRunner(con).apply()
    repository = MetricWarehouseRepository(con)
    repository.write_value(first)
    with pytest.raises(MetricValueConflictError, match="conflicting value"):
        repository.write_value(conflicting)

    changed_document = dict(definition.document)
    changed_document["unit"] = "CHANGED"
    with pytest.raises(MetricValueConflictError, match="changed in place"):
        repository.register_definition(MetricDefinition.from_document(changed_document))
    con.close()


def test_metric_repository_preserves_unavailable_outcome_without_zero(tmp_path: Path) -> None:
    _, engine = _engine()
    evaluation_at = datetime(2026, 8, 28, 7, tzinfo=UTC)
    unavailable = engine.unavailable(
        metric_id="metric.portfolio-value-krw",
        version="1.0.0",
        subject_type="portfolio",
        subject_id="owner",
        evaluation_at=evaluation_at,
        evaluation_slot="kr-1600",
        quality_status="insufficient_history",
        evaluation_run_id="unavailable-run",
    )
    assert unavailable.value is None
    con = duckdb.connect(str(tmp_path / "unavailable.duckdb"))
    MigrationRunner(con).apply()
    repository = MetricWarehouseRepository(con)
    assert repository.write_value(unavailable) is True
    assert con.execute(
        "SELECT value_decimal, quality_status FROM gold.metric_values"
    ).fetchone() == (None, "insufficient_history")
    con.close()


def test_v2_metric_tables_are_in_a_complete_parquet_restore(tmp_path: Path) -> None:
    qualified_tables = v2_backup_table_names()
    assert "gold.metric_values" in qualified_tables
    assert "control.metric_definitions" in qualified_tables

    source = duckdb.connect(str(tmp_path / "source.duckdb"))
    MigrationRunner(source).apply()
    definitions, engine = _engine()
    evaluation_at = datetime(2026, 8, 28, 7, tzinfo=UTC)
    MetricWarehouseRepository(source).write_value(engine.evaluate(
        metric_id="metric.portfolio-value-krw",
        version="1.0.0",
        subject_type="portfolio",
        subject_id="owner",
        evaluation_at=evaluation_at,
        evaluation_slot="kr-1600",
        inputs=(_input("round-trip-row", "123", evaluation_at),),
        evaluation_run_id="round-trip-run",
    ))
    backup_dir = tmp_path / "backup"
    backup_dir.mkdir()
    manifest: dict[str, object] = {
        "manifest_version": 2,
        "tables": {},
        "object_bytes_included": False,
    }
    for qualified in qualified_tables:
        schema, table = qualified.split(".", 1)
        directory = backup_dir / schema
        directory.mkdir(exist_ok=True)
        path = directory / f"{table}.parquet"
        quoted_path = "'" + str(path).replace("'", "''") + "'"
        source.execute(f"COPY (SELECT * FROM {qualified}) TO {quoted_path} (FORMAT PARQUET)")
        manifest["tables"][qualified] = {
            "rows": source.execute(f"SELECT count(*) FROM {qualified}").fetchone()[0],
            "path": f"{schema}/{table}.parquet",
        }
    source.close()
    (backup_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    target = tmp_path / "restored.duckdb"
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/restore_v2_backup.py",
            str(backup_dir),
            "--database",
            str(target),
        ],
        cwd=Path(__file__).resolve().parents[1],
        check=True,
        capture_output=True,
        text=True,
    )
    assert f"tables={len(qualified_tables)}" in completed.stdout
    restored = duckdb.connect(str(target), read_only=True)
    assert restored.execute("SELECT value_decimal FROM gold.metric_values").fetchone()[0] == Decimal("123")
    assert restored.execute("SELECT count(*) FROM control.metric_definitions").fetchone()[0] == 1
    restored.close()
