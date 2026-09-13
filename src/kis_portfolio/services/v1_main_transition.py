"""Preservation-first transition of V1 reference data into the V2 control plane."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import duckdb

@dataclass(frozen=True, slots=True)
class ReferenceTransition:
    name: str
    columns: tuple[str, ...]
    key_columns: tuple[str, ...]


REFERENCE_TRANSITIONS = (
    ReferenceTransition(
        "market_calendar",
        (
            "market", "trade_date", "is_open", "open_time_local", "close_time_local",
            "timezone", "source", "note", "raw_data", "updated_at",
        ),
        ("market", "trade_date"),
    ),
    ReferenceTransition(
        "instrument_master",
        (
            "symbol", "market", "standard_code", "name", "group_code", "etp_code",
            "idx_large_code", "idx_mid_code", "idx_small_code", "raw_data", "updated_at",
        ),
        ("symbol", "market"),
    ),
    ReferenceTransition(
        "instrument_classification_overrides",
        (
            "symbol", "market", "exposure_type", "exposure_region", "asset_subtype",
            "reason", "updated_at",
        ),
        ("symbol", "market"),
    ),
)


def _exists(connection: Any, schema: str, table: str) -> bool:
    return bool(connection.execute(
        """
        SELECT count(*) FROM information_schema.tables
        WHERE table_schema=? AND table_name=? AND table_type='BASE TABLE'
        """,
        [schema, table],
    ).fetchone()[0])


def transition_v1_reference_data(
    connection: duckdb.DuckDBPyConnection,
    *,
    apply: bool = False,
) -> dict[str, object]:
    """Plan or apply an idempotent V1-main to V2-control reference copy.

    Source rows are never changed. The result intentionally contains only counts and
    object names so it is safe to retain as migration evidence.
    """
    ledger_exists = _exists(connection, "control", "schema_migrations")
    applied = ledger_exists and bool(connection.execute(
        "SELECT count(*) FROM control.schema_migrations WHERE version='0019'"
    ).fetchone()[0])
    if not applied:
        raise RuntimeError("required schema version is not applied: 0019")
    rows: list[dict[str, object]] = []
    missing_sources: list[str] = []
    for transition in REFERENCE_TRANSITIONS:
        if not _exists(connection, "main", transition.name):
            missing_sources.append(f"main.{transition.name}")
            rows.append({
                "source": f"main.{transition.name}",
                "target": f"control.{transition.name}",
                "source_rows": None,
                "target_rows_before": int(connection.execute(
                    f"SELECT count(*) FROM control.{transition.name}"
                ).fetchone()[0]),
                "status": "missing_source",
            })
            continue
        source_count = int(connection.execute(
            f"SELECT count(*) FROM main.{transition.name}"
        ).fetchone()[0])
        target_before = int(connection.execute(
            f"SELECT count(*) FROM control.{transition.name}"
        ).fetchone()[0])
        rows.append({
            "source": f"main.{transition.name}",
            "target": f"control.{transition.name}",
            "source_rows": source_count,
            "target_rows_before": target_before,
            "status": "planned" if not apply else "pending",
        })

    if apply and missing_sources:
        raise RuntimeError("required V1 reference sources are missing: " + ", ".join(missing_sources))
    if not apply:
        return {"status": "planned", "applied": False, "objects": rows, "side_effects": "none"}

    connection.execute("BEGIN TRANSACTION")
    try:
        for transition, evidence in zip(REFERENCE_TRANSITIONS, rows, strict=True):
            columns = ",".join(transition.columns)
            updates = ",".join(
                f"{column}=excluded.{column}"
                for column in transition.columns
                if column not in transition.key_columns
            )
            connection.execute(
                f"""
                INSERT INTO control.{transition.name} ({columns})
                SELECT {columns} FROM main.{transition.name}
                ON CONFLICT ({','.join(transition.key_columns)}) DO UPDATE SET {updates}
                """
            )
            missing_after = int(connection.execute(
                f"""
                SELECT count(*) FROM (
                    SELECT {columns} FROM main.{transition.name}
                    EXCEPT
                    SELECT {columns} FROM control.{transition.name}
                )
                """
            ).fetchone()[0])
            evidence["target_rows_after"] = int(connection.execute(
                f"SELECT count(*) FROM control.{transition.name}"
            ).fetchone()[0])
            evidence["unreconciled_source_rows"] = missing_after
            evidence["status"] = "reconciled" if missing_after == 0 else "mismatch"
        if any(item["status"] != "reconciled" for item in rows):
            raise RuntimeError("V1 reference transition reconciliation failed")
        connection.execute("COMMIT")
    except Exception:
        connection.execute("ROLLBACK")
        raise
    return {"status": "reconciled", "applied": True, "objects": rows, "source_mutations": 0}
