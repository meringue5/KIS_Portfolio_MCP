"""Append-only macro definition, observation and profile repository for ADR-027."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from decimal import Decimal
from typing import Any

import duckdb

from kis_portfolio.modules.market.macro import (
    QUERY_MODES,
    MacroObservationRevision,
    MacroSeriesDefinition,
    validate_observation,
)


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _digest(prefix: str, value: Any) -> str:
    return hashlib.sha256(f"{prefix}|{_json(value)}".encode()).hexdigest()


class MacroWarehouseRepository:
    def __init__(self, connection: duckdb.DuckDBPyConnection) -> None:
        self.connection = connection

    def record_observation(
        self,
        value: MacroObservationRevision,
        *,
        definition: MacroSeriesDefinition,
    ) -> str:
        validate_observation(value, definition)
        projected = self.connection.execute(
            """
            SELECT definition_hash,source_id,provider_series_id,native_frequency,
                   native_unit,seasonal_adjustment,vintage_capability,activation_state
            FROM control.macro_series_definitions
            WHERE series_contract_id=? AND version=?
            """,
            [value.series_contract_id, value.series_contract_version],
        ).fetchone()
        expected = (
            definition.definition_hash, definition.source_id, definition.provider_series_id,
            definition.native_frequency, definition.native_unit,
            definition.seasonal_adjustment, definition.vintage_capability,
            definition.activation_state,
        )
        if projected is None or tuple(projected) != expected:
            raise ValueError("macro observation requires the exact projected series definition")

        key = [
            value.series_contract_id, value.observation_period,
            value.revision_kind, value.revision_key,
        ]
        prior = self.connection.execute(
            """
            SELECT macro_observation_revision_id,definition_hash,content_hash,native_value,
                   missing_reason,knowledge_at,fetched_at
            FROM silver.macro_observation_revisions
            WHERE series_contract_id=? AND observation_period=?
              AND revision_kind=? AND revision_key=?
            """,
            key,
        ).fetchone()
        expected_replay = (
            value.definition_hash, value.content_hash, value.native_value,
            value.missing_reason, value.knowledge_at, value.fetched_at,
        )
        if prior is not None:
            normalized = (
                prior[1], prior[2], Decimal(prior[3]) if prior[3] is not None else None,
                prior[4], prior[5], prior[6],
            )
            if normalized != expected_replay:
                raise ValueError("macro revision key replay conflicts with immutable content")
            return prior[0]

        revision_id = _digest("macro-observation-revision", {
            "series_contract_id": value.series_contract_id,
            "observation_period": value.observation_period,
            "revision_kind": value.revision_kind,
            "revision_key": value.revision_key,
        })
        self.connection.execute(
            """
            INSERT INTO silver.macro_observation_revisions(
                macro_observation_revision_id,series_contract_id,series_contract_version,
                definition_hash,observation_period,revision_kind,revision_key,native_value,
                missing_reason,native_unit,native_frequency,seasonal_adjustment,
                source_realtime_start,source_realtime_end,source_available_at,
                source_time_precision,knowledge_at,fetched_at,request_id,pipeline_run_id,
                partition_key,content_hash,rights_status,quality_status,provenance
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            [
                revision_id, value.series_contract_id, value.series_contract_version,
                value.definition_hash, value.observation_period, value.revision_kind,
                value.revision_key, value.native_value, value.missing_reason,
                value.native_unit, value.native_frequency, value.seasonal_adjustment,
                value.source_realtime_start, value.source_realtime_end,
                value.source_available_at, value.source_time_precision,
                value.knowledge_at, value.fetched_at, value.request_id,
                value.pipeline_run_id, value.partition_key, value.content_hash,
                value.rights_status, value.quality_status, _json(value.provenance or {}),
            ],
        )
        if value.pipeline_run_id:
            lineage_id = _digest("macro-lineage", {
                "run_id": value.pipeline_run_id,
                "request_id": value.request_id,
                "revision_id": revision_id,
            })
            self.connection.execute(
                """
                INSERT INTO control.lineage_edges(
                    lineage_edge_id,run_id,input_ref,output_ref,transform_id,
                    transform_version,evidence_hash,created_at
                ) VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(lineage_edge_id) DO NOTHING
                """,
                [
                    lineage_id, value.pipeline_run_id,
                    f"macro-source-request:{value.request_id}",
                    f"silver.macro_observation_revisions:{revision_id}",
                    "macro-fixture-normalizer", "1.0.0",
                    _digest("macro-lineage-evidence", value.content_hash),
                    value.knowledge_at,
                ],
            )
        return revision_id

    def observations_as_of(
        self,
        *,
        cutoff_at: datetime,
        series_contract_id: str | None = None,
        query_mode: str = "system_as_of",
    ) -> list[dict[str, Any]]:
        if cutoff_at.tzinfo is None:
            raise ValueError("macro cutoff must be timezone-aware")
        if query_mode not in QUERY_MODES:
            raise ValueError("unsupported macro query mode")
        clock = "knowledge_at" if query_mode == "system_as_of" else "source_available_at"
        clauses = [f"{clock} IS NOT NULL", f"{clock}<=?"]
        params: list[Any] = [cutoff_at]
        if query_mode == "retrospective_source_as_of":
            clauses.append("source_realtime_end>=CAST(? AS DATE)")
            params.append(cutoff_at)
        if series_contract_id is not None:
            clauses.append("series_contract_id=?")
            params.append(series_contract_id)
        cursor = self.connection.execute(
            f"""
            SELECT * EXCLUDE (row_number_value,recorded_at)
            FROM (
                SELECT revisions.*,
                       row_number() OVER (
                           PARTITION BY series_contract_id,observation_period
                           ORDER BY {clock} DESC,knowledge_at DESC,fetched_at DESC,
                                    macro_observation_revision_id DESC
                       ) AS row_number_value
                FROM silver.macro_observation_revisions revisions
                WHERE {' AND '.join(clauses)}
            )
            WHERE row_number_value=1
            ORDER BY series_contract_id,observation_period
            """,
            params,
        )
        columns = [item[0] for item in cursor.description]
        return [dict(zip(columns, row, strict=True)) | {"query_mode": query_mode}
                for row in cursor.fetchall()]

    def record_profile_snapshot(
        self,
        *,
        profile_id: str,
        profile_version: str,
        evaluation_at: datetime,
        metric_set_version: str,
        query_mode: str,
        definition_set_hash: str,
        series_revision_lineage: list[dict[str, Any]],
        metric_values: list[dict[str, Any]],
        missing_coverage: list[dict[str, Any]],
        rights_summary: dict[str, Any],
        attribution: list[str],
        quality_status: str,
    ) -> str:
        if evaluation_at.tzinfo is None or query_mode not in QUERY_MODES:
            raise ValueError("macro profile requires an aware cutoff and explicit query mode")
        if quality_status not in {"pass", "partial", "missing", "stale", "rights_blocked", "failed"}:
            raise ValueError("unsupported macro profile quality status")
        if len(definition_set_hash) != 64:
            raise ValueError("macro profile definition set hash must be SHA-256")
        document = {
            "profile_id": profile_id,
            "profile_version": profile_version,
            "evaluation_at": evaluation_at,
            "metric_set_version": metric_set_version,
            "query_mode": query_mode,
            "definition_set_hash": definition_set_hash,
            "series_revision_lineage": series_revision_lineage,
            "metric_values": metric_values,
            "missing_coverage": missing_coverage,
            "rights_summary": rights_summary,
            "attribution": attribution,
            "quality_status": quality_status,
        }
        snapshot_id = _digest("macro-profile-snapshot", document)
        natural_key = [profile_id, profile_version, evaluation_at, metric_set_version]
        prior = self.connection.execute(
            """
            SELECT macro_profile_snapshot_id FROM gold.macro_profile_snapshots
            WHERE profile_id=? AND profile_version=? AND evaluation_at=?
              AND metric_set_version=?
            """,
            natural_key,
        ).fetchone()
        if prior is not None:
            if prior[0] != snapshot_id:
                raise ValueError("macro profile replay conflicts with its immutable evaluation key")
            return snapshot_id
        self.connection.execute(
            """
            INSERT INTO gold.macro_profile_snapshots(
                macro_profile_snapshot_id,profile_id,profile_version,evaluation_at,
                metric_set_version,query_mode,definition_set_hash,series_revision_lineage,
                metric_values,missing_coverage,rights_summary,attribution,quality_status
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            [
                snapshot_id, *natural_key, query_mode, definition_set_hash,
                _json(series_revision_lineage), _json(metric_values),
                _json(missing_coverage), _json(rights_summary), _json(attribution),
                quality_status,
            ],
        )
        return snapshot_id
