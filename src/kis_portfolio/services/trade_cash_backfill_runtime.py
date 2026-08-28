"""Resumable control-plane runtime for the governed trade/cash backfill.

The runtime owns execution identity, durable physical-call accounting and
monotonic source watermarks.  Source adapters and canonical writes are supplied
by later Work Items; importing or invoking this module performs no KIS call.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Callable

import duckdb

from kis_portfolio.platform.migrations import MigrationRunner
from kis_portfolio.platform.pipeline import (
    ManagedPipelineRunner,
    PipelineDefinition,
    PipelineRunOutcome,
    PipelineStage,
    StageContext,
    StageResult,
)
from kis_portfolio.services.trade_cash_backfill import (
    BackfillBudgetError,
    BackfillCallBudget,
    BackfillPartition,
    BudgetedTradeCashBackfillPlan,
    PhysicalCallReservation,
)


PIPELINE_ID = "pipeline.trade-cash-backfill-v2"
PIPELINE_VERSION = "1.0.0"
BACKFILL_SLOT = "backfill"
WATERMARK_TYPE = "source_end_date_v1"

PartitionHandler = Callable[
    [BackfillPartition, "CheckpointingCallBudget", StageContext], StageResult
]


@dataclass(frozen=True, slots=True)
class BackfillExecutionOutcome:
    plan_hash: str
    budget_hash: str
    partition_outcomes: tuple[PipelineRunOutcome, ...]
    restored_source_calls: int


def watermark_partition_key(partition: BackfillPartition) -> str:
    """Return a stable, non-secret source stream identity."""

    raw = "|".join(
        (
            partition.source_operation,
            partition.account_label,
            partition.account_product_code,
            partition.account_type,
            partition.market,
            partition.exchange or "-",
            partition.source_route,
        )
    )
    return f"stream-{hashlib.sha256(raw.encode()).hexdigest()[:20]}"


class CheckpointingCallBudget:
    """Persist each reservation before the source adapter can perform I/O."""

    def __init__(
        self,
        connection: duckdb.DuckDBPyConnection,
        gate: BackfillCallBudget,
        *,
        run_id: str,
        stage_name: str,
        partition_key: str,
    ) -> None:
        self._connection = connection
        self._gate = gate
        self._run_id = run_id
        self._stage_name = stage_name
        self._partition_key = partition_key

    def reserve(self, partition_key: str) -> PhysicalCallReservation:
        if partition_key != self._partition_key:
            raise BackfillBudgetError(
                "partition handler attempted to reserve a different partition"
            )
        reservation = self._gate.reserve(partition_key)
        self._connection.execute(
            """
            UPDATE control.pipeline_stage_runs
            SET source_calls=?
            WHERE run_id=? AND stage_name=?
            """,
            [reservation.page_number, self._run_id, self._stage_name],
        )
        return reservation

    @property
    def total_used(self) -> int:
        return self._gate.total_used

    def used_for(self, partition_key: str) -> int:
        return self._gate.used_for(partition_key)


class _WatermarkStore:
    def __init__(
        self,
        connection: duckdb.DuckDBPyConnection,
        stream_starts: dict[str, date],
    ) -> None:
        self.connection = connection
        self.stream_starts = stream_starts

    def advance(self, partition: BackfillPartition, run_id: str) -> str:
        stream_key = watermark_partition_key(partition)
        row = self.connection.execute(
            """
            SELECT watermark_value
            FROM control.watermarks
            WHERE pipeline_id=? AND partition_key=? AND watermark_type=?
            """,
            [PIPELINE_ID, stream_key, WATERMARK_TYPE],
        ).fetchone()
        current = None if row is None else date.fromisoformat(row[0])
        if current is None:
            expected_start = self.stream_starts[stream_key]
            if partition.start_date != expected_start:
                raise RuntimeError(
                    f"watermark gap before first publish: {stream_key} "
                    f"expected {expected_start}, got {partition.start_date}"
                )
        elif partition.end_date <= current:
            return current.isoformat()
        elif partition.start_date > current + timedelta(days=1):
            raise RuntimeError(
                f"watermark gap: {stream_key} current {current}, next {partition.start_date}"
            )

        next_value = partition.end_date if current is None else max(current, partition.end_date)
        self.connection.execute(
            """
            INSERT INTO control.watermarks VALUES (?, ?, ?, ?, ?, current_timestamp)
            ON CONFLICT(pipeline_id, partition_key, watermark_type) DO UPDATE SET
                watermark_value=excluded.watermark_value,
                run_id=excluded.run_id,
                updated_at=excluded.updated_at
            """,
            [PIPELINE_ID, stream_key, WATERMARK_TYPE, next_value.isoformat(), run_id],
        )
        return next_value.isoformat()


def _restore_usage(
    connection: duckdb.DuckDBPyConnection,
    plan: BudgetedTradeCashBackfillPlan,
) -> dict[str, int]:
    restored: dict[str, int] = {}
    for partition in plan.source_plan.callable_partitions:
        row = connection.execute(
            """
            SELECT coalesce(s.source_calls, 0)
            FROM control.pipeline_runs r
            JOIN control.pipeline_stage_runs s ON s.run_id=r.run_id
            WHERE r.pipeline_id=? AND r.pipeline_version=? AND r.logical_date=?
              AND r.slot=? AND r.partition_key=?
              AND s.stage_name='collect-land-normalize'
            """,
            [
                PIPELINE_ID,
                PIPELINE_VERSION,
                plan.source_plan.end_date,
                BACKFILL_SLOT,
                partition.key,
            ],
        ).fetchone()
        if row and row[0]:
            restored[partition.key] = int(row[0])
    return restored


def _stream_starts(plan: BudgetedTradeCashBackfillPlan) -> dict[str, date]:
    starts: dict[str, date] = {}
    for partition in plan.source_plan.callable_partitions:
        key = watermark_partition_key(partition)
        starts[key] = min(starts.get(key, partition.start_date), partition.start_date)
    return starts


def execute_trade_cash_backfill(
    connection: duckdb.DuckDBPyConnection,
    plan: BudgetedTradeCashBackfillPlan,
    partition_handler: PartitionHandler,
) -> BackfillExecutionOutcome:
    """Execute callable partitions with durable resume and publish watermarks."""

    MigrationRunner(connection).require("0001")
    runner = ManagedPipelineRunner(connection)
    shared_gate = BackfillCallBudget(plan)
    restored = _restore_usage(connection, plan)
    shared_gate.restore(restored)
    watermark_store = _WatermarkStore(connection, _stream_starts(plan))
    outcomes: list[PipelineRunOutcome] = []

    for partition in plan.source_plan.callable_partitions:
        def collect(context: StageContext, *, current: BackfillPartition = partition) -> StageResult:
            before = shared_gate.used_for(current.key)
            checkpoint_gate = CheckpointingCallBudget(
                connection,
                shared_gate,
                run_id=context.run_id,
                stage_name="collect-land-normalize",
                partition_key=current.key,
            )
            result = partition_handler(current, checkpoint_gate, context)
            after = shared_gate.used_for(current.key)
            if result.source_calls != after - before:
                raise BackfillBudgetError(
                    "partition handler source_calls does not match guarded reservations: "
                    f"{result.source_calls} != {after - before}"
                )
            return StageResult(
                input_count=result.input_count,
                output_count=result.output_count,
                source_calls=after,
                evidence={
                    **result.evidence,
                    "plan_hash": plan.source_plan.plan_hash,
                    "budget_hash": plan.budget_hash,
                    "partition_key": current.key,
                    "cumulative_partition_source_calls": after,
                },
                quality=result.quality,
                lineage=result.lineage,
            )

        def quality(_: StageContext, *, current: BackfillPartition = partition) -> StageResult:
            return StageResult(
                evidence={"partition_key": current.key, "status": "control-plane-ready"}
            )

        def publish(context: StageContext, *, current: BackfillPartition = partition) -> StageResult:
            value = watermark_store.advance(current, context.run_id)
            return StageResult(
                evidence={
                    "partition_key": current.key,
                    "watermark_type": WATERMARK_TYPE,
                    "watermark_value": value,
                }
            )

        definition = PipelineDefinition(
            pipeline_id=PIPELINE_ID,
            version=PIPELINE_VERSION,
            stages=(
                PipelineStage("collect-land-normalize", collect),
                PipelineStage("quality", quality),
                PipelineStage("publish", publish),
            ),
            source_call_budget=plan.policy.max_physical_calls,
        )
        outcomes.append(
            runner.run(
                definition,
                logical_date=plan.source_plan.end_date,
                slot=BACKFILL_SLOT,
                partition_key=partition.key,
                state={"plan_hash": plan.source_plan.plan_hash, "budget_hash": plan.budget_hash},
            )
        )

    return BackfillExecutionOutcome(
        plan_hash=plan.source_plan.plan_hash,
        budget_hash=plan.budget_hash,
        partition_outcomes=tuple(outcomes),
        restored_source_calls=sum(restored.values()),
    )
