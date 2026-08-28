"""Fail-closed WI-022-S06 production reconstruction and recovery orchestration."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

import duckdb

from kis_portfolio.adapters.outbound.gcs_object_store import GCSObjectStore
from kis_portfolio.adapters.outbound.position_reconstruction_warehouse import (
    PositionReconstructionWarehouseRepository,
    ReconstructionWriteResult,
)
from kis_portfolio.config import get_db_mode, get_motherduck_database
from kis_portfolio.db.connection import get_connection
from kis_portfolio.platform.migrations import MigrationRunner
from kis_portfolio.services.position_reconstruction_runtime import (
    ReconstructionExecutionPlan,
    build_reconstruction_execution_plan,
)
from kis_portfolio.services.v2_recovery import (
    download_v2_backup,
    export_v2_backup,
    restore_v2_backup,
    upload_v2_backup,
)


MAX_LITE_STORAGE_BYTES = 10 * 1024**3
MAX_RECOVERY_ELAPSED_SECONDS = 60 * 60


@dataclass(frozen=True, slots=True)
class WI022S06Config:
    start_at: datetime
    cutoff_at: datetime
    expected_execution_hash: str
    project: str
    bucket: str
    expected_partitions: int = 57
    expected_held_partitions: int = 22
    expected_trade_history_partitions: int = 56
    expected_trade_only_partitions: int = 35
    expected_position_rows: int = 22
    expected_trade_rows: int = 282
    expected_coverage_rows: int = 0
    expected_eligible_partitions: int = 0
    expected_exception_partitions: int = 57


def _validate_plan(config: WI022S06Config, plan: ReconstructionExecutionPlan) -> dict[str, Any]:
    report = plan.public_report()
    expected = {
        "execution_hash": config.expected_execution_hash,
        "partition_count": config.expected_partitions,
        "held_partition_count": config.expected_held_partitions,
        "trade_history_partition_count": config.expected_trade_history_partitions,
        "trade_only_partition_count": config.expected_trade_only_partitions,
        "input_position_rows": config.expected_position_rows,
        "input_trade_rows": config.expected_trade_rows,
        "coverage_rows": config.expected_coverage_rows,
        "eligible_projection_partitions": config.expected_eligible_partitions,
        "exception_only_partitions": config.expected_exception_partitions,
    }
    drift = {
        name: {"expected": value, "actual": report.get(name)}
        for name, value in expected.items()
        if report.get(name) != value
    }
    if drift:
        raise RuntimeError(
            "WI-022-S06 input drifted from the approved S05 aggregate: "
            + ", ".join(sorted(drift))
        )
    if report["source_calls"] != 0 or report["warehouse_writes"] != 0:
        raise RuntimeError("WI-022-S06 planner must remain read-only and source-free")
    if config.expected_eligible_partitions + config.expected_exception_partitions != config.expected_partitions:
        raise RuntimeError("WI-022-S06 approved outcome counts do not cover every partition")
    return report


def _manifest_counts(manifest: dict[str, Any]) -> dict[str, int]:
    return {name: int(item["rows"]) for name, item in manifest["tables"].items()}


def _sum_results(results: tuple[ReconstructionWriteResult, ...]) -> dict[str, int]:
    fields = (
        "episode_identities_inserted",
        "episode_revisions_inserted",
        "lot_identities_inserted",
        "lot_revisions_inserted",
        "allocation_revisions_inserted",
        "allocation_slices_inserted",
        "exception_identities_inserted",
        "exception_revisions_inserted",
        "exceptions_resolved",
    )
    return {name: sum(int(getattr(item, name)) for item in results) for name in fields}


def reconcile_wi022_s06(
    connection: duckdb.DuckDBPyConnection,
    config: WI022S06Config,
    plan: ReconstructionExecutionPlan,
) -> dict[str, Any]:
    """Return aggregate-only current-state evidence for the exact approved partitions."""

    _validate_plan(config, plan)
    eligible = tuple(item for item in plan.partitions if item.plan.assessment.eligible_for_reconciled_projection)
    blocked = tuple(item for item in plan.partitions if not item.plan.assessment.eligible_for_reconciled_projection)

    episode_rows = lot_rows = allocation_rows = open_exceptions = 0
    for item in eligible:
        for episode in item.plan.episodes:
            episode_rows += int(bool(connection.execute(
                "SELECT 1 FROM silver.position_episodes_current WHERE episode_id=?",
                [episode.episode_id],
            ).fetchone()))
        for lot in item.plan.lots:
            lot_rows += int(bool(connection.execute(
                "SELECT 1 FROM silver.purchase_lot_states_current WHERE lot_id=?",
                [lot.lot_id],
            ).fetchone()))
        for allocation in item.plan.allocations:
            allocation_rows += int(bool(connection.execute(
                "SELECT 1 FROM silver.sell_allocations_current WHERE allocation_id=?",
                [allocation.allocation_id],
            ).fetchone()))
    for item in blocked:
        open_exceptions += int(bool(connection.execute(
            """
            SELECT 1 FROM control.reconstruction_exceptions_current
            WHERE partition_key=? AND exception_status='open'
            """,
            [item.plan.partition_key],
        ).fetchone()))

    expected_episodes = sum(len(item.plan.episodes) for item in eligible)
    expected_lots = sum(len(item.plan.lots) for item in eligible)
    expected_allocations = sum(len(item.plan.allocations) for item in eligible)
    summary = {
        "partition_count": len(plan.partitions),
        "eligible_partitions": len(eligible),
        "exception_partitions": len(blocked),
        "current_episode_identities": episode_rows,
        "current_lot_identities": lot_rows,
        "current_allocation_identities": allocation_rows,
        "current_open_exceptions": open_exceptions,
    }
    if (episode_rows, lot_rows, allocation_rows, open_exceptions) != (
        expected_episodes,
        expected_lots,
        expected_allocations,
        len(blocked),
    ):
        raise RuntimeError("WI-022-S06 live reconstruction state does not reconcile with the approved plan")
    return summary


def _backup_round_trip(
    *,
    connection: duckdb.DuckDBPyConnection,
    store: GCSObjectStore,
    root: Path,
    label: str,
) -> tuple[dict[str, Any], dict[str, Any], Path]:
    backup_dir = root / f"{root.name}-{label}"
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


def run_wi022_s06(
    config: WI022S06Config,
    *,
    connection_factory: Callable[[], duckdb.DuckDBPyConnection] = get_connection,
    store_factory: Callable[[str], GCSObjectStore] = lambda bucket: GCSObjectStore(
        bucket, prefix="recovery"
    ),
) -> dict[str, Any]:
    """Apply one exact reviewed plan after private recovery proof and verify an isolated restore."""

    started = time.monotonic()
    if get_db_mode() != "motherduck":
        raise RuntimeError("WI-022-S06 requires KIS_DB_MODE=motherduck")
    if config.start_at.tzinfo is None or config.cutoff_at.tzinfo is None:
        raise RuntimeError("WI-022-S06 timestamps must be timezone-aware")
    knowledge_at = datetime.now(UTC)
    if knowledge_at <= config.cutoff_at:
        raise RuntimeError("WI-022-S06 cutoff must be in the past before append-only publication")
    image_digest = os.getenv("KIS_RELEASE_IMAGE_DIGEST", "")
    git_sha = os.getenv("KIS_RELEASE_GIT_SHA", "")
    if not image_digest.startswith("sha256:") or len(git_sha) < 7:
        raise RuntimeError("WI-022-S06 requires immutable release image and Git SHA provenance")

    workspace = tempfile.TemporaryDirectory(prefix="kis-wi022-s06-")
    root = Path(workspace.name)
    root.chmod(0o700)
    store = store_factory(config.bucket)
    connection = connection_factory()
    MigrationRunner(connection).require("0010")

    plan = build_reconstruction_execution_plan(
        connection,
        start_at=config.start_at,
        cutoff_at=config.cutoff_at,
    )
    plan_report = _validate_plan(config, plan)
    pre_manifest, pre_upload, _ = _backup_round_trip(
        connection=connection,
        store=store,
        root=root,
        label="pre",
    )

    repository = PositionReconstructionWarehouseRepository(connection)
    run_id = "wi022-s06-" + hashlib.sha256(
        f"{config.expected_execution_hash}|{git_sha}".encode()
    ).hexdigest()[:24]
    first = tuple(
        repository.persist(
            request=item.request,
            plan=item.plan,
            run_id=run_id,
            knowledge_at=knowledge_at,
            created_by="system:wi022-s06",
        )
        for item in plan.partitions
    )
    live_reconciliation = reconcile_wi022_s06(connection, config, plan)

    second = tuple(
        repository.persist(
            request=item.request,
            plan=item.plan,
            run_id=run_id + "-idempotency",
            knowledge_at=knowledge_at,
            created_by="system:wi022-s06",
        )
        for item in plan.partitions
    )
    if any(item.inserted_revision_count or item.exceptions_resolved for item in second):
        raise RuntimeError("WI-022-S06 identical replay was not idempotent")

    post_manifest, post_upload, restored_database = _backup_round_trip(
        connection=connection,
        store=store,
        root=root,
        label="post",
    )
    restored = duckdb.connect(str(restored_database), read_only=True)
    try:
        restored_plan = build_reconstruction_execution_plan(
            restored,
            start_at=config.start_at,
            cutoff_at=config.cutoff_at,
        )
        restored_reconciliation = reconcile_wi022_s06(restored, config, restored_plan)
    finally:
        restored.close()
    if restored_reconciliation != live_reconciliation:
        raise RuntimeError("isolated restore reconciliation differs from live aggregate evidence")

    elapsed = time.monotonic() - started
    if pre_upload["byte_size"] > MAX_LITE_STORAGE_BYTES or post_upload["byte_size"] > MAX_LITE_STORAGE_BYTES:
        raise RuntimeError("V2 recovery point exceeds the approved MotherDuck Lite storage bound")
    if elapsed > MAX_RECOVERY_ELAPSED_SECONDS:
        raise RuntimeError("WI-022-S06 exceeded the approved one-hour recovery objective")
    pre_counts = _manifest_counts(pre_manifest)
    post_counts = _manifest_counts(post_manifest)
    evidence = {
        "status": "succeeded",
        "execution_hash": plan.execution_hash,
        "plan": plan_report,
        "first_apply": _sum_results(first),
        "idempotent_replay": _sum_results(second),
        "reconciliation": live_reconciliation,
        "pre_backup": pre_upload,
        "post_backup": post_upload,
        "table_row_deltas": {name: post_counts[name] - pre_counts[name] for name in sorted(pre_counts)},
        "source_calls": 0,
        "elapsed_seconds": round(elapsed, 3),
        "release_image_digest": image_digest,
        "release_git_sha": git_sha,
    }
    stored = store.put_bytes(
        json.dumps(evidence, sort_keys=True).encode(),
        dataset_id="backup.wi022-s06-evidence",
        partition=post_manifest["created_at"].replace(":", "-").replace("+", "_").replace(".", "-"),
        media_type="application/json",
    )
    return {
        **evidence,
        "evidence_uri": stored.uri,
        "evidence_sha256": stored.content_hash,
    }
