"""Owner-only forward consensus contracts for the approved Alpha source."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal


SOURCE_ID = "source.alpha-vantage-personal"
DATASET_ID = "dataset.alpha-vantage-consensus-forward-snapshot"
PIPELINE_ID = "pipeline.alpha-vantage-consensus-forward-v1"
METRICS = frozenset({"eps", "revenue"})


@dataclass(frozen=True, slots=True)
class ConsensusForwardSnapshot:
    definition_hash: str
    issuer_id: str
    provider_forecast_date: date
    horizon: str
    metric: str
    estimate_average: Decimal
    estimate_high: Decimal
    estimate_low: Decimal
    analyst_count: int
    us_session_date: date
    fetched_at: datetime
    source_request_ref: str
    content_hash: str
    average_7_days_ago: Decimal | None = None
    average_30_days_ago: Decimal | None = None
    average_60_days_ago: Decimal | None = None
    average_90_days_ago: Decimal | None = None
    revision_up_trailing_7_days: int | None = None
    revision_up_trailing_30_days: int | None = None
    revision_down_trailing_7_days: int | None = None
    revision_down_trailing_30_days: int | None = None
    source_id: str = SOURCE_ID
    quality_status: str = "pass"


@dataclass(frozen=True, slots=True)
class ConsensusNormalizationResult:
    rows: tuple[ConsensusForwardSnapshot, ...]
    status: str
    missing_reason: str | None = None


def validate_snapshot(value: ConsensusForwardSnapshot) -> None:
    if value.source_id != SOURCE_ID:
        raise ValueError("forward consensus requires the approved Alpha source")
    if len(value.definition_hash) != 64 or len(value.content_hash) != 64:
        raise ValueError("forward consensus contract and content hashes must be SHA-256")
    if len(value.source_request_ref) != 64:
        raise ValueError("forward consensus request reference must be opaque SHA-256")
    if not value.issuer_id.strip() or not value.horizon.strip() or len(value.horizon) > 80:
        raise ValueError("forward consensus issuer and bounded horizon are required")
    if any(character in value.horizon for character in "\r\n\t"):
        raise ValueError("forward consensus horizon must be a single bounded label")
    if value.metric not in METRICS:
        raise ValueError("forward consensus metric must be EPS or revenue")
    if value.quality_status != "pass":
        raise ValueError("only complete forward consensus rows may enter Silver")
    if value.fetched_at.tzinfo is None:
        raise ValueError("forward consensus fetched_at must be timezone-aware")
    if value.us_session_date > value.fetched_at.date():
        raise ValueError("forward consensus cannot use a future U.S. session")
    if value.analyst_count <= 0:
        raise ValueError("forward consensus requires a positive analyst count")
    if not value.estimate_low <= value.estimate_average <= value.estimate_high:
        raise ValueError("forward consensus average must remain inside the observed range")
    counts = (
        value.revision_up_trailing_7_days,
        value.revision_up_trailing_30_days,
        value.revision_down_trailing_7_days,
        value.revision_down_trailing_30_days,
    )
    if any(item is not None and item < 0 for item in counts):
        raise ValueError("forward consensus revision counts cannot be negative")
    comparisons = (
        value.average_7_days_ago,
        value.average_30_days_ago,
        value.average_60_days_ago,
        value.average_90_days_ago,
    )
    if value.metric == "eps" and any(item is None for item in comparisons):
        raise ValueError("EPS forward consensus requires all provider rolling averages")
    if value.metric == "revenue" and any(item is not None for item in comparisons + counts):
        raise ValueError("revenue rows must not invent unsupported rolling fields")
