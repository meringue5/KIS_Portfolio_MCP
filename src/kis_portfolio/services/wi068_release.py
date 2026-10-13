"""Protected additive WI-068 import with private pre/post backups and fresh restore."""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import duckdb

from kis_portfolio.adapters.outbound.gcs_object_store import GCSObjectStore
from kis_portfolio.config import get_db_mode
from kis_portfolio.db.connection import get_connection
from kis_portfolio.platform.migrations import MigrationRunner
from kis_portfolio.services.legacy_total_reference import APPROVED_SHA256, import_candidate
from kis_portfolio.services.wi066_release import (
    MAX_BACKUP_BYTES, MAX_ELAPSED_SECONDS, _backup_round_trip, _backup_summary,
    _state_evidence, _summary_evidence,
)


@dataclass(frozen=True, slots=True)
class WI068ReleaseConfig:
    project: str
    bucket: str


def _reference_evidence(connection: duckdb.DuckDBPyConnection) -> dict:
    rows = connection.execute("""SELECT valuation_kind,count(*) FROM silver.portfolio_legacy_total_reference
        WHERE source_object_hash=? AND canonical=false GROUP BY valuation_kind ORDER BY valuation_kind""",
        [APPROVED_SHA256]).fetchall()
    counts = dict(rows)
    if counts != {"recorded_reference":14, "estimated_reference":11, "unavailable_total":2}:
        raise RuntimeError("WI-068 imported reference coverage differs from approval")
    count, fingerprint = connection.execute("""SELECT count(*),bit_xor(hash(
        observation_date,recovery_version,input_content_hash,recorded_total_krw,reference_total_krw,
        added_foreign_value_krw,valuation_kind,assumptions,coverage_reasons,original_snapshot_at,
        fx_provenance,knowledge_at,source_object_hash,canonical))
        FROM silver.portfolio_legacy_total_reference""").fetchone()
    return {"counts":counts,"row_count":int(count),"fingerprint":int(fingerprint)}


def run_wi068_release(config: WI068ReleaseConfig, *,
    connection_factory: Callable[[], duckdb.DuckDBPyConnection] = get_connection,
    store_factory: Callable[[str], GCSObjectStore] = lambda bucket: GCSObjectStore(bucket, prefix="recovery/wi068"),
) -> dict:
    started = time.monotonic()
    if get_db_mode() != "motherduck":
        raise RuntimeError("WI-068 requires MotherDuck mode")
    git_sha, image = os.getenv("KIS_RELEASE_GIT_SHA", ""), os.getenv("KIS_RELEASE_IMAGE_DIGEST", "")
    if len(git_sha) < 7 or not image.startswith("sha256:"):
        raise RuntimeError("WI-068 requires immutable release provenance")
    connection = connection_factory()
    runner = MigrationRunner(connection)
    runner.require("0020")
    ceiling = connection.execute("SELECT max(version) FROM control.schema_migrations").fetchone()[0]
    if ceiling not in {"0020", "0021"}:
        raise RuntimeError("WI-068 unsupported migration ceiling")
    store = store_factory(config.bucket)
    with tempfile.TemporaryDirectory(prefix="kis-wi068-") as temporary:
        root = Path(temporary)
        root.chmod(0o700)
        input_file = root / "reviewed.json"
        # Fixed approved object identity: no arbitrary URI or runtime-source selection.
        name = store._object_name(APPROVED_SHA256, "backup.wi068-input", "approved-v1")
        store.download(f"gs://{config.bucket}/{name}", input_file, expected_sha256=APPROVED_SHA256)
        input_file.chmod(0o600)
        from kis_portfolio.services.legacy_total_reference import validate_candidate
        validate_candidate(input_file.read_bytes())
        before, summary_before = _state_evidence(connection), _summary_evidence(connection)
        pre, pre_upload, _ = _backup_round_trip(connection=connection, store=store, root=root, label="pre")
        if pre_upload["byte_size"] > MAX_BACKUP_BYTES:
            raise RuntimeError("WI-068 pre backup storage bound exceeded")
        applied = runner.apply(through="0021")
        if applied not in ([], ["0021"]):
            raise RuntimeError("WI-068 unexpected migrations")
        imported = import_candidate(connection, input_file)
        if import_candidate(connection, input_file)["inserted"] != 0 or runner.apply(through="0021"):
            raise RuntimeError("WI-068 replay not idempotent")
        after, summary_after = _state_evidence(connection), _summary_evidence(connection)
        if before != after or summary_before != summary_after:
            raise RuntimeError("WI-068 native state or quarantine changed")
        references = _reference_evidence(connection)
        post, post_upload, restored_path = _backup_round_trip(connection=connection, store=store, root=root, label="post")
        with duckdb.connect(str(restored_path), read_only=True) as restored:
            if (_state_evidence(restored) != after or _summary_evidence(restored) != summary_after
                    or _reference_evidence(restored) != references):
                raise RuntimeError("WI-068 fresh restore differs from live")
        if post_upload["byte_size"] > MAX_BACKUP_BYTES or time.monotonic()-started > MAX_ELAPSED_SECONDS:
            raise RuntimeError("WI-068 recovery budget exceeded")
    evidence = {"status":"succeeded","applied_migrations":applied,
        "pre_migration":pre["source_migrations"][-1]["version"],
        "post_migration":post["source_migrations"][-1]["version"],
        "import":imported,"references":references,"state_before":before,"state_after":after,
        "summary_evidence":summary_after,"pre_backup":_backup_summary(pre_upload),
        "post_backup":_backup_summary(post_upload),"fresh_restore_verified":True,
        "source_calls":0,"original_rows_mutated":0,"deletions":0,
        "release_git_sha":git_sha,"release_image_digest":image,
        "elapsed_seconds":round(time.monotonic()-started,3)}
    stored = store.put_bytes(json.dumps(evidence,sort_keys=True).encode(),
        dataset_id="backup.wi068-release-evidence",partition="run-"+hashlib.sha256(
            f"{git_sha}|{post_upload['index_sha256']}".encode()).hexdigest()[:24],media_type="application/json")
    return {**evidence,"evidence_sha256":stored.content_hash}
