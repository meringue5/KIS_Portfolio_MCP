"""Dependency-free value objects shared by V2 modules."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from uuid import uuid4


class QualityStatus(StrEnum):
    PASS = "pass"
    DEGRADED = "degraded"
    FAIL = "fail"
    QUARANTINED = "quarantined"


@dataclass(frozen=True, slots=True)
class Money:
    amount: Decimal
    currency: str

    def __post_init__(self) -> None:
        normalized = self.currency.strip().upper()
        if len(normalized) != 3:
            raise ValueError("currency must be a three-letter code")
        object.__setattr__(self, "currency", normalized)

    def add(self, other: "Money") -> "Money":
        if self.currency != other.currency:
            raise ValueError("cannot add money in different currencies")
        return Money(self.amount + other.amount, self.currency)


@dataclass(frozen=True, slots=True)
class Provenance:
    source_id: str
    source_record_id: str
    observed_at: datetime
    knowledge_at: datetime
    content_hash: str | None = None

    def __post_init__(self) -> None:
        for value in (self.observed_at, self.knowledge_at):
            if value.tzinfo is None:
                raise ValueError("provenance timestamps must be timezone-aware")


def utc_now() -> datetime:
    return datetime.now(UTC)


def new_id() -> str:
    return str(uuid4())
