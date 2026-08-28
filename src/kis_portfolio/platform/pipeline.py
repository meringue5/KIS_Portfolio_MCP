"""Small managed-pipeline runtime with logical idempotency and stage resume."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any, Callable

import duckdb

from kis_portfolio.modules.core import new_id


class PipelineExecutionError(RuntimeError):
    def __init__(self, run_id: str, stage_name: str, cause: Exception) -> None:
        super().__init__(f"pipeline run {run_id} failed at {stage_name}: {cause}")
        self.run_id = run_id
        self.stage_name = stage_name
        self.__cause__ = cause


@dataclass(slots=True)
class StageContext:
    run_id: str
    logical_date: date
    slot: str
    partition_key: str
    state: dict[str, Any]


@dataclass(frozen=True, slots=True)
class QualityEvidence:
    dataset_id: str
    rule_id: str
    status: str
    observed_value: str | None = None
    expected_value: str | None = None
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class LineageEvidence:
    input_ref: str
    output_ref: str
    transform_id: str
    transform_version: str


@dataclass(frozen=True, slots=True)
class StageResult:
    input_count: int = 0
    output_count: int = 0
    source_calls: int = 0
    evidence: dict[str, Any] = field(default_factory=dict)
    quality: tuple[QualityEvidence, ...] = ()
    lineage: tuple[LineageEvidence, ...] = ()


StageHandler = Callable[[StageContext], StageResult]


@dataclass(frozen=True, slots=True)
class PipelineStage:
    name: str
    handler: StageHandler


@dataclass(frozen=True, slots=True)
class PipelineDefinition:
    pipeline_id: str
    version: str
    stages: tuple[PipelineStage, ...]
    source_call_budget: int

    @property
    def definition_hash(self) -> str:
        value = f"{self.pipeline_id}|{self.version}|{self.source_call_budget}|" + "|".join(
            stage.name for stage in self.stages
        )
        return hashlib.sha256(value.encode()).hexdigest()


class PipelineRegistry:
    def __init__(self) -> None:
        self._definitions: dict[tuple[str, str], PipelineDefinition] = {}

    def register(self, definition: PipelineDefinition) -> None:
        key = (definition.pipeline_id, definition.version)
        if key in self._definitions:
            raise ValueError(f"pipeline already registered: {key}")
        if not definition.stages or len({stage.name for stage in definition.stages}) != len(definition.stages):
            raise ValueError("pipeline requires uniquely named stages")
        self._definitions[key] = definition

    def get(self, pipeline_id: str, version: str) -> PipelineDefinition:
        return self._definitions[(pipeline_id, version)]


@dataclass(frozen=True, slots=True)
class PipelineRunOutcome:
    run_id: str
    status: str
    reused: bool
    source_calls: int


class ManagedPipelineRunner:
    def __init__(self, connection: duckdb.DuckDBPyConnection) -> None:
        self.connection = connection

    @staticmethod
    def logical_key(definition: PipelineDefinition, logical_date: date, slot: str, partition_key: str) -> str:
        raw = f"{definition.pipeline_id}|{definition.version}|{logical_date.isoformat()}|{slot}|{partition_key}"
        return hashlib.sha256(raw.encode()).hexdigest()

    def register_definition(self, definition: PipelineDefinition) -> None:
        document = {
            "pipeline_id": definition.pipeline_id,
            "version": definition.version,
            "stages": [stage.name for stage in definition.stages],
            "source_call_budget": definition.source_call_budget,
        }
        self.connection.execute("""
            INSERT INTO control.pipeline_definitions VALUES (?, ?, 'approved', ?, ?, current_timestamp)
            ON CONFLICT(pipeline_id, version) DO UPDATE SET
                definition_hash=excluded.definition_hash, definition=excluded.definition
        """, [definition.pipeline_id, definition.version, definition.definition_hash, json.dumps(document)])

    def _claim_run(self, definition: PipelineDefinition, logical_date: date, slot: str, partition_key: str) -> tuple[str, str, bool]:
        key = self.logical_key(definition, logical_date, slot, partition_key)
        existing = self.connection.execute(
            "SELECT run_id, status FROM control.pipeline_runs WHERE idempotency_key=?", [key]
        ).fetchone()
        if existing:
            return existing[0], existing[1], True
        run_id = new_id()
        self.connection.execute("""
            INSERT INTO control.pipeline_runs(
                run_id, pipeline_id, pipeline_version, logical_date, slot, partition_key,
                idempotency_key, status, started_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'running', ?)
        """, [run_id, definition.pipeline_id, definition.version, logical_date, slot, partition_key, key,
              datetime.now(UTC)])
        return run_id, "running", False

    def run(
        self,
        definition: PipelineDefinition,
        *,
        logical_date: date,
        slot: str,
        partition_key: str = "default",
        state: dict[str, Any] | None = None,
    ) -> PipelineRunOutcome:
        self.register_definition(definition)
        run_id, status, reused = self._claim_run(definition, logical_date, slot, partition_key)
        if status == "succeeded":
            calls = self.connection.execute(
                "SELECT source_calls FROM control.pipeline_runs WHERE run_id=?", [run_id]
            ).fetchone()[0]
            return PipelineRunOutcome(run_id, status, True, calls)
        self.connection.execute(
            "UPDATE control.pipeline_runs SET status='running', error_code=NULL, error_message=NULL, finished_at=NULL WHERE run_id=?",
            [run_id],
        )
        context = StageContext(run_id, logical_date, slot, partition_key, state or {})
        cumulative_calls = self.connection.execute(
            "SELECT coalesce(sum(source_calls), 0) FROM control.pipeline_stage_runs WHERE run_id=? AND status='succeeded'",
            [run_id],
        ).fetchone()[0]
        for order, stage in enumerate(definition.stages):
            row = self.connection.execute(
                "SELECT status, attempt FROM control.pipeline_stage_runs WHERE run_id=? AND stage_name=?",
                [run_id, stage.name],
            ).fetchone()
            if row and row[0] == "succeeded":
                continue
            attempt = (row[1] if row else 0) + 1
            now = datetime.now(UTC)
            self.connection.execute("""
                INSERT INTO control.pipeline_stage_runs(
                    run_id, stage_name, stage_order, status, attempt, started_at
                ) VALUES (?, ?, ?, 'running', ?, ?)
                ON CONFLICT(run_id, stage_name) DO UPDATE SET
                    status='running', attempt=excluded.attempt, started_at=excluded.started_at,
                    finished_at=NULL, error_message=NULL
            """, [run_id, stage.name, order, attempt, now])
            try:
                result = stage.handler(context)
                if cumulative_calls + result.source_calls > definition.source_call_budget:
                    raise RuntimeError(
                        f"source call budget exceeded: {cumulative_calls + result.source_calls} > {definition.source_call_budget}"
                    )
                cumulative_calls += result.source_calls
                self._record_evidence(run_id, stage.name, result)
            except Exception as exc:
                self.connection.execute("""
                    UPDATE control.pipeline_stage_runs SET status='failed', finished_at=?, error_message=?
                    WHERE run_id=? AND stage_name=?
                """, [datetime.now(UTC), str(exc), run_id, stage.name])
                self.connection.execute("""
                    UPDATE control.pipeline_runs SET status='failed', source_calls=?, finished_at=?,
                        error_code='stage_failed', error_message=? WHERE run_id=?
                """, [cumulative_calls, datetime.now(UTC), str(exc), run_id])
                raise PipelineExecutionError(run_id, stage.name, exc) from exc
        self.connection.execute("""
            UPDATE control.pipeline_runs SET status='succeeded', source_calls=?, finished_at=? WHERE run_id=?
        """, [cumulative_calls, datetime.now(UTC), run_id])
        return PipelineRunOutcome(run_id, "succeeded", reused, cumulative_calls)

    def _record_evidence(self, run_id: str, stage_name: str, result: StageResult) -> None:
        self.connection.execute("""
            UPDATE control.pipeline_stage_runs SET status='succeeded', input_count=?, output_count=?,
                source_calls=?, finished_at=?, evidence=? WHERE run_id=? AND stage_name=?
        """, [result.input_count, result.output_count, result.source_calls, datetime.now(UTC),
              json.dumps(result.evidence, default=str), run_id, stage_name])
        for quality in result.quality:
            self.connection.execute("""
                INSERT INTO control.quality_results VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, [new_id(), run_id, quality.dataset_id, quality.rule_id, quality.status,
                  quality.observed_value, quality.expected_value, json.dumps(quality.details), datetime.now(UTC)])
        for lineage in result.lineage:
            evidence = f"{run_id}|{lineage.input_ref}|{lineage.output_ref}|{lineage.transform_id}|{lineage.transform_version}"
            self.connection.execute("""
                INSERT INTO control.lineage_edges VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, [new_id(), run_id, lineage.input_ref, lineage.output_ref, lineage.transform_id,
                  lineage.transform_version, hashlib.sha256(evidence.encode()).hexdigest(), datetime.now(UTC)])
