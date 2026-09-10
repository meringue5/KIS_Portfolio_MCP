"""Provider-neutral dividend action, entitlement and receipt-link contracts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any


DIVIDEND_SOURCES = frozenset({"source.opendart", "source.kis-open-api", "source.portfolio-owner"})
JURISDICTIONS = frozenset({"KR", "US"})
ACTION_TYPES = frozenset({"cash", "stock", "special", "option"})
ACTION_STATUSES = frozenset({"declared", "confirmed", "corrected", "cancelled"})
CERTAINTIES = frozenset({"declared", "confirmed", "candidate"})
TIME_PRECISIONS = frozenset({"day", "second"})
QUALITY_STATUSES = frozenset({"pass", "partial", "quarantined", "failed"})
ENTITLEMENT_BASES = frozenset({"source_confirmed", "pit_estimate", "manual"})
COVERAGE_STATUSES = frozenset({
    "source_confirmed", "estimated", "not_observed", "insufficient_history",
    "ambiguous_action", "source_gap",
})
LINK_STATUSES = frozenset({"exact", "reconciled", "candidate", "partial", "unmatched", "source_gap", "reversed"})
COMPONENT_TYPES = frozenset({"gross", "tax", "net"})


@dataclass(frozen=True, slots=True)
class DividendActionRevision:
    source_id: str
    jurisdiction: str
    issuer_id: str
    instrument_id: str
    source_action_id: str
    action_type: str
    action_status: str
    certainty: str
    source_available_at: datetime
    observed_at: datetime
    fetched_at: datetime
    knowledge_at: datetime
    source_time_precision: str = "day"
    amount_per_share: Decimal | None = None
    currency: str | None = None
    declaration_date: date | None = None
    ex_date: date | None = None
    record_date: date | None = None
    payable_date: date | None = None
    cancellation_date: date | None = None
    filing_revision_id: str | None = None
    correction_target_revision_id: str | None = None
    quality_status: str = "pass"
    provenance: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class DividendEntitlementRevision:
    dividend_action_id: str
    account_id: str
    basis: str
    coverage_status: str
    knowledge_at: datetime
    eligibility_date: date | None = None
    eligible_quantity: Decimal | None = None
    rate_per_share: Decimal | None = None
    expected_gross: Decimal | None = None
    expected_tax: Decimal | None = None
    expected_net: Decimal | None = None
    currency: str | None = None
    source_observation_id: str | None = None
    position_evidence_id: str | None = None
    corporate_action_revision_id: str | None = None
    correction_target_revision_id: str | None = None
    quality_status: str = "pass"
    provenance: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class DividendReceiptLinkRevision:
    dividend_action_id: str
    relation_key: str
    link_status: str
    reason: str
    rule_version: str
    knowledge_at: datetime
    dividend_entitlement_id: str | None = None
    cash_flow_event_id: str | None = None
    allocated_receipt_amount: Decimal | None = None
    currency: str | None = None
    correction_target_revision_id: str | None = None
    quality_status: str = "pass"
    provenance: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class CashAmountComponentRevision:
    cash_flow_event_id: str
    component_type: str
    amount: Decimal
    currency: str
    source_id: str
    source_observation_id: str
    knowledge_at: datetime
    correction_target_revision_id: str | None = None
    quality_status: str = "pass"
    provenance: dict[str, Any] | None = None


def _require_aware(*values: datetime) -> None:
    if any(value.tzinfo is None for value in values):
        raise ValueError("dividend timestamps must be timezone-aware")


def validate_action(value: DividendActionRevision) -> None:
    if value.source_id not in DIVIDEND_SOURCES:
        raise ValueError("dividend action requires an approved source")
    if value.jurisdiction not in JURISDICTIONS:
        raise ValueError("unsupported dividend jurisdiction")
    if value.action_type not in ACTION_TYPES or value.action_status not in ACTION_STATUSES:
        raise ValueError("unsupported dividend action type or status")
    if value.certainty not in CERTAINTIES or value.source_time_precision not in TIME_PRECISIONS:
        raise ValueError("unsupported dividend certainty or time precision")
    if value.quality_status not in QUALITY_STATUSES:
        raise ValueError("unsupported dividend quality status")
    if not all((value.issuer_id.strip(), value.instrument_id.strip(), value.source_action_id.strip())):
        raise ValueError("dividend action identity is required")
    if (value.amount_per_share is None) != (value.currency is None):
        raise ValueError("dividend per-share amount and currency must appear together")
    if value.amount_per_share is not None and value.amount_per_share < 0:
        raise ValueError("dividend per-share amount cannot be negative")
    if value.action_status in {"corrected", "cancelled"} and not value.correction_target_revision_id:
        raise ValueError("corrected dividend action requires an explicit target revision")
    _require_aware(value.source_available_at, value.observed_at, value.fetched_at, value.knowledge_at)
    if value.fetched_at < value.observed_at or value.knowledge_at < value.observed_at:
        raise ValueError("dividend knowledge and fetch times cannot precede observation")


def validate_entitlement(value: DividendEntitlementRevision) -> None:
    if value.basis not in ENTITLEMENT_BASES or value.coverage_status not in COVERAGE_STATUSES:
        raise ValueError("unsupported entitlement basis or coverage")
    if value.quality_status not in QUALITY_STATUSES:
        raise ValueError("unsupported entitlement quality status")
    if not value.dividend_action_id.strip() or not value.account_id.strip():
        raise ValueError("entitlement action and account identity are required")
    _require_aware(value.knowledge_at)
    amounts = (value.eligible_quantity, value.rate_per_share, value.expected_gross, value.expected_tax, value.expected_net)
    if value.coverage_status in {"source_gap", "not_observed", "insufficient_history", "ambiguous_action"}:
        if any(item is not None for item in amounts):
            raise ValueError("uncovered entitlement cannot invent quantity or amounts")
    if value.coverage_status == "source_confirmed" and not value.source_observation_id:
        raise ValueError("source-confirmed entitlement requires source evidence")
    if value.coverage_status == "estimated" and not value.position_evidence_id:
        raise ValueError("estimated entitlement requires point-in-time position evidence")
    if any(item is not None for item in amounts[1:]) and not value.currency:
        raise ValueError("entitlement monetary values require currency")


def validate_receipt_link(value: DividendReceiptLinkRevision) -> None:
    if value.link_status not in LINK_STATUSES or value.quality_status not in QUALITY_STATUSES:
        raise ValueError("unsupported receipt-link status or quality")
    if not all((value.dividend_action_id.strip(), value.relation_key.strip(), value.reason.strip(), value.rule_version.strip())):
        raise ValueError("receipt-link identity, reason and rule version are required")
    _require_aware(value.knowledge_at)
    if value.link_status in {"exact", "reconciled", "candidate", "partial", "reversed"} and not value.cash_flow_event_id:
        raise ValueError("linked receipt state requires a cash event")
    if value.link_status in {"unmatched", "source_gap"} and value.cash_flow_event_id is not None:
        raise ValueError("unmatched or source-gap receipt cannot claim a cash event")
    if (value.allocated_receipt_amount is None) != (value.currency is None):
        raise ValueError("receipt allocation and currency must appear together")


def validate_component(value: CashAmountComponentRevision) -> None:
    if value.component_type not in COMPONENT_TYPES:
        raise ValueError("cash amount component must be gross, tax or net")
    if value.source_id not in DIVIDEND_SOURCES:
        raise ValueError("cash amount component requires an approved source")
    if value.quality_status not in QUALITY_STATUSES:
        raise ValueError("unsupported cash amount component quality")
    if not all((value.cash_flow_event_id.strip(), value.currency.strip(), value.source_observation_id.strip())):
        raise ValueError("cash amount component identity and source evidence are required")
    _require_aware(value.knowledge_at)
