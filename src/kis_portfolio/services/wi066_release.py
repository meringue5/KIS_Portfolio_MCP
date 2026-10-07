"""Protected WI-066 migration, backup, restore, and quality verification."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import duckdb

from kis_portfolio.adapters.outbound.gcs_object_store import GCSObjectStore
from kis_portfolio.config import get_db_mode, get_motherduck_database
from kis_portfolio.db.connection import get_connection
from kis_portfolio.platform.migrations import MigrationRunner
from kis_portfolio.services.v2_recovery import (
    download_v2_backup,
    export_v2_backup,
    restore_v2_backup,
    upload_v2_backup,
)


MAX_BACKUP_BYTES = 10 * 1024**3
MAX_ELAPSED_SECONDS = 60 * 60


@dataclass(frozen=True, slots=True)
class WI066ReleaseConfig:
    project: str
    bucket: str


def _state_evidence(connection: duckdb.DuckDBPyConnection) -> dict[str, int]:
    row_count, fingerprint = connection.execute(
        """
        SELECT count(*), coalesce(bit_xor(hash(
            evaluation_date,evaluation_slot,account_id,instrument_id,aggregate_level,
            quantity,value_krw,cost_krw,unrealized_pnl_krw,contribution_pct,
            allocation_pct,as_of,input_watermarks,quality_status,lineage_hash
        )),0)
        FROM gold.portfolio_daily_state
        """
    ).fetchone()
    return {"row_count": int(row_count), "fingerprint": int(fingerprint)}


def _summary_evidence(connection: duckdb.DuckDBPyConnection) -> dict[str, int]:
    row = connection.execute(
        """
        SELECT
            count(*) FILTER (WHERE evaluation_slot='v1-latest') AS legacy_groups,
            count(*) FILTER (
                WHERE evaluation_slot='v1-latest'
                  AND total_value_krw IS NULL
                  AND quality_status='legacy_unassessed'
            ) AS legacy_quarantined_groups,
            count(*) FILTER (WHERE evaluation_slot<>'v1-latest') AS native_groups,
            count(*) FILTER (
                WHERE evaluation_slot<>'v1-latest'
                  AND (
                    (quality_status='pass' AND total_value_krw IS NOT NULL)
                    OR (quality_status='degraded' AND total_value_krw IS NULL)
                  )
            ) AS native_valid_groups
        FROM gold.portfolio_daily_summary
        """
    ).fetchone()
    evidence = {
        "legacy_groups": int(row[0]),
        "legacy_quarantined_groups": int(row[1]),
        "native_groups": int(row[2]),
        "native_valid_groups": int(row[3]),
    }
    if evidence["legacy_groups"] < 1:
        raise RuntimeError("WI-066 expected retained legacy history but found none")
    if evidence["legacy_quarantined_groups"] != evidence["legacy_groups"]:
        raise RuntimeError("WI-066 legacy history quarantine is incomplete")
    if evidence["native_groups"] < 1:
        raise RuntimeError("WI-066 expected current V2-native history but found none")
    if evidence["native_valid_groups"] != evidence["native_groups"]:
        raise RuntimeError("WI-066 native history projection is invalid")
    return evidence


def _backup_summary(uploaded: dict[str, Any]) -> dict[str, Any]:
    return {
        "index_sha256": uploaded["index_sha256"],
        "object_count": int(uploaded["object_count"]),
        "byte_size": int(uploaded["byte_size"]),
    }


def _backup_round_trip(
    *,
    connection: duckdb.DuckDBPyConnection,
    store: GCSObjectStore,
    root: Path,
    label: str,
) -> tuple[dict[str, Any], dict[str, Any], Path]:
    backup_dir = root / label
    manifest = export_v2_backup(connection, backup_dir, database=get_motherduck_database())
    uploaded = upload_v2_backup(store, backup_dir)
    downloaded = root / f"{label}-download"
    download_v2_backup(
        store,
        index_uri=uploaded["index_uri"],
        index_sha256=uploaded["index_sha256"],
        destination=downloaded,
    )
    restored_database = root / f"{label}-restore.duckdb"
    restore_v2_backup(downloaded, restored_database)
    return manifest, uploaded, restored_database


def run_wi066_release(
    config: WI066ReleaseConfig,
    *,
    connection_factory: Callable[[], duckdb.DuckDBPyConnection] = get_connection,
    store_factory: Callable[[str], GCSObjectStore] = lambda bucket: GCSObjectStore(
        bucket, prefix="recovery/wi066"
    ),
) -> dict[str, Any]:
    """Back up, apply 0020, verify quarantine, restore, and emit aggregate evidence."""
    started = time.monotonic()
    if get_db_mode() != "motherduck":
        raise RuntimeError("WI-066 release requires KIS_DB_MODE=motherduck")
    image_digest = os.getenv("KIS_RELEASE_IMAGE_DIGEST", "")
    git_sha = os.getenv("KIS_RELEASE_GIT_SHA", "")
    if not image_digest.startswith("sha256:") or len(git_sha) < 7:
        raise RuntimeError("WI-066 release requires immutable image and Git SHA provenance")

    connection = connection_factory()
    runner = MigrationRunner(connection)
    runner.require("0019")
    current_version = connection.execute(
        "SELECT max(version) FROM control.schema_migrations"
    ).fetchone()[0]
    if current_version not in {"0019", "0020"}:
        raise RuntimeError(f"WI-066 release found unsupported migration ceiling: {current_version}")

    store = store_factory(config.bucket)
    with tempfile.TemporaryDirectory(prefix="kis-wi066-") as temporary:
        root = Path(temporary)
        root.chmod(0o700)
        state_before = _state_evidence(connection)
        pre_manifest, pre_upload, _ = _backup_round_trip(
            connection=connection, store=store, root=root, label="pre",
        )

        applied_migrations = runner.apply(through="0020")
        if applied_migrations not in ([], ["0020"]):
            raise RuntimeError(f"WI-066 applied unexpected migrations: {applied_migrations}")
        if runner.apply(through="0020"):
            raise RuntimeError("WI-066 migration replay was not idempotent")
        state_after = _state_evidence(connection)
        if state_after != state_before:
            raise RuntimeError("WI-066 view-only migration changed portfolio state rows")
        summary_evidence = _summary_evidence(connection)

        post_manifest, post_upload, restored_database = _backup_round_trip(
            connection=connection, store=store, root=root, label="post",
        )
        restored = duckdb.connect(str(restored_database), read_only=True)
        try:
            restored_state = _state_evidence(restored)
            restored_summary = _summary_evidence(restored)
        finally:
            restored.close()
        if restored_state != state_after or restored_summary != summary_evidence:
            raise RuntimeError("WI-066 restored history evidence differs from live")

    elapsed = time.monotonic() - started
    for uploaded in (pre_upload, post_upload):
        if int(uploaded["byte_size"]) > MAX_BACKUP_BYTES:
            raise RuntimeError("WI-066 backup exceeds the approved storage bound")
    if elapsed > MAX_ELAPSED_SECONDS:
        raise RuntimeError("WI-066 release exceeded the approved one-hour objective")

    evidence = {
        "status": "succeeded",
        "applied_migrations": applied_migrations,
        "pre_migration": pre_manifest["source_migrations"][-1]["version"],
        "post_migration": post_manifest["source_migrations"][-1]["version"],
        "state_before": state_before,
        "state_after": state_after,
        "summary_evidence": summary_evidence,
        "pre_backup": _backup_summary(pre_upload),
        "post_backup": _backup_summary(post_upload),
        "view_replaced": True,
        "source_calls": 0,
        "data_rows_mutated": 0,
        "deletions": 0,
        "elapsed_seconds": round(elapsed, 3),
        "release_image_digest": image_digest,
        "release_git_sha": git_sha,
    }
    stored = store.put_bytes(
        json.dumps(evidence, sort_keys=True).encode(),
        dataset_id="backup.wi066-release-evidence",
        partition="run-" + hashlib.sha256(
            f"{git_sha}|{post_upload['index_sha256']}".encode()
        ).hexdigest()[:24],
        media_type="application/json",
    )
    return {
        **evidence,
        "evidence_uri": stored.uri,
        "evidence_sha256": stored.content_hash,
    }
