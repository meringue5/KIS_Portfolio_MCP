"""Quality gate for an explicitly typed secondary USD/KRW valuation rate."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from kis_portfolio.clients.korea_exim import KoreaEximFxRate, fetch_usd_krw_deal_bas_rate


MAX_DEVIATION_RATIO = Decimal("0.03")
MAX_REFERENCE_AGE_DAYS = 7


@dataclass(frozen=True, slots=True)
class FxFallbackAssessment:
    eligible: bool
    reason: str
    reference_date: date | None
    reference_age_days: int | None
    deviation_ratio: Decimal | None


def assess_fx_fallback(
    candidate: KoreaEximFxRate,
    *,
    logical_date: date,
    reference_date: date | None,
    reference_rate: Decimal | None,
) -> FxFallbackAssessment:
    reference_age = (
        (logical_date - reference_date).days if reference_date is not None else None
    )
    deviation = (
        abs(candidate.rate - reference_rate) / reference_rate
        if reference_rate is not None and reference_rate > 0 else None
    )
    reason = "pass"
    if candidate.rate_date != logical_date:
        reason = "provider_date_mismatch"
    elif reference_age is None or not 0 <= reference_age <= MAX_REFERENCE_AGE_DAYS:
        reason = "reference_missing_or_stale"
    elif deviation is None or deviation > MAX_DEVIATION_RATIO:
        reason = "cross_source_deviation_exceeded"
    return FxFallbackAssessment(
        eligible=reason == "pass",
        reason=reason,
        reference_date=reference_date,
        reference_age_days=reference_age,
        deviation_ratio=deviation,
    )


def latest_kis_usd_krw_reference(connection: Any, *, logical_date: date) -> tuple[date, Decimal] | None:
    row = connection.execute(
        """SELECT rates.rate_date,rates.rate
           FROM silver.fx_rates_daily rates
           JOIN bronze.source_observations observations
             ON observations.observation_id=rates.source_observation_id
           WHERE rates.base_currency='USD' AND rates.quote_currency='KRW'
             AND rates.rate_type='close' AND rates.quality_status='pass'
             AND observations.source_id='source.kis-open-api'
             AND rates.rate_date<=?
           ORDER BY rates.rate_date DESC LIMIT 1""",
        [logical_date],
    ).fetchone()
    return (row[0], Decimal(str(row[1]))) if row else None


async def validate_korea_exim_fx_source(
    connection: Any,
    *,
    logical_date: date,
    api_key: str,
) -> dict[str, Any]:
    candidate = await fetch_usd_krw_deal_bas_rate(
        api_key=api_key,
        requested_date=logical_date,
    )
    reference = latest_kis_usd_krw_reference(connection, logical_date=logical_date)
    assessment = assess_fx_fallback(
        candidate,
        logical_date=logical_date,
        reference_date=reference[0] if reference else None,
        reference_rate=reference[1] if reference else None,
    )
    return {
        "status": "passed" if assessment.eligible else "failed",
        "provider": candidate.provider,
        "requested_date": logical_date.isoformat(),
        "native_rate_field": candidate.native_rate_field,
        "reference_date": assessment.reference_date.isoformat() if assessment.reference_date else None,
        "reference_age_days": assessment.reference_age_days,
        "deviation_ratio": (
            str(assessment.deviation_ratio) if assessment.deviation_ratio is not None else None
        ),
        "reason": assessment.reason,
    }
