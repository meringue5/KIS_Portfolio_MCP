"""Strict synthetic Alpha fixture normalization with zero network or raw persistence."""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from kis_portfolio.modules.market.consensus import (
    ConsensusForwardSnapshot,
    ConsensusNormalizationResult,
    validate_snapshot,
)
from kis_portfolio.platform.consensus_registry import ConsensusContractBundle


IDENTITY_FIELDS = frozenset({"date", "horizon"})
EPS_FIELDS = frozenset({
    "eps_estimate_analyst_count",
    "eps_estimate_average",
    "eps_estimate_high",
    "eps_estimate_low",
    "eps_estimate_average_7_days_ago",
    "eps_estimate_average_30_days_ago",
    "eps_estimate_average_60_days_ago",
    "eps_estimate_average_90_days_ago",
    "eps_estimate_revision_up_trailing_7_days",
    "eps_estimate_revision_up_trailing_30_days",
    "eps_estimate_revision_down_trailing_7_days",
    "eps_estimate_revision_down_trailing_30_days",
})
REVENUE_FIELDS = frozenset({
    "revenue_estimate_analyst_count",
    "revenue_estimate_average",
    "revenue_estimate_high",
    "revenue_estimate_low",
})
ESTIMATE_FIELDS = IDENTITY_FIELDS | EPS_FIELDS | REVENUE_FIELDS


def _hash(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def _decimal(value: Any, *, field: str) -> Decimal:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Alpha fixture {field} must be a non-empty numeric string")
    try:
        return Decimal(value.strip().replace(",", ""))
    except InvalidOperation as exc:
        raise ValueError(f"Alpha fixture {field} is not a Decimal") from exc


def _optional_int(value: Any, *, field: str) -> int | None:
    if value is None or value == "":
        return None
    if not isinstance(value, str) or not value.strip().isdigit():
        raise ValueError(f"Alpha fixture {field} must be an integer string or null")
    return int(value)


def _required_int(value: Any, *, field: str) -> int:
    result = _optional_int(value, field=field)
    if result is None:
        raise ValueError(f"Alpha fixture {field} is required")
    return result


def _forecast_date(value: Any) -> date:
    if not isinstance(value, str):
        raise ValueError("Alpha fixture date must be an ISO string")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("Alpha fixture date must be ISO YYYY-MM-DD") from exc


def normalize_alpha_fixture(
    document: dict[str, Any],
    *,
    bundle: ConsensusContractBundle,
    issuer_id: str,
    expected_symbol: str,
    fetched_at: datetime,
    us_session_date: date,
    request_id: str,
) -> ConsensusNormalizationResult:
    if document.get("fixture_only") is not True:
        raise ValueError("isolated Alpha normalizer accepts conspicuously fixture-only documents")
    if bundle.activation_state != "inactive":
        raise ValueError("isolated Alpha normalization requires an inactive contract bundle")
    payload = document.get("payload")
    if not isinstance(payload, dict):
        raise ValueError("Alpha fixture payload must be an object")
    if "Information" in payload or "Note" in payload:
        return ConsensusNormalizationResult((), "partial", "provider_information")
    if "Error Message" in payload:
        return ConsensusNormalizationResult((), "failed", "provider_error")
    if set(payload) != {"symbol", "estimates"}:
        raise ValueError("Alpha fixture top-level shape drifted from the exact allowlist")
    if payload["symbol"] != expected_symbol:
        raise ValueError("Alpha fixture symbol differs from the held-issuer request")
    estimates = payload["estimates"]
    if not isinstance(estimates, list) or not estimates or len(estimates) > 128:
        raise ValueError("Alpha fixture estimates must be a bounded non-empty array")
    if fetched_at.tzinfo is None:
        raise ValueError("Alpha fixture fetched_at must be timezone-aware")
    source_request_ref = hashlib.sha256(request_id.encode()).hexdigest()
    rows: list[ConsensusForwardSnapshot] = []
    for estimate in estimates:
        if not isinstance(estimate, dict) or set(estimate) != ESTIMATE_FIELDS:
            raise ValueError("Alpha fixture estimate shape drifted from the 18-field allowlist")
        forecast_date = _forecast_date(estimate["date"])
        horizon = estimate["horizon"]
        if not isinstance(horizon, str):
            raise ValueError("Alpha fixture horizon must be a string")
        common = {
            "definition_hash": bundle.definition_hash,
            "issuer_id": issuer_id,
            "provider_forecast_date": forecast_date,
            "horizon": horizon,
            "us_session_date": us_session_date,
            "fetched_at": fetched_at,
            "source_request_ref": source_request_ref,
        }
        eps_content = {
            "metric": "eps",
            "forecast_date": forecast_date,
            "horizon": horizon,
            "average": estimate["eps_estimate_average"],
            "high": estimate["eps_estimate_high"],
            "low": estimate["eps_estimate_low"],
            "analyst_count": estimate["eps_estimate_analyst_count"],
            "average_7": estimate["eps_estimate_average_7_days_ago"],
            "average_30": estimate["eps_estimate_average_30_days_ago"],
            "average_60": estimate["eps_estimate_average_60_days_ago"],
            "average_90": estimate["eps_estimate_average_90_days_ago"],
            "up_7": estimate["eps_estimate_revision_up_trailing_7_days"],
            "up_30": estimate["eps_estimate_revision_up_trailing_30_days"],
            "down_7": estimate["eps_estimate_revision_down_trailing_7_days"],
            "down_30": estimate["eps_estimate_revision_down_trailing_30_days"],
        }
        eps = ConsensusForwardSnapshot(
            **common,
            metric="eps",
            estimate_average=_decimal(estimate["eps_estimate_average"], field="eps average"),
            estimate_high=_decimal(estimate["eps_estimate_high"], field="eps high"),
            estimate_low=_decimal(estimate["eps_estimate_low"], field="eps low"),
            analyst_count=_required_int(
                estimate["eps_estimate_analyst_count"], field="eps analyst count"
            ),
            average_7_days_ago=_decimal(
                estimate["eps_estimate_average_7_days_ago"], field="eps average 7 days ago"
            ),
            average_30_days_ago=_decimal(
                estimate["eps_estimate_average_30_days_ago"], field="eps average 30 days ago"
            ),
            average_60_days_ago=_decimal(
                estimate["eps_estimate_average_60_days_ago"], field="eps average 60 days ago"
            ),
            average_90_days_ago=_decimal(
                estimate["eps_estimate_average_90_days_ago"], field="eps average 90 days ago"
            ),
            revision_up_trailing_7_days=_optional_int(
                estimate["eps_estimate_revision_up_trailing_7_days"], field="eps up 7"
            ),
            revision_up_trailing_30_days=_optional_int(
                estimate["eps_estimate_revision_up_trailing_30_days"], field="eps up 30"
            ),
            revision_down_trailing_7_days=_optional_int(
                estimate["eps_estimate_revision_down_trailing_7_days"], field="eps down 7"
            ),
            revision_down_trailing_30_days=_optional_int(
                estimate["eps_estimate_revision_down_trailing_30_days"], field="eps down 30"
            ),
            content_hash=_hash(eps_content),
        )
        revenue_content = {
            "metric": "revenue",
            "forecast_date": forecast_date,
            "horizon": horizon,
            "average": estimate["revenue_estimate_average"],
            "high": estimate["revenue_estimate_high"],
            "low": estimate["revenue_estimate_low"],
            "analyst_count": estimate["revenue_estimate_analyst_count"],
        }
        revenue = ConsensusForwardSnapshot(
            **common,
            metric="revenue",
            estimate_average=_decimal(
                estimate["revenue_estimate_average"], field="revenue average"
            ),
            estimate_high=_decimal(estimate["revenue_estimate_high"], field="revenue high"),
            estimate_low=_decimal(estimate["revenue_estimate_low"], field="revenue low"),
            analyst_count=_required_int(
                estimate["revenue_estimate_analyst_count"], field="revenue analyst count"
            ),
            content_hash=_hash(revenue_content),
        )
        validate_snapshot(eps)
        validate_snapshot(revenue)
        rows.extend((eps, revenue))
    return ConsensusNormalizationResult(tuple(rows), "pass")
