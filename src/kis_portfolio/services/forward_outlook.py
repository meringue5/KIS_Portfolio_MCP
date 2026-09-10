"""Inactive Alpha forward-outlook planning, quality and analysis guardrails."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Iterable

import duckdb

from kis_portfolio.modules.market.consensus import (
    DATASET_ID,
    PIPELINE_ID,
    ConsensusForwardSnapshot,
    validate_snapshot,
)
from kis_portfolio.platform.consensus_registry import ConsensusContractBundle


CURRENT_SCOPE_CALLS = 4
MAX_PROVIDER_DAY_CALLS = 8
ACCOUNT_FREE_DAY_LIMIT = 25
MIN_CALL_SPACING_SECONDS = 15
SILVER_STOP_ROWS = 500_000
PRIVATE_BACKUP_STOP_BYTES = 512 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class HeldIssuerCandidate:
    issuer_id: str
    instrument_id: str
    provider_symbol: str
    market: str
    asset_type: str
    economic_exposure: str
    currency: str
    quantity: Decimal
    quality_status: str


@dataclass(frozen=True, slots=True)
class TermsReview:
    reviewed_on: date
    expires_on: date
    evidence_hash: str
    status: str = "approved"


@dataclass(frozen=True, slots=True)
class ConsensusCallPlan:
    issuer_ids: tuple[str, ...]
    provider_symbols: tuple[str, ...]
    provider_day: date
    spacing_seconds: int = MIN_CALL_SPACING_SECONDS
    retry_count: int = 0

    @property
    def physical_calls(self) -> int:
        return len(self.issuer_ids)

    @property
    def scope_status(self) -> str:
        return "current" if self.physical_calls <= CURRENT_SCOPE_CALLS else "expanded_within_hard_max"

    @property
    def plan_hash(self) -> str:
        document = {
            "pipeline_id": PIPELINE_ID,
            "issuer_ids": self.issuer_ids,
            "provider_symbols": self.provider_symbols,
            "provider_day": self.provider_day,
            "spacing_seconds": self.spacing_seconds,
            "retry_count": self.retry_count,
        }
        return hashlib.sha256(
            json.dumps(document, sort_keys=True, separators=(",", ":"), default=str).encode()
        ).hexdigest()


@dataclass(frozen=True, slots=True)
class ForwardRevisionResult:
    origin: str
    issuer_id: str
    provider_forecast_date: date
    horizon: str
    metric: str
    current_fetched_at: datetime
    prior_fetched_at: datetime
    average_delta: Decimal
    average_change_pct: Decimal | None
    analyst_count_delta: int
    quality_status: str
    unknown_reason: str | None = None


@dataclass(frozen=True, slots=True)
class ProviderRollingComparison:
    origin: str
    days: int
    current_average: Decimal
    provider_prior_average: Decimal
    delta: Decimal
    interpretation: str = "provider_attribute_not_historical_snapshot"


def require_production_activation(bundle: ConsensusContractBundle) -> None:
    if bundle.activation_state != "production":
        raise RuntimeError("Alpha source calls remain inactive until the production gate opens")


def validate_terms_review(review: TermsReview, *, as_of: date) -> TermsReview:
    if (
        review.status != "approved"
        or len(review.evidence_hash) != 64
        or any(character not in "0123456789abcdef" for character in review.evidence_hash.lower())
    ):
        raise ValueError("Alpha terms review requires approved hash evidence")
    if review.expires_on < review.reviewed_on:
        raise ValueError("Alpha terms review interval is invalid")
    if (review.expires_on - review.reviewed_on).days > 92:
        raise ValueError("Alpha terms review cannot exceed the quarterly review window")
    if as_of < review.reviewed_on or as_of > review.expires_on:
        raise ValueError("Alpha terms review is not valid for the provider day")
    return review


def resolve_held_issuer_allowlist(
    candidates: Iterable[HeldIssuerCandidate],
) -> tuple[HeldIssuerCandidate, ...]:
    eligible: list[HeldIssuerCandidate] = []
    for item in candidates:
        in_scope = (
            item.market == "NASD"
            and item.asset_type == "equity"
            and item.economic_exposure == "overseas_direct"
            and item.currency == "USD"
            and item.quantity > 0
        )
        if not in_scope:
            continue
        if item.quality_status != "pass" or not item.issuer_id.strip() or not item.provider_symbol.strip():
            raise ValueError("Alpha eligible holding lacks exact issuer identity or passing quality")
        eligible.append(item)
    if len({item.issuer_id for item in eligible}) != len(eligible):
        raise ValueError("Alpha held scope contains an ambiguous duplicate issuer")
    if len({item.provider_symbol for item in eligible}) != len(eligible):
        raise ValueError("Alpha held scope contains an ambiguous duplicate provider symbol")
    if len(eligible) > MAX_PROVIDER_DAY_CALLS:
        raise ValueError("Alpha held scope exceeds the eight-call hard maximum")
    return tuple(sorted(eligible, key=lambda item: (item.issuer_id, item.provider_symbol)))


def validate_call_plan(
    plan: ConsensusCallPlan,
    *,
    terms_review: TermsReview,
) -> ConsensusCallPlan:
    validate_terms_review(terms_review, as_of=plan.provider_day)
    if not plan.issuer_ids or len(plan.issuer_ids) != len(plan.provider_symbols):
        raise ValueError("Alpha call plan requires matched non-empty issuer and symbol partitions")
    if any(not value.strip() for value in plan.issuer_ids + plan.provider_symbols):
        raise ValueError("Alpha call plan contains an empty issuer or provider symbol")
    if len(set(plan.issuer_ids)) != len(plan.issuer_ids) or len(set(plan.provider_symbols)) != len(plan.provider_symbols):
        raise ValueError("Alpha call plan partitions must be exact and unique")
    if plan.physical_calls > MAX_PROVIDER_DAY_CALLS or plan.physical_calls > ACCOUNT_FREE_DAY_LIMIT:
        raise ValueError("Alpha call plan exceeds its provider-day budget")
    if plan.spacing_seconds < MIN_CALL_SPACING_SECONDS:
        raise ValueError("Alpha calls must be serialized at least fifteen seconds apart")
    if plan.retry_count != 0:
        raise ValueError("Alpha forward collection prohibits same-run retries")
    return plan


def validate_capacity(*, silver_rows: int, private_backup_bytes: int) -> str:
    if silver_rows < 0 or private_backup_bytes < 0:
        raise ValueError("Alpha capacity counters cannot be negative")
    if silver_rows > SILVER_STOP_ROWS:
        raise ValueError("Alpha Silver exceeds the 500000-row stop line")
    if private_backup_bytes > PRIVATE_BACKUP_STOP_BYTES:
        raise ValueError("Alpha private backup exceeds the 512 MiB stop line")
    review = (
        silver_rows * 5 >= SILVER_STOP_ROWS * 4
        or private_backup_bytes * 5 >= PRIVATE_BACKUP_STOP_BYTES * 4
    )
    return "review" if review else "pass"


def require_provider_consensus_origin(origin: str) -> None:
    if origin != "provider_consensus":
        raise ValueError("user or model scenarios must never be labeled provider consensus")


def require_owner_only_consumer(consumer: str) -> None:
    if consumer not in {"owner-only-analysis", "private-mcp-after-production-approval"}:
        raise ValueError("Alpha normalized consensus cannot be redistributed or sent to Telegram")


def three_year_retention_cutoff(as_of: date) -> date:
    try:
        return as_of.replace(year=as_of.year - 3)
    except ValueError:
        return as_of.replace(year=as_of.year - 3, day=28)


def calculate_forward_revision(
    current: ConsensusForwardSnapshot,
    prior: ConsensusForwardSnapshot,
    *,
    evaluation_at: datetime,
) -> ForwardRevisionResult:
    validate_snapshot(current)
    validate_snapshot(prior)
    if evaluation_at.tzinfo is None:
        raise ValueError("forward revision evaluation cutoff must be timezone-aware")
    identity = lambda item: (
        item.issuer_id,
        item.provider_forecast_date,
        item.metric,
        item.horizon,
        item.definition_hash,
    )
    if identity(current) != identity(prior):
        raise ValueError("forward revision inputs must share exact provider consensus identity")
    if current.fetched_at <= prior.fetched_at:
        raise ValueError("forward revision inputs must advance fetched-at knowledge")
    if current.fetched_at > evaluation_at or prior.fetched_at > evaluation_at:
        raise ValueError("forward revision cannot use a future fetched-at snapshot")
    delta = current.estimate_average - prior.estimate_average
    if prior.estimate_average == 0:
        percent = None
        quality_status = "partial"
        reason = "zero_prior_average"
    else:
        percent = delta / abs(prior.estimate_average) * Decimal(100)
        quality_status = "pass"
        reason = None
    return ForwardRevisionResult(
        origin="provider_consensus",
        issuer_id=current.issuer_id,
        provider_forecast_date=current.provider_forecast_date,
        horizon=current.horizon,
        metric=current.metric,
        current_fetched_at=current.fetched_at,
        prior_fetched_at=prior.fetched_at,
        average_delta=delta,
        average_change_pct=percent,
        analyst_count_delta=current.analyst_count - prior.analyst_count,
        quality_status=quality_status,
        unknown_reason=reason,
    )


def provider_rolling_comparison(
    value: ConsensusForwardSnapshot,
    *,
    days: int,
) -> ProviderRollingComparison:
    validate_snapshot(value)
    if value.metric != "eps" or days not in {7, 30, 60, 90}:
        raise ValueError("provider rolling comparison supports EPS 7/30/60/90-day attributes only")
    prior = getattr(value, f"average_{days}_days_ago")
    if prior is None:
        raise ValueError("provider rolling comparison is missing")
    return ProviderRollingComparison(
        origin="provider_consensus",
        days=days,
        current_average=value.estimate_average,
        provider_prior_average=prior,
        delta=value.estimate_average - prior,
    )


def record_coverage_quality(
    connection: duckdb.DuckDBPyConnection,
    *,
    run_id: str,
    expected_issuer_refs: tuple[str, ...],
    published_issuer_refs: tuple[str, ...],
    evaluated_at: datetime,
) -> tuple[str, str]:
    if evaluated_at.tzinfo is None:
        raise ValueError("Alpha coverage evaluation time must be timezone-aware")
    expected = set(expected_issuer_refs)
    published = set(published_issuer_refs)
    if not expected or not published <= expected:
        raise ValueError("Alpha coverage requires a non-empty exact held-issuer scope")
    missing = sorted(expected - published)
    status = "pass" if not missing else "failed" if not published else "partial"
    quality_result_id = hashlib.sha256(
        f"{run_id}|{DATASET_ID}|held-issuer-coverage".encode()
    ).hexdigest()
    details = {
        "expected_issuer_refs": sorted(expected),
        "published_issuer_refs": sorted(published),
        "missing_issuer_refs": missing,
        "historical_pit_supported": False,
        "raw_retained": False,
    }
    connection.execute(
        """
        INSERT INTO control.quality_results(
            quality_result_id,run_id,dataset_id,rule_id,status,observed_value,
            expected_value,details,evaluated_at
        ) VALUES (?,?,?,'held-issuer-coverage',?,?,?,?,?)
        ON CONFLICT(quality_result_id) DO NOTHING
        """,
        [
            quality_result_id,
            run_id,
            DATASET_ID,
            status,
            str(len(published)),
            str(len(expected)),
            json.dumps(details, sort_keys=True),
            evaluated_at,
        ],
    )
    return quality_result_id, status


def publish_session_watermark(
    connection: duckdb.DuckDBPyConnection,
    *,
    run_id: str,
    session_key: str,
    quality_result_id: str,
    observed_at: datetime,
) -> bool:
    if observed_at.tzinfo is None:
        raise ValueError("Alpha watermark observation time must be timezone-aware")
    quality = connection.execute(
        """
        SELECT run_id,status FROM control.quality_results
        WHERE quality_result_id=? AND dataset_id=? AND rule_id='held-issuer-coverage'
        """,
        [quality_result_id, DATASET_ID],
    ).fetchone()
    if quality is None or quality[0] != run_id:
        raise ValueError("Alpha watermark requires matching coverage evidence")
    if quality[1] != "pass":
        return False
    prior = connection.execute(
        """
        SELECT watermark_value FROM control.watermarks
        WHERE pipeline_id=? AND partition_key='held-us-direct'
          AND watermark_type='us_session'
        """,
        [PIPELINE_ID],
    ).fetchone()
    if prior is not None and session_key < str(prior[0]):
        raise ValueError("Alpha session watermark cannot move backwards")
    connection.execute(
        """
        INSERT INTO control.watermarks(
            pipeline_id,partition_key,watermark_type,watermark_value,run_id,updated_at
        ) VALUES (?,'held-us-direct','us_session',?,?,?)
        ON CONFLICT(pipeline_id,partition_key,watermark_type) DO UPDATE SET
            watermark_value=excluded.watermark_value,
            run_id=excluded.run_id,
            updated_at=excluded.updated_at
        """,
        [PIPELINE_ID, session_key, run_id, observed_at],
    )
    return True
