"""DuckDB/MotherDuck persistence for governed metric definitions and values."""

from __future__ import annotations

import json
from decimal import Decimal

import duckdb

from kis_portfolio.modules.monitoring import MetricDefinition, MetricValue


class MetricValueConflictError(RuntimeError):
    """Raised when a logical evaluation key would be silently rewritten."""


class MetricWarehouseRepository:
    def __init__(self, connection: duckdb.DuckDBPyConnection) -> None:
        self.connection = connection

    def register_definition(self, definition: MetricDefinition) -> None:
        prior = self.connection.execute(
            "SELECT definition_hash FROM control.metric_definitions WHERE metric_id=? AND version=?",
            [definition.metric_id, definition.version],
        ).fetchone()
        if prior and prior[0] != definition.definition_hash:
            raise MetricValueConflictError(
                f"metric definition changed in place: {(definition.metric_id, definition.version)}"
            )
        self.connection.execute("""
            INSERT INTO control.metric_definitions(
                metric_id, version, contract_status, definition_hash, definition
            ) VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(metric_id, version) DO NOTHING
        """, [
            definition.metric_id,
            definition.version,
            definition.status,
            definition.definition_hash,
            json.dumps(definition.document, ensure_ascii=False, sort_keys=True),
        ])

    @staticmethod
    def _input_refs(value: MetricValue) -> str:
        return json.dumps([
            {
                "ref": item.ref,
                "effective_at": item.effective_at.isoformat(),
                "knowledge_at": item.knowledge_at.isoformat(),
                "quality_status": item.quality_status,
                "lineage_hash": item.lineage_hash,
            }
            for item in sorted(value.inputs, key=lambda candidate: candidate.ref)
        ], sort_keys=True, separators=(",", ":"))

    def write_value(self, value: MetricValue) -> bool:
        self.register_definition(value.definition)
        key = [
            value.definition.metric_id,
            value.definition.version,
            value.subject_type,
            value.subject_id,
            value.evaluation_at,
        ]
        prior = self.connection.execute("""
            SELECT evaluation_slot, effective_at, knowledge_cutoff_at, value_decimal, unit,
                   quality_status, input_refs, formula_hash, lineage_hash
            FROM gold.metric_values
            WHERE metric_id=? AND metric_version=? AND subject_type=? AND subject_id=? AND evaluation_at=?
        """, key).fetchone()
        input_refs = self._input_refs(value)
        expected = (
            value.evaluation_slot,
            value.effective_at,
            value.knowledge_cutoff_at,
            value.value,
            value.definition.unit,
            value.quality_status,
            input_refs,
            value.formula_hash,
            value.lineage_hash,
        )
        if prior:
            normalized = (
                prior[0], prior[1], prior[2], Decimal(prior[3]) if prior[3] is not None else None,
                prior[4], prior[5],
                str(prior[6]), prior[7], prior[8],
            )
            if normalized != expected:
                raise MetricValueConflictError("conflicting value for existing metric evaluation key")
            return False
        self.connection.execute("""
            INSERT INTO gold.metric_values(
                metric_id, metric_version, subject_type, subject_id, evaluation_at,
                evaluation_slot, effective_at, knowledge_cutoff_at, value_decimal, unit,
                quality_status, input_refs, formula_hash, lineage_hash, evaluation_run_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, [
            *key,
            value.evaluation_slot,
            value.effective_at,
            value.knowledge_cutoff_at,
            value.value,
            value.definition.unit,
            value.quality_status,
            input_refs,
            value.formula_hash,
            value.lineage_hash,
            value.evaluation_run_id,
        ])
        return True

    def count_values(self) -> int:
        return self.connection.execute("SELECT count(*) FROM gold.metric_values").fetchone()[0]
