"""Append-only normalized forward-consensus repository with fetched-at reads."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from decimal import Decimal
from typing import Any

import duckdb

from kis_portfolio.modules.market.consensus import ConsensusForwardSnapshot, validate_snapshot
from kis_portfolio.platform.consensus_registry import ConsensusContractBundle


def _json(value: object) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)


def _digest(prefix: str, value: object) -> str:
    return hashlib.sha256(f"{prefix}|{_json(value)}".encode()).hexdigest()


class ConsensusWarehouseRepository:
    def __init__(self, connection: duckdb.DuckDBPyConnection) -> None:
        self.connection = connection

    def record_snapshot(
        self,
        value: ConsensusForwardSnapshot,
        *,
        bundle: ConsensusContractBundle,
        pipeline_run_id: str | None = None,
    ) -> str:
        validate_snapshot(value)
        if bundle.activation_state != "inactive" or value.definition_hash != bundle.definition_hash:
            raise ValueError("consensus snapshot requires the exact inactive contract bundle")
        natural_key = [
            value.issuer_id,
            value.provider_forecast_date,
            value.metric,
            value.horizon,
            value.fetched_at,
        ]
        prior = self.connection.execute(
            """
            SELECT consensus_forward_snapshot_id,definition_hash,content_hash,
                   source_request_ref,us_session_date
            FROM silver.alpha_vantage_consensus_forward_snapshots
            WHERE issuer_id=? AND provider_forecast_date=? AND metric=? AND horizon=?
              AND fetched_at=?
            """,
            natural_key,
        ).fetchone()
        expected_replay = (
            value.definition_hash,
            value.content_hash,
            value.source_request_ref,
            value.us_session_date,
        )
        if prior is not None:
            if tuple(prior[1:]) != expected_replay:
                raise ValueError("consensus snapshot conflicts with its immutable fetched-at key")
            return prior[0]
        snapshot_id = _digest("alpha-forward-snapshot", {
            "issuer_id": value.issuer_id,
            "provider_forecast_date": value.provider_forecast_date,
            "metric": value.metric,
            "horizon": value.horizon,
            "fetched_at": value.fetched_at,
        })
        self.connection.execute(
            """
            INSERT INTO silver.alpha_vantage_consensus_forward_snapshots(
                consensus_forward_snapshot_id,definition_hash,source_id,issuer_id,
                provider_forecast_date,horizon,metric,estimate_average,estimate_high,
                estimate_low,analyst_count,average_7_days_ago,average_30_days_ago,
                average_60_days_ago,average_90_days_ago,revision_up_trailing_7_days,
                revision_up_trailing_30_days,revision_down_trailing_7_days,
                revision_down_trailing_30_days,us_session_date,fetched_at,
                source_request_ref,content_hash,quality_status
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            [
                snapshot_id,
                value.definition_hash,
                value.source_id,
                value.issuer_id,
                value.provider_forecast_date,
                value.horizon,
                value.metric,
                value.estimate_average,
                value.estimate_high,
                value.estimate_low,
                value.analyst_count,
                value.average_7_days_ago,
                value.average_30_days_ago,
                value.average_60_days_ago,
                value.average_90_days_ago,
                value.revision_up_trailing_7_days,
                value.revision_up_trailing_30_days,
                value.revision_down_trailing_7_days,
                value.revision_down_trailing_30_days,
                value.us_session_date,
                value.fetched_at,
                value.source_request_ref,
                value.content_hash,
                value.quality_status,
            ],
        )
        if pipeline_run_id:
            lineage_id = _digest("alpha-forward-lineage", {
                "run_id": pipeline_run_id,
                "source_request_ref": value.source_request_ref,
                "snapshot_id": snapshot_id,
            })
            self.connection.execute(
                """
                INSERT INTO control.lineage_edges(
                    lineage_edge_id,run_id,input_ref,output_ref,transform_id,
                    transform_version,evidence_hash,created_at
                ) VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(lineage_edge_id) DO NOTHING
                """,
                [
                    lineage_id,
                    pipeline_run_id,
                    f"alpha-memory-request:{value.source_request_ref}",
                    f"silver.alpha_vantage_consensus_forward_snapshots:{snapshot_id}",
                    "alpha-forward-normalizer",
                    "1.0.0",
                    value.content_hash,
                    value.fetched_at,
                ],
            )
        return snapshot_id

    def snapshots_as_of(
        self,
        *,
        cutoff_at: datetime,
        issuer_id: str | None = None,
    ) -> list[dict[str, Any]]:
        if cutoff_at.tzinfo is None:
            raise ValueError("consensus cutoff must be timezone-aware")
        clauses = ["fetched_at<=?"]
        params: list[Any] = [cutoff_at]
        if issuer_id is not None:
            clauses.append("issuer_id=?")
            params.append(issuer_id)
        cursor = self.connection.execute(
            f"""
            SELECT * EXCLUDE (row_number_value,recorded_at)
            FROM (
                SELECT snapshots.*,
                       row_number() OVER (
                           PARTITION BY issuer_id,provider_forecast_date,metric,horizon
                           ORDER BY fetched_at DESC,consensus_forward_snapshot_id DESC
                       ) AS row_number_value
                FROM silver.alpha_vantage_consensus_forward_snapshots snapshots
                WHERE {' AND '.join(clauses)}
            )
            WHERE row_number_value=1
            ORDER BY issuer_id,provider_forecast_date,metric,horizon
            """,
            params,
        )
        columns = [column[0] for column in cursor.description]
        return [dict(zip(columns, row, strict=True)) | {
            "knowledge_mode": "forward_collected_system_as_of"
        } for row in cursor.fetchall()]

    def retention_candidates(self, *, fetched_before: datetime) -> tuple[str, ...]:
        """Plan expired normalized rows without deleting or mutating them."""

        if fetched_before.tzinfo is None:
            raise ValueError("consensus retention cutoff must be timezone-aware")
        rows = self.connection.execute(
            """
            SELECT consensus_forward_snapshot_id
            FROM silver.alpha_vantage_consensus_forward_snapshots
            WHERE fetched_at<? ORDER BY fetched_at,consensus_forward_snapshot_id
            """,
            [fetched_before],
        ).fetchall()
        return tuple(row[0] for row in rows)


def snapshot_from_row(row: dict[str, Any]) -> ConsensusForwardSnapshot:
    """Build the typed value used by pure analysis without exposing DB metadata."""

    decimal_fields = (
        "estimate_average",
        "estimate_high",
        "estimate_low",
        "average_7_days_ago",
        "average_30_days_ago",
        "average_60_days_ago",
        "average_90_days_ago",
    )
    values = dict(row)
    for field in decimal_fields:
        if values.get(field) is not None:
            values[field] = Decimal(values[field])
    allowed = set(ConsensusForwardSnapshot.__dataclass_fields__)
    return ConsensusForwardSnapshot(**{key: value for key, value in values.items() if key in allowed})
