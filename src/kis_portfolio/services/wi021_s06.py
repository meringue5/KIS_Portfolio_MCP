"""Fail-closed WI-021-S06 production backfill and recovery orchestration."""

from __future__ import annotations

import json
import os
import tempfile
import time
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Callable

import duckdb

from kis_portfolio.account_registry import load_account_registry
from kis_portfolio.adapters.outbound.gcs_object_store import GCSObjectStore
from kis_portfolio.config import get_db_mode, get_motherduck_database
from kis_portfolio.db.connection import get_connection
from kis_portfolio.platform.migrations import MigrationRunner
from kis_portfolio.services.trade_cash_backfill import (
    DOMESTIC_ORDER_HISTORY,
    OVERSEAS_ORDER_HISTORY,
    OVERSEAS_TRANSACTION_HISTORY,
    BackfillBudgetPolicy,
    account_scopes_from_registry,
    apply_call_budget,
    plan_trade_cash_backfill,
)
from kis_portfolio.services.trade_cash_backfill_pipeline import build_trade_cash_partition_handler
from kis_portfolio.services.trade_cash_backfill_runtime import (
    BACKFILL_SLOT,
    PIPELINE_ID,
    PIPELINE_VERSION,
    WATERMARK_TYPE,
    execute_trade_cash_backfill,
)
from kis_portfolio.services.trade_cash_backfill_source import KisTradeCashBackfillSource
from kis_portfolio.services.v2_recovery import (
    download_v2_backup,
    export_v2_backup,
    restore_v2_backup,
    upload_v2_backup,
)


MAX_LITE_STORAGE_BYTES = 10 * 1024**3
MAX_RECOVERY_ELAPSED_SECONDS = 4 * 60 * 60


@dataclass(frozen=True, slots=True)
class WI021S06Config:
    start_date: date
    end_date: date
    as_of_date: date
    expected_plan_hash: str
    expected_budget_hash: str
    project: str
    bucket: str
    max_physical_calls: int = 400
    expected_partitions: int = 131
    expected_quality_rows: int = 262
    expected_lineage_rows: int = 150
    expected_watermark_streams: int = 11


def _plan(config: WI021S06Config):
    accounts = load_account_registry()
    source_plan = plan_trade_cash_backfill(
        account_scopes_from_registry(
            accounts,
            overseas_account_labels=("brokerage",),
            overseas_exchanges=("NAS",),
        ),
        start_date=config.start_date,
        end_date=config.end_date,
        as_of_date=config.as_of_date,
    )
    plan = apply_call_budget(
        source_plan,
        policy=BackfillBudgetPolicy(
            max_physical_calls=config.max_physical_calls,
            page_limits=(
                (DOMESTIC_ORDER_HISTORY, 3),
                (OVERSEAS_ORDER_HISTORY, 3),
                (OVERSEAS_TRANSACTION_HISTORY, 2),
            ),
        ),
    )
    if plan.source_plan.plan_hash != config.expected_plan_hash:
        raise RuntimeError("WI-021-S06 plan hash drifted from the approved preflight")
    if plan.budget_hash != config.expected_budget_hash:
        raise RuntimeError("WI-021-S06 budget hash drifted from the approved preflight")
    if len(plan.source_plan.callable_partitions) != config.expected_partitions:
        raise RuntimeError("WI-021-S06 callable partition count drifted")
    return accounts, plan


def _stage_evidence(connection: duckdb.DuckDBPyConnection, config: WI021S06Config) -> list[dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT r.partition_key, r.status, s.status, s.source_calls, s.input_count,
               s.output_count, s.evidence
        FROM control.pipeline_runs r
        LEFT JOIN control.pipeline_stage_runs s
          ON s.run_id=r.run_id AND s.stage_name='collect-land-normalize'
        WHERE r.pipeline_id=? AND r.pipeline_version=? AND r.logical_date=? AND r.slot=?
        ORDER BY r.partition_key
        """,
        [PIPELINE_ID, PIPELINE_VERSION, config.end_date, BACKFILL_SLOT],
    ).fetchall()
    result = []
    for partition_key, run_status, stage_status, calls, input_count, output_count, evidence in rows:
        payload = json.loads(evidence) if evidence else {}
        result.append({
            "partition_key": partition_key,
            "run_status": run_status,
            "stage_status": stage_status,
            "source_calls": int(calls or 0),
            "input_count": int(input_count or 0),
            "output_count": int(output_count or 0),
            "evidence": payload,
        })
    return result


def reconcile_wi021_s06(
    connection: duckdb.DuckDBPyConnection,
    config: WI021S06Config,
) -> dict[str, Any]:
    """Return aggregate-only evidence and fail if any production invariant is broken."""

    stages = _stage_evidence(connection, config)
    source_calls = sum(item["source_calls"] for item in stages)
    per_partition_violations = 0
    raw_rows = trade_events = cash_events = 0
    evidence_failures = 0
    for item in stages:
        operation = item["partition_key"].split("|")[1]
        limit = {
            DOMESTIC_ORDER_HISTORY: 3,
            OVERSEAS_ORDER_HISTORY: 3,
            OVERSEAS_TRANSACTION_HISTORY: 2,
        }.get(operation, 0)
        per_partition_violations += int(item["source_calls"] > limit)
        reconciliation = item["evidence"].get("reconciliation", {})
        raw_rows += int(reconciliation.get("raw_rows", 0))
        trade_events += int(reconciliation.get("trade_events", 0))
        cash_events += int(reconciliation.get("cash_events", 0))
        evidence_failures += int(
            item["evidence"].get("plan_hash") != config.expected_plan_hash
            or item["evidence"].get("budget_hash") != config.expected_budget_hash
            or reconciliation.get("status") != "pass"
            or not reconciliation.get("pagination_complete", False)
            or reconciliation.get("pagination_warning") is not None
            or item["input_count"] != int(reconciliation.get("raw_rows", -1))
            or item["output_count"] != int(reconciliation.get("trade_events", -1))
            + int(reconciliation.get("cash_events", -1))
        )

    target = """
        SELECT run_id FROM control.pipeline_runs
        WHERE pipeline_id=? AND pipeline_version=? AND logical_date=? AND slot=?
    """
    parameters = [PIPELINE_ID, PIPELINE_VERSION, config.end_date, BACKFILL_SLOT]
    stage_rows = connection.execute(
        f"SELECT status, count(*) FROM control.pipeline_stage_runs WHERE run_id IN ({target}) GROUP BY status",
        parameters,
    ).fetchall()
    quality_rows, nonpass_quality = connection.execute(
        f"""
        SELECT count(*), count(*) FILTER (WHERE status <> 'pass')
        FROM control.quality_results WHERE run_id IN ({target})
        """,
        parameters,
    ).fetchone()
    lineage_rows, invalid_lineage = connection.execute(
        f"""
        SELECT count(*), count(*) FILTER (
          WHERE transform_id <> 'trade-cash-backfill-normalize'
             OR transform_version <> '1.0.0'
             OR output_ref NOT IN ('dataset.trade-event', 'dataset.cash-transaction-event')
        )
        FROM control.lineage_edges WHERE run_id IN ({target})
        """,
        parameters,
    ).fetchone()
    watermark_streams, foreign_watermarks = connection.execute(
        f"""
        SELECT count(*), count(*) FILTER (WHERE run_id NOT IN ({target}))
        FROM control.watermarks
        WHERE pipeline_id=? AND watermark_type=?
        """,
        [*parameters, PIPELINE_ID, WATERMARK_TYPE],
    ).fetchone()
    bronze_trade, bronze_cash = connection.execute(
        f"""
        SELECT
          count(*) FILTER (WHERE dataset_id='dataset.trade-event'),
          count(*) FILTER (WHERE dataset_id='dataset.cash-transaction-event')
        FROM bronze.source_observations WHERE pipeline_run_id IN ({target})
        """,
        parameters,
    ).fetchone()
    silver_trade, silver_cash, purchase_lots = connection.execute(
        f"""
        WITH observations AS (
          SELECT observation_id FROM bronze.source_observations
          WHERE pipeline_run_id IN ({target})
        )
        SELECT
          (SELECT count(*) FROM silver.trade_events WHERE source_observation_id IN (SELECT observation_id FROM observations)),
          (SELECT count(*) FROM silver.cash_flow_events WHERE source_observation_id IN (SELECT observation_id FROM observations)),
          (SELECT count(*) FROM silver.purchase_lots l JOIN silver.trade_events e USING (trade_event_id)
             WHERE e.source_observation_id IN (SELECT observation_id FROM observations))
        """,
        parameters,
    ).fetchone()

    summary = {
        "partition_count": len(stages),
        "succeeded_partitions": sum(item["run_status"] == "succeeded" for item in stages),
        "failed_partitions": sum(item["run_status"] == "failed" for item in stages),
        "source_calls": source_calls,
        "per_partition_budget_violations": per_partition_violations,
        "stage_status_counts": {status: count for status, count in stage_rows},
        "quality_rows": int(quality_rows),
        "nonpass_quality_rows": int(nonpass_quality),
        "lineage_rows": int(lineage_rows),
        "invalid_lineage_rows": int(invalid_lineage),
        "watermark_streams": int(watermark_streams),
        "foreign_watermark_refs": int(foreign_watermarks),
        "raw_rows": raw_rows,
        "trade_events": trade_events,
        "cash_events": cash_events,
        "bronze_trade_observations": int(bronze_trade),
        "bronze_cash_observations": int(bronze_cash),
        "silver_trade_events": int(silver_trade),
        "silver_cash_events": int(silver_cash),
        "purchase_lots": int(purchase_lots),
        "evidence_failures": evidence_failures,
    }
    failures = []
    if len(stages) != config.expected_partitions or summary["succeeded_partitions"] != config.expected_partitions:
        failures.append("partition completion")
    if summary["failed_partitions"] or source_calls > config.max_physical_calls or per_partition_violations:
        failures.append("call budget")
    if summary["stage_status_counts"] != {"succeeded": config.expected_partitions * 3}:
        failures.append("stage completion")
    if quality_rows != config.expected_quality_rows or nonpass_quality:
        failures.append("quality evidence")
    if lineage_rows != config.expected_lineage_rows or invalid_lineage:
        failures.append("lineage evidence")
    if watermark_streams != config.expected_watermark_streams or foreign_watermarks:
        failures.append("watermark evidence")
    if (bronze_trade, bronze_cash, silver_trade, silver_cash, purchase_lots) != (
        raw_rows, cash_events, trade_events, cash_events, 0,
    ):
        failures.append("Bronze/Silver reconciliation")
    if evidence_failures:
        failures.append("partition evidence")
    if failures:
        raise RuntimeError("WI-021-S06 reconciliation failed: " + ", ".join(failures))
    return summary


def _manifest_counts(manifest: dict[str, Any]) -> dict[str, int]:
    return {name: int(item["rows"]) for name, item in manifest["tables"].items()}


def run_wi021_s06(
    config: WI021S06Config,
    *,
    connection_factory: Callable[[], duckdb.DuckDBPyConnection] = get_connection,
    store_factory: Callable[[str], GCSObjectStore] = lambda bucket: GCSObjectStore(bucket, prefix="recovery"),
) -> dict[str, Any]:
    """Execute the approved production sequence; pre-recovery completes before KIS I/O."""

    started = time.monotonic()
    if get_db_mode() != "motherduck":
        raise RuntimeError("WI-021-S06 requires KIS_DB_MODE=motherduck")
    accounts, plan = _plan(config)
    image_digest = os.getenv("KIS_RELEASE_IMAGE_DIGEST", "")
    git_sha = os.getenv("KIS_RELEASE_GIT_SHA", "")
    if not image_digest.startswith("sha256:") or len(git_sha) < 7:
        raise RuntimeError("WI-021-S06 requires immutable release image and Git SHA provenance")

    workspace = tempfile.TemporaryDirectory(prefix="kis-wi021-s06-")
    root = Path(workspace.name)
    root.chmod(0o700)
    store = store_factory(config.bucket)
    connection = connection_factory()
    MigrationRunner(connection).require("0008")

    pre_dir = root / f"{root.name}-pre"
    pre_manifest = export_v2_backup(connection, pre_dir, database=get_motherduck_database())
    pre_upload = upload_v2_backup(store, pre_dir)
    pre_download = root / "pre-download"
    download_v2_backup(
        store,
        index_uri=pre_upload["index_uri"],
        index_sha256=pre_upload["index_sha256"],
        destination=pre_download,
    )
    restore_v2_backup(pre_download, root / "pre-restore.duckdb")

    source = KisTradeCashBackfillSource(accounts)
    handler = build_trade_cash_partition_handler(connection, source.fetch)
    outcome = execute_trade_cash_backfill(connection, plan, handler)
    live_reconciliation = reconcile_wi021_s06(connection, config)

    post_dir = root / f"{root.name}-post"
    post_manifest = export_v2_backup(connection, post_dir, database=get_motherduck_database())
    post_upload = upload_v2_backup(store, post_dir)
    post_download = root / "post-download"
    download_v2_backup(
        store,
        index_uri=post_upload["index_uri"],
        index_sha256=post_upload["index_sha256"],
        destination=post_download,
    )
    restored_database = root / "post-restore.duckdb"
    restore_v2_backup(post_download, restored_database)
    restored = duckdb.connect(str(restored_database), read_only=True)
    try:
        restored_reconciliation = reconcile_wi021_s06(restored, config)
    finally:
        restored.close()
    if restored_reconciliation != live_reconciliation:
        raise RuntimeError("isolated restore reconciliation differs from live aggregate evidence")

    elapsed = time.monotonic() - started
    if pre_upload["byte_size"] > MAX_LITE_STORAGE_BYTES or post_upload["byte_size"] > MAX_LITE_STORAGE_BYTES:
        raise RuntimeError("V2 recovery point exceeds the approved MotherDuck Lite storage bound")
    if elapsed > MAX_RECOVERY_ELAPSED_SECONDS:
        raise RuntimeError("WI-021-S06 exceeded the approved four-hour recovery objective")
    pre_counts = _manifest_counts(pre_manifest)
    post_counts = _manifest_counts(post_manifest)
    evidence = {
        "status": "succeeded",
        "plan_hash": plan.source_plan.plan_hash,
        "budget_hash": plan.budget_hash,
        "callable_partitions": len(plan.source_plan.callable_partitions),
        "known_gaps": len(plan.source_plan.known_gaps),
        "reused_partitions": sum(item.reused for item in outcome.partition_outcomes),
        "reconciliation": live_reconciliation,
        "pre_backup": pre_upload,
        "post_backup": post_upload,
        "table_row_deltas": {name: post_counts[name] - pre_counts[name] for name in sorted(pre_counts)},
        "elapsed_seconds": round(elapsed, 3),
        "release_image_digest": image_digest,
        "release_git_sha": git_sha,
    }
    stored = store.put_bytes(
        json.dumps(evidence, sort_keys=True).encode(),
        dataset_id="backup.wi021-s06-evidence",
        partition=post_dir.name,
        media_type="application/json",
    )
    return {
        **evidence,
        "evidence_uri": stored.uri,
        "evidence_sha256": stored.content_hash,
    }
