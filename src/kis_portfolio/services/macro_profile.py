"""Offline macro profile metrics and fail-closed inactive pipeline guardrails."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Mapping

import duckdb

from kis_portfolio.modules.market.macro import MacroMetricResult, MacroSeriesDefinition


PIPELINE_ID = "pipeline.macro-profile-v2"
PIPELINE_VERSION = "2.0.0"
SOURCE_LIMITS = {
    ("source.fred-alfred", "routine"): 32,
    ("source.fred-alfred", "backfill"): 256,
    ("source.bok-ecos", "routine"): 16,
    ("source.bok-ecos", "backfill"): 96,
}
MAX_PARTITION_PAGES = 10
BRONZE_STOP_BYTES = 512 * 1024 * 1024
SILVER_STOP_ROWS = 500_000
GOLD_STOP_ROWS = 100_000


@dataclass(frozen=True, slots=True)
class MacroCallPlan:
    source_id: str
    mode: str
    partition_pages: Mapping[str, int]

    @property
    def physical_calls(self) -> int:
        return sum(self.partition_pages.values())

    @property
    def plan_hash(self) -> str:
        document = {
            "pipeline_id": PIPELINE_ID,
            "pipeline_version": PIPELINE_VERSION,
            "source_id": self.source_id,
            "mode": self.mode,
            "partition_pages": dict(sorted(self.partition_pages.items())),
        }
        return hashlib.sha256(
            json.dumps(document, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()


def validate_call_plan(plan: MacroCallPlan) -> MacroCallPlan:
    limit = SOURCE_LIMITS.get((plan.source_id, plan.mode))
    if limit is None:
        raise ValueError("unsupported macro source or collection mode")
    if not plan.partition_pages:
        raise ValueError("macro call plan requires fixed series partitions")
    if any(not key.strip() or pages < 0 for key, pages in plan.partition_pages.items()):
        raise ValueError("macro call plan contains an invalid partition")
    if any(pages > MAX_PARTITION_PAGES for pages in plan.partition_pages.values()):
        raise ValueError("macro series partition exceeds the ten-page cap")
    if plan.physical_calls > limit:
        raise ValueError("macro call plan exceeds its physical-call budget")
    return plan


def require_production_activation(definition: MacroSeriesDefinition) -> None:
    """Fail closed before any future source adapter performs I/O."""

    if definition.activation_state != "production":
        raise RuntimeError("macro source calls remain inactive until the production gate opens")


def validate_capacity(*, bronze_bytes: int, silver_rows: int, gold_rows: int) -> str:
    if min(bronze_bytes, silver_rows, gold_rows) < 0:
        raise ValueError("macro capacity counters cannot be negative")
    if bronze_bytes > BRONZE_STOP_BYTES:
        raise ValueError("macro Bronze exceeds the 512 MiB stop line")
    if silver_rows > SILVER_STOP_ROWS:
        raise ValueError("macro Silver exceeds the 500000-row stop line")
    if gold_rows > GOLD_STOP_ROWS:
        raise ValueError("macro Gold exceeds the 100000-row stop line")
    review = (
        bronze_bytes * 5 >= BRONZE_STOP_BYTES * 4
        or silver_rows * 5 >= SILVER_STOP_ROWS * 4
        or gold_rows * 5 >= GOLD_STOP_ROWS * 4
    )
    return "review" if review else "pass"


def _unknown(metric_id: str, reason: str, *revision_ids: str) -> MacroMetricResult:
    return MacroMetricResult(
        metric_id=metric_id,
        metric_version="1.0.0",
        quality_status="unknown",
        unknown_reason=reason,
        input_revision_ids=tuple(revision_ids),
    )


def yoy_percent_change(
    current: Decimal | None,
    prior_year: Decimal | None,
    *,
    revision_ids: tuple[str, ...] = (),
) -> MacroMetricResult:
    metric_id = "metric.macro-yoy-percent-change"
    if current is None or prior_year is None:
        return _unknown(metric_id, "missing_input", *revision_ids)
    if prior_year == 0:
        return _unknown(metric_id, "zero_denominator", *revision_ids)
    return MacroMetricResult(
        metric_id, "1.0.0", "pass",
        value=((current / prior_year) - Decimal(1)) * Decimal(100),
        input_revision_ids=revision_ids,
    )


def period_delta(
    current: Decimal | None,
    prior: Decimal | None,
    *,
    revision_ids: tuple[str, ...] = (),
) -> MacroMetricResult:
    metric_id = "metric.macro-period-delta"
    if current is None or prior is None:
        return _unknown(metric_id, "missing_input", *revision_ids)
    return MacroMetricResult(
        metric_id, "1.0.0", "pass", value=current - prior,
        input_revision_ids=revision_ids,
    )


def quarterly_annualized_growth(
    current: Decimal | None,
    prior: Decimal | None,
    *,
    revision_ids: tuple[str, ...] = (),
) -> MacroMetricResult:
    metric_id = "metric.macro-quarterly-annualized-growth"
    if current is None or prior is None:
        return _unknown(metric_id, "missing_input", *revision_ids)
    if current <= 0 or prior <= 0:
        return _unknown(metric_id, "non_positive_input", *revision_ids)
    return MacroMetricResult(
        metric_id, "1.0.0", "pass",
        value=(((current / prior) ** 4) - Decimal(1)) * Decimal(100),
        input_revision_ids=revision_ids,
    )


def yield_curve_state(
    spread: Decimal | None,
    *,
    revision_ids: tuple[str, ...] = (),
) -> MacroMetricResult:
    metric_id = "metric.macro-yield-curve-state"
    if spread is None:
        return _unknown(metric_id, "missing_input", *revision_ids)
    label = "inverted" if spread < 0 else "flat" if spread == 0 else "positive"
    return MacroMetricResult(
        metric_id, "1.0.0", "pass", value=spread, label=label,
        input_revision_ids=revision_ids,
    )


def vix_regime(
    value: Decimal | None,
    *,
    revision_ids: tuple[str, ...] = (),
) -> MacroMetricResult:
    metric_id = "metric.macro-vix-regime"
    if value is None:
        return _unknown(metric_id, "missing_input", *revision_ids)
    if value < 20:
        label = "below_20"
    elif value < 30:
        label = "20_to_below_30"
    elif value < 40:
        label = "30_to_below_40"
    else:
        label = "40_or_above"
    return MacroMetricResult(
        metric_id, "1.0.0", "pass", value=value, label=label,
        input_revision_ids=revision_ids,
    )


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
    if status not in {"pass", "partial", "failed", "missing", "stale", "rights_blocked"}:
        raise ValueError("unsupported macro quality status")
    if evaluated_at.tzinfo is None:
        raise ValueError("macro quality evaluation time must be timezone-aware")
    governed_partition = f"{source_id}|{partition_key}"
    quality_result_id = hashlib.sha256(
        f"{run_id}|dataset.macro-observation|{governed_partition}|{rule_id}".encode()
    ).hexdigest()
    connection.execute(
        """
        INSERT INTO control.quality_results(
            quality_result_id,run_id,dataset_id,rule_id,status,observed_value,
            expected_value,details,evaluated_at
        ) VALUES (?,?,'dataset.macro-observation',?,?,?,?,?,?)
        ON CONFLICT(quality_result_id) DO NOTHING
        """,
        [quality_result_id, run_id, rule_id, status, observed_value,
         expected_value, json.dumps({"partition_key": governed_partition}), evaluated_at],
    )
    return quality_result_id


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
    if observed_at.tzinfo is None:
        raise ValueError("macro watermark observation time must be timezone-aware")
    governed_partition = f"{source_id}|{partition_key}"
    quality = connection.execute(
        """
        SELECT run_id,status,details FROM control.quality_results
        WHERE quality_result_id=? AND dataset_id='dataset.macro-observation'
        """,
        [quality_result_id],
    ).fetchone()
    if quality is None:
        raise ValueError("macro watermark requires governed quality evidence")
    details = json.loads(quality[2]) if isinstance(quality[2], str) else dict(quality[2] or {})
    if quality[0] != run_id or details.get("partition_key") != governed_partition:
        raise ValueError("macro quality evidence does not match the run partition")
    if quality[1] != "pass":
        return False
    prior = connection.execute(
        """
        SELECT watermark_value FROM control.watermarks
        WHERE pipeline_id=? AND partition_key=? AND watermark_type='source_cursor'
        """,
        [PIPELINE_ID, governed_partition],
    ).fetchone()
    if prior is not None and watermark_value < str(prior[0]):
        raise ValueError("macro watermark cannot move backwards")
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
        [PIPELINE_ID, governed_partition, watermark_value, run_id, observed_at],
    )
    return True
