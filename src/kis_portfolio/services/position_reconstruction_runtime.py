"""Read-only production planning for governed position reconstruction."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

import duckdb

from kis_portfolio.modules.portfolio.reconstruction import CorporateActionCoverage
from kis_portfolio.services.position_replay import (
    PositionReplayPlan,
    ReplayCorporateActionEffect,
    ReplayRequest,
    ReplayTrade,
    replay_position,
)


PIPELINE_ID = "pipeline.position-lot-reconstruction-v2"
PIPELINE_VERSION = "1.0.0"
MINIMUM_INPUT_MIGRATION = "0008"


@dataclass(frozen=True, slots=True)
class ReconstructionPartitionPlan:
    request: ReplayRequest
    plan: PositionReplayPlan
    has_current_position: bool
    has_trade_history: bool


@dataclass(frozen=True, slots=True)
class ReconstructionExecutionPlan:
    start_at: datetime
    cutoff_at: datetime
    schema_version: str
    partitions: tuple[ReconstructionPartitionPlan, ...]
    execution_hash: str
    input_position_rows: int
    input_trade_rows: int
    coverage_rows: int

    def public_report(self) -> dict[str, Any]:
        statuses: dict[str, int] = {}
        blockers: dict[str, int] = {}
        for item in self.partitions:
            status = item.plan.assessment.status.value
            statuses[status] = statuses.get(status, 0) + 1
            for blocker in item.plan.assessment.blockers:
                blockers[blocker] = blockers.get(blocker, 0) + 1
        eligible = tuple(
            item for item in self.partitions
            if item.plan.assessment.eligible_for_reconciled_projection
        )
        blocked = len(self.partitions) - len(eligible)
        return {
            "pipeline_id": PIPELINE_ID,
            "pipeline_version": PIPELINE_VERSION,
            "mode": "read_only_aggregate_dry_run",
            "start_at": self.start_at.isoformat(),
            "cutoff_at": self.cutoff_at.isoformat(),
            "schema_version": self.schema_version,
            "execution_hash": self.execution_hash,
            "partition_count": len(self.partitions),
            "held_partition_count": sum(item.has_current_position for item in self.partitions),
            "trade_history_partition_count": sum(item.has_trade_history for item in self.partitions),
            "trade_only_partition_count": sum(
                item.has_trade_history and not item.has_current_position for item in self.partitions
            ),
            "status_counts": dict(sorted(statuses.items())),
            "blocker_counts": dict(sorted(blockers.items())),
            "eligible_projection_partitions": len(eligible),
            "exception_only_partitions": blocked,
            "projected_episode_identities": sum(len(item.plan.episodes) for item in eligible),
            "projected_lot_identities": sum(len(item.plan.lots) for item in eligible),
            "projected_allocation_revisions": sum(len(item.plan.allocations) for item in eligible),
            "projected_allocation_slices": sum(
                len(allocation.plan.slices)
                for item in eligible for allocation in item.plan.allocations
            ),
            "projected_exception_identities": blocked,
            "input_position_rows": self.input_position_rows,
            "input_trade_rows": self.input_trade_rows,
            "coverage_rows": self.coverage_rows,
            "source_calls": 0,
            "warehouse_writes": 0,
            "silver_projection_publish_allowed": bool(eligible),
            "exception_publish_allowed": bool(blocked),
            "s06_ready": bool(self.partitions),
        }


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _table_exists(connection: duckdb.DuckDBPyConnection, schema: str, table: str) -> bool:
    return bool(connection.execute(
        """
        SELECT 1 FROM information_schema.tables
        WHERE table_catalog=current_database() AND table_schema=? AND table_name=?
        """,
        [schema, table],
    ).fetchone())


def _schema_version(connection: duckdb.DuckDBPyConnection) -> str:
    row = connection.execute("SELECT max(version) FROM control.schema_migrations").fetchone()
    version = str(row[0] or "")
    applied = {
        str(item[0]) for item in connection.execute(
            "SELECT version FROM control.schema_migrations"
        ).fetchall()
    }
    if MINIMUM_INPUT_MIGRATION not in applied:
        raise RuntimeError(f"reconstruction input migration {MINIMUM_INPUT_MIGRATION} is not applied")
    return version


def _position_state(
    connection: duckdb.DuckDBPyConnection,
    cutoff_at: datetime,
) -> tuple[dict[str, datetime], dict[tuple[str, str], Decimal], int]:
    cutoffs = {
        str(account_id): as_of
        for account_id, as_of in connection.execute(
            """
            SELECT account_id,max(as_of)
            FROM silver.position_snapshots
            WHERE quality_status='pass' AND as_of<=?
            GROUP BY account_id
            """,
            [cutoff_at],
        ).fetchall()
    }
    rows = connection.execute(
        """
        WITH cutoffs AS (
            SELECT account_id,max(as_of) AS as_of
            FROM silver.position_snapshots
            WHERE quality_status='pass' AND as_of<=?
            GROUP BY account_id
        )
        SELECT positions.account_id,positions.instrument_id,positions.quantity
        FROM silver.position_snapshots positions
        JOIN cutoffs USING(account_id,as_of)
        WHERE positions.quality_status='pass' AND positions.quantity>0
        ORDER BY positions.account_id,positions.instrument_id
        """,
        [cutoff_at],
    ).fetchall()
    quantities = {(str(account), str(instrument)): Decimal(str(quantity)) for account, instrument, quantity in rows}
    return cutoffs, quantities, len(rows)


def _trade_state(
    connection: duckdb.DuckDBPyConnection,
    start_at: datetime,
    cutoff_at: datetime,
) -> dict[tuple[str, str], tuple[ReplayTrade, ...]]:
    rows = connection.execute(
        """
        SELECT trade_event_id,account_id,instrument_id,side,executed_at,execution_sequence,
               quantity,price,currency
        FROM silver.trade_events_current
        WHERE quality_status='pass' AND executed_at BETWEEN ? AND ?
        ORDER BY account_id,instrument_id,executed_at,execution_sequence,trade_event_id
        """,
        [start_at, cutoff_at],
    ).fetchall()
    grouped: dict[tuple[str, str], list[ReplayTrade]] = {}
    for row in rows:
        trade = ReplayTrade(
            trade_event_id=str(row[0]),
            account_id=str(row[1]),
            instrument_id=str(row[2]),
            side=str(row[3]),
            executed_at=row[4],
            execution_sequence=str(row[5]),
            quantity=Decimal(str(row[6])),
            price=Decimal(str(row[7])),
            currency=str(row[8]),
        )
        grouped.setdefault((trade.account_id, trade.instrument_id), []).append(trade)
    return {key: tuple(value) for key, value in grouped.items()}


def _coverage_rows(
    connection: duckdb.DuckDBPyConnection,
    cutoff_at: datetime,
) -> tuple[dict[str, tuple[str, date, date]], int]:
    rows = connection.execute(
        """
        SELECT quality_result_id,details
        FROM control.quality_results
        WHERE dataset_id='dataset.corporate-action-event'
          AND rule_id='held_instrument_date_range_coverage'
          AND status='pass' AND evaluated_at<=?
        ORDER BY evaluated_at DESC,quality_result_id DESC
        """,
        [cutoff_at],
    ).fetchall()
    result: dict[str, tuple[str, date, date]] = {}
    for quality_id, raw_details in rows:
        details = json.loads(raw_details) if isinstance(raw_details, str) else dict(raw_details or {})
        try:
            instrument_id = str(details["instrument_id"])
            start_date = date.fromisoformat(str(details["start_date"]))
            end_date = date.fromisoformat(str(details["end_date"]))
        except (KeyError, TypeError, ValueError):
            continue
        result.setdefault(instrument_id, (str(quality_id), start_date, end_date))
    return result, len(rows)


def _action_effects(
    connection: duckdb.DuckDBPyConnection,
    cutoff_at: datetime,
) -> tuple[ReplayCorporateActionEffect, ...]:
    if not _table_exists(connection, "silver", "corporate_action_adjustment_effects"):
        return ()
    rows = connection.execute(
        """
        SELECT corporate_action_revision_id,effect_type,input_instrument_id,output_instrument_id,
               factor_numerator,factor_denominator,effective_at,knowledge_at,quality_status
        FROM silver.corporate_action_adjustment_effects
        WHERE quality_status='pass' AND knowledge_at<=?
        ORDER BY effective_at,corporate_action_revision_id,effect_type
        """,
        [cutoff_at],
    ).fetchall()
    return tuple(
        ReplayCorporateActionEffect(
            corporate_action_revision_id=str(row[0]),
            effect_type=str(row[1]),
            input_instrument_id=str(row[2]),
            output_instrument_id=str(row[3]) if row[3] else None,
            factor_numerator=Decimal(str(row[4])) if row[4] is not None else None,
            factor_denominator=Decimal(str(row[5])) if row[5] is not None else None,
            effective_at=row[6],
            knowledge_at=row[7],
            quality_status=str(row[8]),
        )
        for row in rows
    )


def _lineage_effects(
    instrument_id: str,
    effects: tuple[ReplayCorporateActionEffect, ...],
) -> tuple[tuple[str, ...], tuple[ReplayCorporateActionEffect, ...]]:
    lineage = {instrument_id}
    changed = True
    while changed:
        changed = False
        for effect in effects:
            identities = {effect.input_instrument_id}
            if effect.output_instrument_id:
                identities.add(effect.output_instrument_id)
            if lineage & identities and not identities <= lineage:
                lineage.update(identities)
                changed = True
    selected = tuple(
        effect for effect in effects
        if effect.input_instrument_id in lineage
        or (effect.output_instrument_id is not None and effect.output_instrument_id in lineage)
    )
    return tuple(sorted(lineage)), selected


def build_reconstruction_execution_plan(
    connection: duckdb.DuckDBPyConnection,
    *,
    start_at: datetime,
    cutoff_at: datetime,
) -> ReconstructionExecutionPlan:
    """Read governed production facts and return a confidential internal plan plus safe report."""

    if start_at.tzinfo is None or cutoff_at.tzinfo is None or start_at >= cutoff_at:
        raise ValueError("reconstruction window must be positive and timezone-aware")
    schema_version = _schema_version(connection)
    account_cutoffs, positions, position_rows = _position_state(connection, cutoff_at)
    trades = _trade_state(connection, start_at, cutoff_at)
    coverage, coverage_count = _coverage_rows(connection, cutoff_at)
    effects = _action_effects(connection, cutoff_at)
    scopes = sorted(set(positions) | set(trades))
    partitions: list[ReconstructionPartitionPlan] = []
    trade_count = 0
    for account_id, instrument_id in scopes:
        current_quantity = positions.get((account_id, instrument_id), Decimal("0"))
        partition_trades = trades.get((account_id, instrument_id), ())
        trade_count += len(partition_trades)
        lineage, partition_effects = _lineage_effects(instrument_id, effects)
        coverage_record = coverage.get(instrument_id)
        coverage_status = CorporateActionCoverage.NOT_ASSESSED
        coverage_id = None
        if coverage_record:
            coverage_id, covered_start, covered_end = coverage_record
            if covered_start <= start_at.date() and covered_end >= cutoff_at.date():
                coverage_status = CorporateActionCoverage.PASS
        gaps = () if account_id in account_cutoffs else ("missing_current_account_snapshot",)
        request = ReplayRequest(
            account_id=account_id,
            target_instrument_id=instrument_id,
            lineage_instrument_ids=lineage,
            start_at=start_at,
            cutoff_at=cutoff_at,
            current_quantity=current_quantity,
            corporate_action_coverage=coverage_status,
            coverage_quality_result_id=coverage_id,
            source_gap_reasons=gaps,
        )
        plan = replay_position(request, partition_trades, partition_effects)
        partitions.append(ReconstructionPartitionPlan(
            request=request,
            plan=plan,
            has_current_position=(account_id, instrument_id) in positions,
            has_trade_history=bool(partition_trades),
        ))
    hash_document = {
        "pipeline_id": PIPELINE_ID,
        "pipeline_version": PIPELINE_VERSION,
        "start_at": start_at.isoformat(),
        "cutoff_at": cutoff_at.isoformat(),
        # Additive migrations between the S05 dry-run and the S06 managed
        # execution must not change the logical execution identity by themselves.
        "partitions": [
            (
                item.plan.partition_key,
                item.plan.replay_hash,
                item.plan.projection_hash,
                item.plan.assessment.status.value,
                item.plan.assessment.blockers,
            )
            for item in partitions
        ],
    }
    execution_hash = hashlib.sha256(_json(hash_document).encode()).hexdigest()
    return ReconstructionExecutionPlan(
        start_at=start_at,
        cutoff_at=cutoff_at,
        schema_version=schema_version,
        partitions=tuple(partitions),
        execution_hash=execution_hash,
        input_position_rows=position_rows,
        input_trade_rows=trade_count,
        coverage_rows=coverage_count,
    )
