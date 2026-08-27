"""DB-only governance, quality and lineage read models."""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

import duckdb


class GovernanceReadModel:
    def __init__(self, connection: duckdb.DuckDBPyConnection, repo_root: Path) -> None:
        self.connection = connection
        self.repo_root = repo_root

    def catalog(self, *, include_proposed: bool = False) -> dict[str, list[dict[str, Any]]]:
        output: dict[str, list[dict[str, Any]]] = {}
        for kind in ("sources", "datasets", "collections", "pipelines"):
            path = self.repo_root / "governance/catalog" / f"{kind}.toml"
            records = tomllib.loads(path.read_text(encoding="utf-8")).get("contracts", [])
            if not include_proposed:
                records = [record for record in records if record.get("status") in {"approved", "active"}]
            output[kind] = records
        return output

    def quality(self, run_id: str) -> list[dict[str, Any]]:
        cursor = self.connection.execute("""
            SELECT dataset_id, rule_id, status, observed_value, expected_value, details, evaluated_at
            FROM control.quality_results WHERE run_id=? ORDER BY dataset_id, rule_id
        """, [run_id])
        columns = [item[0] for item in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def lineage(self, run_id: str) -> list[dict[str, Any]]:
        cursor = self.connection.execute("""
            SELECT input_ref, output_ref, transform_id, transform_version, evidence_hash, created_at
            FROM control.lineage_edges WHERE run_id=? ORDER BY created_at, input_ref
        """, [run_id])
        columns = [item[0] for item in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def pipeline_status(self, run_id: str) -> dict[str, Any] | None:
        cursor = self.connection.execute("SELECT * FROM control.pipeline_run_summary WHERE run_id=?", [run_id])
        row = cursor.fetchone()
        if row is None:
            return None
        return dict(zip([item[0] for item in cursor.description], row))
