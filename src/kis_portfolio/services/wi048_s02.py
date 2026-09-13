"""Protected production transition from retained V1 references to the V2 control plane."""

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
from kis_portfolio.services.v1_main_transition import (
    REFERENCE_TRANSITIONS,
    transition_v1_reference_data,
)
from kis_portfolio.services.v2_recovery import (
    download_v2_backup,
    export_v2_backup,
    restore_v2_backup,
    upload_v2_backup,
)


MAX_BACKUP_BYTES = 10 * 1024**3
MAX_ELAPSED_SECONDS = 60 * 60


@dataclass(frozen=True, slots=True)
class WI048S02Config:
    project: str
    bucket: str


def _table_evidence(connection: duckdb.DuckDBPyConnection) -> dict[str, dict[str, int]]:
    evidence: dict[str, dict[str, int]] = {}
    for transition in REFERENCE_TRANSITIONS:
        columns = ",".join(transition.columns)
        count, fingerprint = connection.execute(
            f"SELECT count(*),coalesce(bit_xor(hash({columns})),0) FROM control.{transition.name}"
        ).fetchone()
        evidence[f"control.{transition.name}"] = {
            "rows": int(count),
            "fingerprint": int(fingerprint),
        }
    return evidence


def _backup_round_trip(
    *,
    connection: duckdb.DuckDBPyConnection,
    store: GCSObjectStore,
    root: Path,
    label: str,
) -> tuple[dict[str, Any], dict[str, Any], Path]:
    backup_dir = root / label
    manifest = export_v2_backup(
        connection,
        backup_dir,
        database=get_motherduck_database(),
    )
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


def run_wi048_s02(
    config: WI048S02Config,
    *,
    connection_factory: Callable[[], duckdb.DuckDBPyConnection] = get_connection,
    store_factory: Callable[[str], GCSObjectStore] = lambda bucket: GCSObjectStore(
        bucket, prefix="recovery/wi048"
    ),
) -> dict[str, Any]:
    """Back up, transition, reconcile, restore and retain aggregate-only evidence."""
    started = time.monotonic()
    if get_db_mode() != "motherduck":
        raise RuntimeError("WI-048-S02 requires KIS_DB_MODE=motherduck")
    image_digest = os.getenv("KIS_RELEASE_IMAGE_DIGEST", "")
    git_sha = os.getenv("KIS_RELEASE_GIT_SHA", "")
    if not image_digest.startswith("sha256:") or len(git_sha) < 7:
        raise RuntimeError("WI-048-S02 requires immutable release image and Git SHA provenance")

    connection = connection_factory()
    MigrationRunner(connection).require("0018")
    store = store_factory(config.bucket)
    with tempfile.TemporaryDirectory(prefix="kis-wi048-s02-") as temporary:
        root = Path(temporary)
        root.chmod(0o700)
        pre_manifest, pre_upload, _ = _backup_round_trip(
            connection=connection,
            store=store,
            root=root,
            label="pre",
        )

        applied_migrations = MigrationRunner(connection).apply(through="0019")
        first = transition_v1_reference_data(connection, apply=True)
        second = transition_v1_reference_data(connection, apply=True)
        if first["status"] != "reconciled" or second["status"] != "reconciled":
            raise RuntimeError("WI-048-S02 reference transition did not reconcile")
        live_evidence = _table_evidence(connection)

        post_manifest, post_upload, restored_database = _backup_round_trip(
            connection=connection,
            store=store,
            root=root,
            label="post",
        )
        restored = duckdb.connect(str(restored_database), read_only=True)
        try:
            restored_evidence = _table_evidence(restored)
        finally:
            restored.close()
        if restored_evidence != live_evidence:
            raise RuntimeError("WI-048-S02 restored reference evidence differs from live")

    elapsed = time.monotonic() - started
    for uploaded in (pre_upload, post_upload):
        if int(uploaded["byte_size"]) > MAX_BACKUP_BYTES:
            raise RuntimeError("WI-048-S02 backup exceeds the approved storage bound")
    if elapsed > MAX_ELAPSED_SECONDS:
        raise RuntimeError("WI-048-S02 exceeded the approved one-hour objective")

    evidence = {
        "status": "succeeded",
        "applied_migrations": applied_migrations,
        "reference_tables": live_evidence,
        "idempotent_replay": True,
        "pre_backup": pre_upload,
        "post_backup": post_upload,
        "pre_migration": pre_manifest["source_migrations"][-1]["version"],
        "post_migration": post_manifest["source_migrations"][-1]["version"],
        "source_calls": 0,
        "source_mutations": 0,
        "deletions": 0,
        "elapsed_seconds": round(elapsed, 3),
        "release_image_digest": image_digest,
        "release_git_sha": git_sha,
    }
    stored = store.put_bytes(
        json.dumps(evidence, sort_keys=True).encode(),
        dataset_id="backup.wi048-s02-evidence",
        partition="run-" + hashlib.sha256(f"{git_sha}|{post_upload['index_sha256']}".encode()).hexdigest()[:24],
        media_type="application/json",
    )
    return {
        **evidence,
        "evidence_uri": stored.uri,
        "evidence_sha256": stored.content_hash,
    }
