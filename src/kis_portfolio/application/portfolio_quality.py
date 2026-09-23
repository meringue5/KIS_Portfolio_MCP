"""Pure quality decisions shared by portfolio readers and presentations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Iterable


@dataclass(frozen=True, slots=True)
class PortfolioQualityComponent:
    """One current-state component needed for capability-level quality composition."""

    account_ref: str
    aggregate_level: str
    market: str
    currency: str
    value_krw: Decimal
    quality_status: str
    fx_date: object = None


@dataclass(frozen=True, slots=True)
class PortfolioCapabilityQuality:
    """Independently useful current portfolio capabilities and their exclusions."""

    complete_total_krw: Decimal | None
    verified_krw_listed_positions_krw: Decimal
    verified_krw_listed_positions_count: int
    observed_accounts: frozenset[str]
    expected_accounts: frozenset[str]
    missing_reasons: tuple[str, ...]

    @property
    def complete(self) -> bool:
        return self.complete_total_krw is not None


def _normalize_date(value: object) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def fx_watermark_is_current(
    *, currency: str, raw_fx_date: object, evaluation_date: object, earliest_fx_date: object,
) -> bool:
    """A foreign KRW valuation requires a dated rate in the approved session window."""
    if currency.upper() == "KRW":
        return True
    fx_date = _normalize_date(raw_fx_date)
    normalized_evaluation_date = _normalize_date(evaluation_date)
    normalized_earliest_fx_date = _normalize_date(earliest_fx_date)
    if not fx_date or not normalized_evaluation_date or not normalized_earliest_fx_date:
        return False
    return normalized_earliest_fx_date <= fx_date <= normalized_evaluation_date


def component_quality_reasons(
    component: PortfolioQualityComponent,
    *,
    evaluation_date: object,
    earliest_fx_date: object,
) -> tuple[str, ...]:
    """Return bounded reasons that prevent this component from complete KRW valuation."""
    reasons: list[str] = []
    currency = component.currency.upper()
    if currency in {"", "UNKNOWN"}:
        reasons.append("unknown_currency")
    elif not fx_watermark_is_current(
        currency=currency,
        raw_fx_date=component.fx_date,
        evaluation_date=evaluation_date,
        earliest_fx_date=earliest_fx_date,
    ):
        reasons.append("fx_input_stale")
    if component.quality_status != "pass":
        reasons.append("degraded_components")
    return tuple(dict.fromkeys(reasons))


def evaluate_portfolio_capabilities(
    components: Iterable[PortfolioQualityComponent],
    *,
    expected_accounts: Iterable[str],
    evaluation_date: object,
    earliest_fx_date: object,
) -> PortfolioCapabilityQuality:
    """Compose complete and partial current-value capabilities without cross-feature poisoning."""
    items = tuple(components)
    expected = frozenset(str(item) for item in expected_accounts)
    observed = frozenset(item.account_ref for item in items)
    reasons: list[str] = []
    verified_value = Decimal("0")
    verified_count = 0
    total = Decimal("0")
    for item in items:
        item_reasons = component_quality_reasons(
            item,
            evaluation_date=evaluation_date,
            earliest_fx_date=earliest_fx_date,
        )
        reasons.extend(item_reasons)
        total += item.value_krw
        if (
            not item_reasons
            and item.aggregate_level == "position"
            and item.market.upper() == "KRX"
            and item.currency.upper() == "KRW"
        ):
            verified_value += item.value_krw
            verified_count += 1
    if not items:
        reasons.append("missing_current_state")
    elif not expected:
        reasons.append("missing_required_account_registry")
    elif observed != expected:
        reasons.append("account_coverage_gap")
    distinct_reasons = tuple(dict.fromkeys(reasons))
    return PortfolioCapabilityQuality(
        complete_total_krw=total if items and not distinct_reasons else None,
        verified_krw_listed_positions_krw=verified_value,
        verified_krw_listed_positions_count=verified_count,
        observed_accounts=observed,
        expected_accounts=expected,
        missing_reasons=distinct_reasons,
    )
