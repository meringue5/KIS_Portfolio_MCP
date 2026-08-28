"""Post-migration private backup and restore verification for WI-029-S04."""

from __future__ import annotations

import tempfile
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import duckdb

from kis_portfolio.adapters.outbound.alert_calibration_warehouse import (
    AlertCalibrationWarehouse,
)
from kis_portfolio.adapters.outbound.gcs_object_store import GCSObjectStore
from kis_portfolio.application.signal_replay import calibrate_price_history
from kis_portfolio.platform.migrations import MigrationRunner
from kis_portfolio.services.shadow_alerts import (
    CALIBRATION_REPORT_HASH,
    RULE_ID,
    RULE_VERSION,
)
from kis_portfolio.services.v2_recovery import (
    download_v2_backup,
    export_v2_backup,
    restore_v2_backup,
    upload_v2_backup,
)


REPLAY_START = date(2023, 8, 28)
REPLAY_END = date(2026, 8, 27)
SHADOW_START = date(2026, 8, 28)
SHADOW_END = date(2026, 9, 10)


def persist_wi029_s04_evidence(
    connection: duckdb.DuckDBPyConnection,
    *,
    recorded_at: datetime | None = None,
) -> dict[str, Any]:
    """Freeze the approved replay and create the collecting two-week shadow window."""
    now = recorded_at or datetime.now(UTC)
    if now.tzinfo is None:
        raise ValueError("recorded_at must be timezone-aware")
    result = calibrate_price_history(
        connection,
        start_date=REPLAY_START,
        end_date=REPLAY_END,
        price_basis="adjusted",
    )
    if result.report_hash != CALIBRATION_REPORT_HASH:
        raise RuntimeError("WI-029 calibration evidence drifted from the approved report")
    repository = AlertCalibrationWarehouse(connection)
    calibration = repository.write_calibration(result)
    initial_expected = tuple(
        f"{session_key}|{evaluation_slot}"
        for session_key, evaluation_slot in connection.execute(
            """
            SELECT DISTINCT session_key,evaluation_slot
            FROM gold.alert_candidates
            WHERE rule_id=? AND rule_version=?
              AND evaluation_date BETWEEN ? AND ?
            ORDER BY session_key,evaluation_slot
            """,
            [RULE_ID, RULE_VERSION, SHADOW_START, SHADOW_END],
        ).fetchall()
    )
    if not initial_expected:
        raise RuntimeError("WI-029 shadow window cannot start without an observed governed slot")
    evidence = repository.build_shadow_evidence(
        rule_set_id=RULE_ID,
        rule_set_version=RULE_VERSION,
        window_start=SHADOW_START,
        window_end=SHADOW_END,
        expected_session_keys=initial_expected,
        owner_review_complete=False,
    )
    shadow_status = repository.write_shadow_evidence(evidence, updated_at=now)
    if shadow_status != "collecting":
        raise RuntimeError("WI-029 shadow window started in an unexpected state")
    return {
        "calibration_run_id": calibration.calibration_run_id,
        "calibration_inserted": calibration.inserted,
        "calibration_report_hash": result.report_hash,
        "shadow_window_id": evidence.shadow_window_id,
        "shadow_window_status": shadow_status,
        "shadow_window_start": SHADOW_START.isoformat(),
        "shadow_window_end": SHADOW_END.isoformat(),
        "initial_observed_session_count": len(evidence.observed_session_keys),
        "initial_candidate_count": evidence.candidate_count,
        "initial_quality_suppressed_count": evidence.quality_suppressed_count,
        "initial_external_send_count": evidence.external_send_count,
    }


def verify_wi029_s04(
    connection: duckdb.DuckDBPyConnection,
    *,
    project: str,
    bucket: str,
) -> dict[str, Any]:
    MigrationRunner(connection).require("0013")
    external_rule_count = int(connection.execute(
        "SELECT count(*) FROM control.alert_rule_versions WHERE delivery_mode='external'"
    ).fetchone()[0])
    telegram_claim_count = int(connection.execute(
        "SELECT count(*) FROM control.alert_dispatch_claims WHERE channel='telegram'"
    ).fetchone()[0])
    if external_rule_count or telegram_claim_count:
        raise RuntimeError("WI-029 shadow activation found an external delivery path")
    evidence = persist_wi029_s04_evidence(connection)
    store = GCSObjectStore(bucket, prefix="recovery")
    with tempfile.TemporaryDirectory(prefix="kis-wi029-s04-") as temporary:
        root = Path(temporary)
        backup_dir = root / "post-migration"
        manifest = export_v2_backup(connection, backup_dir, database="kis_portfolio")
        uploaded = upload_v2_backup(store, backup_dir)
        restored_dir = root / "downloaded"
        downloaded = download_v2_backup(
            store,
            index_uri=uploaded["index_uri"],
            index_sha256=uploaded["index_sha256"],
            destination=restored_dir,
        )
        restored = restore_v2_backup(restored_dir, root / "restored.duckdb")
    return {
        "status": "verified",
        "project": project,
        "migration": "0013",
        "backup_table_count": len(manifest["tables"]),
        "backup_index_uri": uploaded["index_uri"],
        "backup_index_sha256": uploaded["index_sha256"],
        "uploaded_object_count": uploaded["object_count"],
        "downloaded_object_count": downloaded["object_count"],
        "restored_table_count": restored["tables"],
        "external_rule_count": external_rule_count,
        "telegram_claim_count": telegram_claim_count,
        "evidence": evidence,
    }
