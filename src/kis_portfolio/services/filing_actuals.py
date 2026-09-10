"""Fail-closed planning and publish gates for the inactive filing pipeline."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Mapping

import duckdb


PIPELINE_ID = "pipeline.filing-actual-v1"
PIPELINE_VERSION = "1.0.0"
SOURCE_LIMITS = {
    ("source.opendart", "routine"): (100, 20),
    ("source.opendart", "backfill"): (250, 250),
    ("source.sec-edgar", "routine"): (64, 16),
    ("source.sec-edgar", "backfill"): (320, 320),
}


@dataclass(frozen=True, slots=True)
class FilingCallPlan:
    source_id: str
    mode: str
    partition_calls: Mapping[str, int]
    search_pages: Mapping[str, int]

    @property
    def physical_calls(self) -> int:
        return sum(self.partition_calls.values())

    @property
    def plan_hash(self) -> str:
        document = {
            "pipeline_id": PIPELINE_ID,
            "version": PIPELINE_VERSION,
            "source_id": self.source_id,
            "mode": self.mode,
            "partition_calls": dict(sorted(self.partition_calls.items())),
            "search_pages": dict(sorted(self.search_pages.items())),
        }
        return hashlib.sha256(
            json.dumps(document, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()


def validate_call_plan(plan: FilingCallPlan) -> FilingCallPlan:
    limits = SOURCE_LIMITS.get((plan.source_id, plan.mode))
    if limits is None:
        raise ValueError("unsupported filing source or collection mode")
    global_limit, issuer_limit = limits
    if not plan.partition_calls:
        raise ValueError("filing call plan requires a fixed issuer partition")
    if any(not key.strip() or value < 0 for key, value in plan.partition_calls.items()):
        raise ValueError("filing call plan contains an invalid partition")
    if plan.physical_calls > global_limit:
        raise ValueError("filing call plan exceeds its global physical-call budget")
    if any(value > issuer_limit for value in plan.partition_calls.values()):
        raise ValueError("filing call plan exceeds its issuer physical-call budget")
    if plan.source_id == "source.opendart" and plan.mode == "routine":
        if any(value < 0 or value > 2 for value in plan.search_pages.values()):
            raise ValueError("OpenDART routine search is limited to two pages per issuer")
    if set(plan.search_pages) - set(plan.partition_calls):
        raise ValueError("filing search page budget references an unknown partition")
    return plan


def publish_partition_watermark(
    connection: duckdb.DuckDBPyConnection,
    *,
    run_id: str,
    source_id: str,
    partition_key: str,
    watermark_value: str,
    quality_result_id: str,
    observed_at: datetime,
) -> bool:
    """Advance only a fully reconciled partition; failures retain the old watermark."""

    if observed_at.tzinfo is None:
        raise ValueError("filing watermark observation time must be timezone-aware")
    governed_partition = f"{source_id}|{partition_key}"
    quality = connection.execute(
        """
        SELECT run_id,status,details FROM control.quality_results
        WHERE quality_result_id=? AND dataset_id='dataset.filing-event'
        """,
        [quality_result_id],
    ).fetchone()
    if quality is None:
        raise ValueError("filing watermark requires governed quality evidence")
    quality_details = json.loads(quality[2]) if isinstance(quality[2], str) else dict(quality[2] or {})
    if quality[0] != run_id or quality_details.get("partition_key") != governed_partition:
        raise ValueError("filing quality evidence does not match the run partition")
    if quality[1] != "pass":
        return False
    existing = connection.execute(
        """
        SELECT watermark_value FROM control.watermarks
        WHERE pipeline_id=? AND partition_key=? AND watermark_type='source_cursor'
        """,
        [PIPELINE_ID, governed_partition],
    ).fetchone()
    if existing is not None and str(watermark_value) < str(existing[0]):
        raise ValueError("filing watermark cannot move backwards")
    connection.execute(
        """
        INSERT INTO control.watermarks(
            pipeline_id,partition_key,watermark_type,watermark_value,
            run_id,updated_at
        ) VALUES (?,?,'source_cursor',?,?,?)
        ON CONFLICT(pipeline_id,partition_key,watermark_type) DO UPDATE SET
            watermark_value=excluded.watermark_value,
            updated_at=excluded.updated_at,
            run_id=excluded.run_id
        """,
        [PIPELINE_ID, governed_partition, watermark_value, run_id, observed_at],
    )
    return True


def record_partition_quality(
    connection: duckdb.DuckDBPyConnection,
    *,
    run_id: str,
    source_id: str,
    partition_key: str,
    rule_id: str,
    status: str,
    observed_value: str,
    expected_value: str,
    evaluated_at: datetime,
) -> str:
    if status not in {"pass", "partial", "failed", "quarantined"}:
        raise ValueError("unsupported filing quality status")
    if evaluated_at.tzinfo is None:
        raise ValueError("filing quality evaluation time must be timezone-aware")
    governed_partition = f"{source_id}|{partition_key}"
    quality_result_id = hashlib.sha256(
        f"{run_id}|dataset.filing-event|{governed_partition}|{rule_id}".encode()
    ).hexdigest()
    connection.execute(
        """
        INSERT INTO control.quality_results(
            quality_result_id,run_id,dataset_id,rule_id,status,observed_value,
            expected_value,details,evaluated_at
        ) VALUES (?,?,'dataset.filing-event',?,?,?,?,?,?)
        ON CONFLICT(quality_result_id) DO NOTHING
        """,
        [quality_result_id, run_id, rule_id, status, observed_value, expected_value,
         json.dumps({"partition_key": governed_partition}, sort_keys=True), evaluated_at],
    )
    return quality_result_id
