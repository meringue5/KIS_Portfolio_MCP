"""Fail-closed planning and capacity guards for the inactive dividend pipeline."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Mapping

import duckdb


PIPELINE_ID = "pipeline.dividend-ledger-v1"
PIPELINE_VERSION = "1.0.0"
CALL_LIMITS = {"routine": 64, "backfill": 320}
MAX_PAGES_PER_PARTITION = 10
MAX_PRIVATE_OBJECT_BYTES = 1024 * 1024 * 1024
MAX_SILVER_ROWS = 500_000


@dataclass(frozen=True, slots=True)
class DividendCallPlan:
    mode: str
    partition_calls: Mapping[str, int]
    partition_pages: Mapping[str, int]

    @property
    def physical_calls(self) -> int:
        return sum(self.partition_calls.values())

    @property
    def plan_hash(self) -> str:
        document = {
            "pipeline_id": PIPELINE_ID,
            "version": PIPELINE_VERSION,
            "mode": self.mode,
            "partition_calls": dict(sorted(self.partition_calls.items())),
            "partition_pages": dict(sorted(self.partition_pages.items())),
        }
        return hashlib.sha256(
            json.dumps(document, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()


def validate_call_plan(plan: DividendCallPlan) -> DividendCallPlan:
    limit = CALL_LIMITS.get(plan.mode)
    if limit is None:
        raise ValueError("dividend plan mode must be routine or backfill")
    if not plan.partition_calls or set(plan.partition_pages) != set(plan.partition_calls):
        raise ValueError("dividend plan requires exact call and page partitions")
    if any(not key.strip() or calls < 0 for key, calls in plan.partition_calls.items()):
        raise ValueError("dividend plan contains an invalid partition or call count")
    if any(pages < 0 or pages > MAX_PAGES_PER_PARTITION for pages in plan.partition_pages.values()):
        raise ValueError("dividend partition exceeds the ten-page limit")
    if plan.physical_calls > limit:
        raise ValueError("dividend plan exceeds its physical-call budget")
    return plan


def validate_capacity(*, private_object_bytes: int, silver_rows: int) -> None:
    if private_object_bytes < 0 or silver_rows < 0:
        raise ValueError("dividend capacity counters cannot be negative")
    if private_object_bytes > MAX_PRIVATE_OBJECT_BYTES:
        raise ValueError("dividend private object capacity exceeds 1 GiB")
    if silver_rows > MAX_SILVER_ROWS:
        raise ValueError("dividend Silver capacity exceeds 500000 rows")


def record_partition_quality(
    connection: duckdb.DuckDBPyConnection,
    *,
    run_id: str,
    partition_key: str,
    status: str,
    observed_value: str,
    expected_value: str,
    evaluated_at: datetime,
) -> str:
    if status not in {"pass", "partial", "failed", "quarantined"}:
        raise ValueError("unsupported dividend quality status")
    if evaluated_at.tzinfo is None:
        raise ValueError("dividend quality time must be timezone-aware")
    quality_result_id = hashlib.sha256(
        f"{run_id}|dataset.dividend-reconciliation|{partition_key}".encode()
    ).hexdigest()
    connection.execute(
        """
        INSERT INTO control.quality_results(
            quality_result_id,run_id,dataset_id,rule_id,status,observed_value,
            expected_value,details,evaluated_at
        ) VALUES (?,?,'dataset.dividend-reconciliation','dividend_partition_complete',?,?,?,?,?)
        ON CONFLICT(quality_result_id) DO NOTHING
        """,
        [quality_result_id, run_id, status, observed_value, expected_value,
         json.dumps({"partition_key": partition_key}, sort_keys=True), evaluated_at],
    )
    return quality_result_id


def publish_partition_watermark(
    connection: duckdb.DuckDBPyConnection,
    *,
    run_id: str,
    partition_key: str,
    watermark_value: str,
    quality_result_id: str,
    observed_at: datetime,
) -> bool:
    if observed_at.tzinfo is None:
        raise ValueError("dividend watermark time must be timezone-aware")
    quality = connection.execute(
        """SELECT run_id,status,details FROM control.quality_results
           WHERE quality_result_id=? AND dataset_id='dataset.dividend-reconciliation'""",
        [quality_result_id],
    ).fetchone()
    if not quality:
        raise ValueError("dividend watermark requires governed quality evidence")
    details = json.loads(quality[2]) if isinstance(quality[2], str) else dict(quality[2] or {})
    if quality[0] != run_id or details.get("partition_key") != partition_key:
        raise ValueError("dividend quality evidence does not match the run partition")
    if quality[1] != "pass":
        return False
    existing = connection.execute(
        """SELECT watermark_value FROM control.watermarks
           WHERE pipeline_id=? AND partition_key=? AND watermark_type='source_cursor'""",
        [PIPELINE_ID, partition_key],
    ).fetchone()
    if existing is not None and watermark_value < existing[0]:
        raise ValueError("dividend watermark cannot move backwards")
    connection.execute(
        """
        INSERT INTO control.watermarks(
            pipeline_id,partition_key,watermark_type,watermark_value,run_id,updated_at
        ) VALUES (?,?,'source_cursor',?,?,?)
        ON CONFLICT(pipeline_id,partition_key,watermark_type) DO UPDATE SET
            watermark_value=excluded.watermark_value,
            run_id=excluded.run_id,
            updated_at=excluded.updated_at
        """,
        [PIPELINE_ID, partition_key, watermark_value, run_id, observed_at],
    )
    return True
