"""Pure position reconstruction and sell-allocation boundary contract.

This module deliberately has no source client or database dependency.  It
defines the fail-closed decisions that later WI-022 stages must preserve when
they replay governed trade and corporate-action facts.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Iterable


CONTRACT_VERSION = "1.0.0"
ZERO = Decimal("0")


class EvidenceProvenance(StrEnum):
    ACTUAL = "actual"
    MANUAL = "manual"
    INFERRED_OPENING = "inferred_opening"


class CorporateActionCoverage(StrEnum):
    PASS = "pass"
    NOT_ASSESSED = "not_assessed"
    FAIL = "fail"


class ReconstructionStatus(StrEnum):
    RECONSTRUCTED = "reconstructed"
    INFERRED_OPENING = "inferred_opening"
    PROVISIONAL = "provisional"
    NOT_ASSESSED = "not_assessed"
    RECONCILIATION_EXCEPTION = "reconciliation_exception"


class AllocationMethod(StrEnum):
    EXPLICIT_LOT = "explicit_lot"
    EXPLICIT_THREAD_FIFO = "explicit_thread_fifo"
    INFERRED_FIFO = "inferred_fifo"


class AllocationStatus(StrEnum):
    COMPLETE = "complete"
    RECONCILIATION_EXCEPTION = "reconciliation_exception"


class AllocationContractError(ValueError):
    """Raised when an explicit allocation request violates its declared scope."""


def _decimal(value: Decimal | int | str, field: str) -> Decimal:
    try:
        result = value if isinstance(value, Decimal) else Decimal(str(value))
    except Exception as exc:  # pragma: no cover - Decimal supplies varying subclasses
        raise ValueError(f"{field} must be a decimal") from exc
    if not result.is_finite():
        raise ValueError(f"{field} must be finite")
    return result


def reconstruction_partition_key(
    account_id: str,
    instrument_id: str,
    start_at: datetime,
    end_at: datetime,
) -> str:
    """Return a stable non-secret partition key for one reconstruction window."""

    if not account_id or not instrument_id:
        raise ValueError("account_id and instrument_id are required")
    if start_at >= end_at:
        raise ValueError("reconstruction window must have positive duration")
    identity = "|".join(
        (CONTRACT_VERSION, account_id, instrument_id, start_at.isoformat(), end_at.isoformat())
    )
    return f"reconstruct-{hashlib.sha256(identity.encode()).hexdigest()}"


@dataclass(frozen=True, slots=True)
class ReconstructionAssessment:
    status: ReconstructionStatus
    current_quantity: Decimal
    replayed_quantity: Decimal
    inferred_opening_quantity: Decimal | None
    evidence_provenance: EvidenceProvenance | None
    blockers: tuple[str, ...]
    eligible_for_reconciled_projection: bool


def assess_reconstruction(
    *,
    current_quantity: Decimal | int | str,
    replayed_quantity: Decimal | int | str,
    corporate_action_coverage: CorporateActionCoverage,
    source_gap_reasons: Iterable[str] = (),
    ambiguous_event_order: bool = False,
) -> ReconstructionAssessment:
    """Classify a replay against the broker position without inventing history.

    A positive residual can become an explicitly labelled opening lot only
    after corporate-action coverage passes and there is no known source gap.
    A negative residual or ambiguous ordering is an exception, never a
    negative lot.  Missing coverage and source gaps retain their own states.
    """

    current = _decimal(current_quantity, "current_quantity")
    replayed = _decimal(replayed_quantity, "replayed_quantity")
    if current < ZERO:
        raise ValueError("current_quantity cannot be negative")
    gaps = tuple(sorted({reason.strip() for reason in source_gap_reasons if reason.strip()}))
    residual = current - replayed
    blockers: list[str] = []

    if ambiguous_event_order:
        blockers.append("ambiguous_event_order")
    if residual < ZERO:
        blockers.append("replay_exceeds_current_position")
    if corporate_action_coverage is CorporateActionCoverage.FAIL:
        blockers.append("corporate_action_coverage_failed")
    if blockers:
        return ReconstructionAssessment(
            ReconstructionStatus.RECONCILIATION_EXCEPTION,
            current,
            replayed,
            None,
            None,
            tuple(blockers),
            False,
        )

    if corporate_action_coverage is CorporateActionCoverage.NOT_ASSESSED:
        return ReconstructionAssessment(
            ReconstructionStatus.NOT_ASSESSED,
            current,
            replayed,
            None,
            None,
            ("corporate_action_coverage_not_assessed",),
            False,
        )

    if gaps:
        return ReconstructionAssessment(
            ReconstructionStatus.PROVISIONAL,
            current,
            replayed,
            None,
            None,
            gaps,
            False,
        )

    if residual > ZERO:
        return ReconstructionAssessment(
            ReconstructionStatus.INFERRED_OPENING,
            current,
            replayed,
            residual,
            EvidenceProvenance.INFERRED_OPENING,
            (),
            True,
        )

    return ReconstructionAssessment(
        ReconstructionStatus.RECONSTRUCTED,
        current,
        replayed,
        None,
        EvidenceProvenance.ACTUAL,
        (),
        True,
    )


@dataclass(frozen=True, slots=True)
class OpenLot:
    lot_id: str
    account_id: str
    instrument_id: str
    episode_id: str
    opened_at: datetime
    remaining_quantity: Decimal
    thread_id: str | None = None

    def __post_init__(self) -> None:
        if not self.lot_id or not self.account_id or not self.instrument_id or not self.episode_id:
            raise ValueError("lot identity and scope are required")
        quantity = _decimal(self.remaining_quantity, "remaining_quantity")
        if quantity <= ZERO:
            raise ValueError("remaining_quantity must be positive")
        object.__setattr__(self, "remaining_quantity", quantity)


@dataclass(frozen=True, slots=True)
class SellAllocationRequest:
    sell_trade_event_id: str
    account_id: str
    instrument_id: str
    episode_id: str
    quantity: Decimal
    explicit_lot_ids: tuple[str, ...] = ()
    explicit_thread_id: str | None = None

    def __post_init__(self) -> None:
        if not self.sell_trade_event_id or not self.account_id or not self.instrument_id or not self.episode_id:
            raise ValueError("sell identity and scope are required")
        quantity = _decimal(self.quantity, "quantity")
        if quantity <= ZERO:
            raise ValueError("sell quantity must be positive")
        if self.explicit_lot_ids and self.explicit_thread_id:
            raise ValueError("explicit lot and thread selectors are mutually exclusive")
        if len(set(self.explicit_lot_ids)) != len(self.explicit_lot_ids):
            raise ValueError("explicit lot ids must be unique")
        object.__setattr__(self, "quantity", quantity)


@dataclass(frozen=True, slots=True)
class SellAllocationSlice:
    lot_id: str
    allocated_quantity: Decimal


@dataclass(frozen=True, slots=True)
class SellAllocationPlan:
    method: AllocationMethod
    status: AllocationStatus
    slices: tuple[SellAllocationSlice, ...]
    requested_quantity: Decimal
    allocated_quantity: Decimal
    unallocated_quantity: Decimal
    review_required: bool
    blockers: tuple[str, ...]


def plan_sell_allocation(
    request: SellAllocationRequest,
    open_lots: Iterable[OpenLot],
) -> SellAllocationPlan:
    """Allocate a sell deterministically without mutating lots.

    Explicit selectors never fall back to a broader scope.  FIFO order is
    `(opened_at, lot_id)` and always remains inside one account, instrument and
    position episode.  Insufficient quantity returns a reviewable exception;
    it never creates an opening lot or a negative balance.
    """

    all_lots = tuple(open_lots)
    scoped = tuple(
        lot
        for lot in all_lots
        if lot.account_id == request.account_id
        and lot.instrument_id == request.instrument_id
        and lot.episode_id == request.episode_id
    )
    scoped_by_id = {lot.lot_id: lot for lot in scoped}

    if request.explicit_lot_ids:
        missing = tuple(lot_id for lot_id in request.explicit_lot_ids if lot_id not in scoped_by_id)
        if missing:
            raise AllocationContractError(
                "explicit lots are unavailable or outside the sell scope: " + ",".join(missing)
            )
        candidates = tuple(scoped_by_id[lot_id] for lot_id in request.explicit_lot_ids)
        method = AllocationMethod.EXPLICIT_LOT
    elif request.explicit_thread_id:
        candidates = tuple(lot for lot in scoped if lot.thread_id == request.explicit_thread_id)
        if not candidates:
            raise AllocationContractError("explicit thread has no open lot in the sell scope")
        method = AllocationMethod.EXPLICIT_THREAD_FIFO
    else:
        candidates = scoped
        method = AllocationMethod.INFERRED_FIFO

    remaining = request.quantity
    slices: list[SellAllocationSlice] = []
    for lot in sorted(candidates, key=lambda item: (item.opened_at, item.lot_id)):
        if remaining == ZERO:
            break
        allocated = min(lot.remaining_quantity, remaining)
        if allocated > ZERO:
            slices.append(SellAllocationSlice(lot.lot_id, allocated))
            remaining -= allocated

    allocated_total = request.quantity - remaining
    complete = remaining == ZERO
    blockers = () if complete else ("insufficient_open_lot_quantity",)
    return SellAllocationPlan(
        method=method,
        status=AllocationStatus.COMPLETE if complete else AllocationStatus.RECONCILIATION_EXCEPTION,
        slices=tuple(slices),
        requested_quantity=request.quantity,
        allocated_quantity=allocated_total,
        unallocated_quantity=remaining,
        review_required=method is AllocationMethod.INFERRED_FIFO or not complete,
        blockers=blockers,
    )
