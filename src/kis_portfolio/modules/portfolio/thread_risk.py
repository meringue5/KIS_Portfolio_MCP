"""Pure owner-authoritative thread-risk and review contracts."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any, Mapping


MAX_RISK_BUDGET_RATIO = Decimal("0.0200000000")


class RiskPlanAuthority(StrEnum):
    OWNER_DIRECT = "owner_direct"
    OWNER_CONFIRMED = "owner_confirmed"


class ReviewType(StrEnum):
    MISSING_THREAD_RISK_PLAN = "missing_thread_risk_plan"
    MISSING_TRADE_JOURNAL = "missing_trade_journal"
    SELL_ALLOCATION_CONFIRMATION = "sell_allocation_confirmation"
    UNRESOLVED_SELL_ALLOCATION = "unresolved_sell_allocation"


class ReviewStatus(StrEnum):
    OPEN = "open"
    ANSWERED = "answered"
    DISMISSED = "dismissed"


def _decimal(value: Decimal | int | str, field_name: str) -> Decimal:
    try:
        result = value if isinstance(value, Decimal) else Decimal(str(value))
    except Exception as exc:  # pragma: no cover - Decimal exception types vary
        raise ValueError(f"{field_name} must be a decimal") from exc
    if not result.is_finite():
        raise ValueError(f"{field_name} must be finite")
    return result


def _aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None:
        raise ValueError(f"{field_name} must be timezone-aware")


@dataclass(frozen=True, slots=True)
class ThreadRiskPlanDraft:
    thread_id: str
    reference_price: Decimal
    stop_price: Decimal
    currency: str
    risk_budget_ratio: Decimal
    effective_at: datetime
    knowledge_at: datetime
    authority_source: RiskPlanAuthority = RiskPlanAuthority.OWNER_DIRECT
    advice_metadata: Mapping[str, Any] = field(default_factory=dict)
    provenance: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.thread_id.strip():
            raise ValueError("thread_id is required")
        reference = _decimal(self.reference_price, "reference_price")
        stop = _decimal(self.stop_price, "stop_price")
        budget = _decimal(self.risk_budget_ratio, "risk_budget_ratio")
        if reference <= 0 or stop <= 0:
            raise ValueError("reference_price and stop_price must be positive")
        if stop >= reference:
            raise ValueError("V1 long-position stop_price must be below reference_price")
        if budget <= 0 or budget > MAX_RISK_BUDGET_RATIO:
            raise ValueError("risk_budget_ratio must be positive and no greater than 0.02")
        if not self.currency.strip():
            raise ValueError("currency is required")
        _aware(self.effective_at, "effective_at")
        _aware(self.knowledge_at, "knowledge_at")
        object.__setattr__(self, "reference_price", reference)
        object.__setattr__(self, "stop_price", stop)
        object.__setattr__(self, "risk_budget_ratio", budget)
        object.__setattr__(self, "currency", self.currency.strip().upper())


def review_identity(review_type: ReviewType, subject_type: str, subject_id: str) -> tuple[str, str]:
    if not subject_type.strip() or not subject_id.strip():
        raise ValueError("review subject type and identity are required")
    material = f"owner-review-v1|{review_type.value}|{subject_type}|{subject_id}"
    digest = hashlib.sha256(material.encode()).hexdigest()
    return f"review-{digest}", digest
