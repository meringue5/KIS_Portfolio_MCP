"""Post-migration private backup and restore verification for WI-029-S04."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

import duckdb

from kis_portfolio.adapters.outbound.gcs_object_store import GCSObjectStore
from kis_portfolio.platform.migrations import MigrationRunner
from kis_portfolio.services.v2_recovery import (
    download_v2_backup,
    export_v2_backup,
    restore_v2_backup,
    upload_v2_backup,
)


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
    }
