"""Explicit, source-preserving alert-slot migration with private recovery verification."""
from __future__ import annotations

import os
from pathlib import Path
import tempfile

import duckdb

from kis_portfolio.adapters.outbound.gcs_object_store import GCSObjectStore
from kis_portfolio.config import get_db_mode
from kis_portfolio.db.catalog import v2_backup_table_names
from kis_portfolio.db.connection import get_connection
from kis_portfolio.platform.migrations import MigrationRunner
from kis_portfolio.services.wi066_release import MAX_BACKUP_BYTES, _backup_round_trip, _backup_summary


def fingerprints(connection):
    return {
        name: connection.execute(f"SELECT count(*),bit_xor(hash(t)) FROM {name} t").fetchone()
        for name in v2_backup_table_names() if name != "control.schema_migrations"
    }


def run_wi078_release(*, bucket, connection_factory=get_connection,
                      store_factory=lambda bucket: GCSObjectStore(bucket, prefix="recovery/wi078")):
    image = os.getenv("KIS_RELEASE_IMAGE_DIGEST", "")
    sha = os.getenv("KIS_RELEASE_GIT_SHA", "")
    if get_db_mode() != "motherduck" or not image.startswith("sha256:") or len(sha) < 7:
        raise RuntimeError("wi078_release_provenance_required")
    connection = connection_factory()
    try:
        runner = MigrationRunner(connection)
        runner.require("0023")
        if max(runner.applied()) not in {"0023", "0024"}:
            raise RuntimeError("wi078_migration_ceiling_unsupported")
        before = fingerprints(connection)
        with tempfile.TemporaryDirectory(prefix="kis-wi078-") as tmp:
            root = Path(tmp)
            root.chmod(0o700)
            store = store_factory(bucket)
            _, pre_upload, pre_path = _backup_round_trip(
                connection=connection, store=store, root=root, label="pre")
            if pre_upload["byte_size"] > MAX_BACKUP_BYTES:
                raise RuntimeError("wi078_backup_budget_exceeded")
            with duckdb.connect(str(pre_path)) as restored:
                MigrationRunner(restored).apply(through="0024")
                if fingerprints(restored) != before:
                    raise RuntimeError("wi078_rehearsal_changed_rows")
            applied = runner.apply(through="0024")
            if applied not in ([], ["0024"]) or fingerprints(connection) != before:
                raise RuntimeError("wi078_migration_changed_rows")
            _, post_upload, post_path = _backup_round_trip(
                connection=connection, store=store, root=root, label="post")
            if post_upload["byte_size"] > MAX_BACKUP_BYTES:
                raise RuntimeError("wi078_backup_budget_exceeded")
            with duckdb.connect(str(post_path), read_only=True) as restored:
                if fingerprints(restored) != before:
                    raise RuntimeError("wi078_post_restore_mismatch")
            return dict(status="verified", applied_migrations=applied,
                        preserved_tables=len(before), pre_backup=_backup_summary(pre_upload),
                        post_backup=_backup_summary(post_upload), git_sha=sha, image_digest=image)
    finally:
        connection.close()
