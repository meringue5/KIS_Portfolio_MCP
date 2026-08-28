"""Provider-neutral corporate-action contracts and fail-closed validation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any


ACTION_TYPES = frozenset({
    "split",
    "reverse_split",
    "symbol_change",
    "merger",
    "spin_off",
    "unknown",
})
ACTION_STATUSES = frozenset({"provisional", "confirmed", "cancelled", "unknown"})
TERMS_STATUSES = frozenset({"complete", "not_applicable", "unknown"})
QUALITY_STATUSES = frozenset({"pass", "provisional", "unresolved", "cancelled"})


@dataclass(frozen=True, slots=True)
class CorporateActionRevision:
    market: str
    action_type: str
    action_status: str
    source_instrument_id: str
    effective_at: datetime
    knowledge_at: datetime
    terms_status: str
    quality_status: str
    result_instrument_id: str | None = None
    record_date: date | None = None
    ex_date: date | None = None
    listing_date: date | None = None
    pre_action_units: Decimal | None = None
    post_action_units: Decimal | None = None
    provenance: dict[str, Any] | None = None


def validate_corporate_action(value: CorporateActionRevision) -> None:
    if value.action_type not in ACTION_TYPES:
        raise ValueError("unsupported corporate action type")
    if value.action_status not in ACTION_STATUSES:
        raise ValueError("unsupported corporate action status")
    if value.terms_status not in TERMS_STATUSES:
        raise ValueError("unsupported corporate action terms status")
    if value.quality_status not in QUALITY_STATUSES:
        raise ValueError("unsupported corporate action quality status")
    if not value.market.strip() or not value.source_instrument_id.strip():
        raise ValueError("corporate action requires market and source instrument")
    if value.effective_at.tzinfo is None or value.knowledge_at.tzinfo is None:
        raise ValueError("corporate action times must be timezone-aware")
    if value.terms_status == "complete" and value.action_type != "symbol_change":
        if value.pre_action_units is None or value.post_action_units is None:
            raise ValueError("complete corporate action terms require pre and post units")
        if value.pre_action_units <= 0 or value.post_action_units <= 0:
            raise ValueError("corporate action units must be positive")
    if value.action_type == "split" and value.terms_status == "complete":
        if value.post_action_units <= value.pre_action_units:
            raise ValueError("split must increase units")
    if value.action_type == "reverse_split" and value.terms_status == "complete":
        if value.post_action_units >= value.pre_action_units:
            raise ValueError("reverse split must reduce units")
    if value.action_type == "symbol_change" and value.terms_status == "complete":
        if not value.result_instrument_id:
            raise ValueError("complete symbol change requires a result instrument")
