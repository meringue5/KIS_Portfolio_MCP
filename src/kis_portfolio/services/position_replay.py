"""Deterministic, side-effect-free trade and corporate-action replay.

WI-022-S03 deliberately returns candidate episode, lot and sell-allocation
facts.  Persistence into the S02 ledger belongs to S04.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, localcontext
from fractions import Fraction
from typing import Iterable

from kis_portfolio.modules.portfolio.reconstruction import (
    AllocationStatus,
    CorporateActionCoverage,
    EvidenceProvenance,
    OpenLot,
    ReconstructionAssessment,
    ReconstructionStatus,
    SellAllocationPlan,
    SellAllocationRequest,
    assess_reconstruction,
    plan_sell_allocation,
    reconstruction_partition_key,
)


REPLAY_VERSION = "1.0.0"
ZERO = Decimal("0")


class ReplayContractError(ValueError):
    """Raised when supplied canonical facts violate the replay input contract."""


@dataclass(frozen=True, slots=True)
class ReplayRequest:
    account_id: str
    target_instrument_id: str
    lineage_instrument_ids: tuple[str, ...]
    start_at: datetime
    cutoff_at: datetime
    current_quantity: Decimal
    corporate_action_coverage: CorporateActionCoverage
    coverage_quality_result_id: str | None = None
    source_gap_reasons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.account_id or not self.target_instrument_id:
            raise ReplayContractError("account and target instrument are required")
        if self.start_at.tzinfo is None or self.cutoff_at.tzinfo is None:
            raise ReplayContractError("replay window must be timezone-aware")
        if self.start_at >= self.cutoff_at:
            raise ReplayContractError("replay window must have positive duration")
        quantity = _decimal(self.current_quantity, "current_quantity")
        if quantity < ZERO:
            raise ReplayContractError("current quantity cannot be negative")
        lineage = tuple(sorted({item.strip() for item in self.lineage_instrument_ids if item.strip()}))
        if self.target_instrument_id not in lineage:
            raise ReplayContractError("target instrument must be in the governed lineage scope")
        gaps = tuple(sorted({item.strip() for item in self.source_gap_reasons if item.strip()}))
        object.__setattr__(self, "current_quantity", quantity)
        object.__setattr__(self, "lineage_instrument_ids", lineage)
        object.__setattr__(self, "source_gap_reasons", gaps)


@dataclass(frozen=True, slots=True)
class ReplayTrade:
    trade_event_id: str
    account_id: str
    instrument_id: str
    side: str
    executed_at: datetime
    execution_sequence: str
    quantity: Decimal
    price: Decimal
    currency: str
    quality_status: str = "pass"

    def __post_init__(self) -> None:
        side = self.side.strip().lower()
        if not self.trade_event_id or not self.account_id or not self.instrument_id:
            raise ReplayContractError("trade identity and scope are required")
        if side not in {"buy", "sell"}:
            raise ReplayContractError("trade side must be buy or sell")
        if self.executed_at.tzinfo is None:
            raise ReplayContractError("trade executed_at must be timezone-aware")
        quantity = _decimal(self.quantity, "trade quantity")
        price = _decimal(self.price, "trade price")
        if quantity <= ZERO or price < ZERO:
            raise ReplayContractError("trade quantity must be positive and price non-negative")
        if self.quality_status != "pass":
            raise ReplayContractError("only passing canonical trade revisions may be replayed")
        object.__setattr__(self, "side", side)
        object.__setattr__(self, "quantity", quantity)
        object.__setattr__(self, "price", price)
        object.__setattr__(self, "execution_sequence", self.execution_sequence.strip() or "aggregate")
        object.__setattr__(self, "currency", self.currency.strip().upper())


@dataclass(frozen=True, slots=True)
class ReplayCorporateActionEffect:
    corporate_action_revision_id: str
    effect_type: str
    input_instrument_id: str
    output_instrument_id: str | None
    factor_numerator: Decimal | None
    factor_denominator: Decimal | None
    effective_at: datetime
    knowledge_at: datetime
    quality_status: str = "pass"

    def __post_init__(self) -> None:
        effect_type = self.effect_type.strip().lower()
        if effect_type not in {"quantity_multiplier", "price_multiplier", "instrument_successor"}:
            raise ReplayContractError(f"unsupported corporate-action effect: {effect_type}")
        if not self.corporate_action_revision_id or not self.input_instrument_id:
            raise ReplayContractError("corporate-action revision and input instrument are required")
        if self.effective_at.tzinfo is None or self.knowledge_at.tzinfo is None:
            raise ReplayContractError("corporate-action times must be timezone-aware")
        if self.quality_status != "pass":
            raise ReplayContractError("only passing corporate-action effects may be replayed")
        numerator = _optional_decimal(self.factor_numerator, "factor numerator")
        denominator = _optional_decimal(self.factor_denominator, "factor denominator")
        if effect_type in {"quantity_multiplier", "price_multiplier"}:
            if numerator is None or denominator is None or numerator <= ZERO or denominator <= ZERO:
                raise ReplayContractError("multiplier effects require positive complete factors")
        elif not self.output_instrument_id:
            raise ReplayContractError("instrument successor requires an output instrument")
        object.__setattr__(self, "effect_type", effect_type)
        object.__setattr__(self, "factor_numerator", numerator)
        object.__setattr__(self, "factor_denominator", denominator)


@dataclass(frozen=True, slots=True)
class ReplayLot:
    lot_id: str
    episode_id: str
    account_id: str
    opening_instrument_id: str
    instrument_id: str
    opening_trade_event_id: str | None
    opened_at: datetime
    evidence_provenance: EvidenceProvenance
    effective_quantity: Decimal
    remaining_quantity: Decimal
    effective_unit_cost: Decimal | None
    currency: str
    state_effective_at: datetime
    cause_type: str
    cause_ref: str


@dataclass(frozen=True, slots=True)
class ReplayEpisode:
    episode_id: str
    account_id: str
    opening_instrument_id: str
    instrument_id: str
    opened_at: datetime
    closed_at: datetime | None
    current_quantity: Decimal
    reconstruction_status: ReconstructionStatus


@dataclass(frozen=True, slots=True)
class ReplayAllocationCandidate:
    allocation_id: str
    sell_trade_event_id: str
    episode_id: str
    instrument_id: str
    plan: SellAllocationPlan


@dataclass(frozen=True, slots=True)
class PositionReplayPlan:
    partition_key: str
    replay_hash: str
    projection_hash: str
    assessment: ReconstructionAssessment
    coverage_quality_result_id: str | None
    episodes: tuple[ReplayEpisode, ...]
    lots: tuple[ReplayLot, ...]
    allocations: tuple[ReplayAllocationCandidate, ...]
    trade_count: int
    corporate_action_revision_count: int
    side_effects: str = "none"

    def public_summary(self) -> dict[str, object]:
        return {
            "replay_version": REPLAY_VERSION,
            "partition_key": self.partition_key,
            "replay_hash": self.replay_hash,
            "projection_hash": self.projection_hash,
            "status": self.assessment.status.value,
            "blockers": list(self.assessment.blockers),
            "episode_count": len(self.episodes),
            "lot_count": len(self.lots),
            "allocation_count": len(self.allocations),
            "trade_count": self.trade_count,
            "corporate_action_revision_count": self.corporate_action_revision_count,
            "side_effects": self.side_effects,
        }


@dataclass(frozen=True, slots=True)
class _ActionBundle:
    revision_id: str
    input_instrument_id: str
    output_instrument_id: str | None
    effective_at: datetime
    knowledge_at: datetime
    quantity_factor: Fraction
    price_factor: Decimal


@dataclass(slots=True)
class _MutableLot:
    lot_id: str
    episode_id: str
    account_id: str
    opening_instrument_id: str
    instrument_id: str
    opening_trade_event_id: str | None
    opened_at: datetime
    evidence_provenance: EvidenceProvenance
    effective_quantity: Fraction
    remaining_quantity: Fraction
    effective_unit_cost: Decimal | None
    currency: str
    state_effective_at: datetime
    cause_type: str
    cause_ref: str


@dataclass(slots=True)
class _MutableEpisode:
    episode_id: str
    account_id: str
    opening_instrument_id: str
    instrument_id: str
    opened_at: datetime
    closed_at: datetime | None = None


def replay_projection_hash(plan: PositionReplayPlan) -> str:
    """Recompute the deterministic candidate-fact hash used at publish time."""

    return _projection_hash(
        replay_hash=plan.replay_hash,
        assessment=plan.assessment,
        episodes=plan.episodes,
        lots=plan.lots,
        allocations=plan.allocations,
    )


def _projection_hash(
    *,
    replay_hash: str,
    assessment: ReconstructionAssessment,
    episodes: tuple[ReplayEpisode, ...],
    lots: tuple[ReplayLot, ...],
    allocations: tuple[ReplayAllocationCandidate, ...],
) -> str:
    document = {
        "replay_hash": replay_hash,
        "assessment": {
            "status": assessment.status.value,
            "current_quantity": assessment.current_quantity,
            "replayed_quantity": assessment.replayed_quantity,
            "inferred_opening_quantity": assessment.inferred_opening_quantity,
            "evidence_provenance": (
                assessment.evidence_provenance.value if assessment.evidence_provenance else None
            ),
            "blockers": assessment.blockers,
            "eligible": assessment.eligible_for_reconciled_projection,
        },
        "episodes": [
            (
                item.episode_id,
                item.account_id,
                item.opening_instrument_id,
                item.instrument_id,
                item.opened_at.isoformat(),
                item.closed_at.isoformat() if item.closed_at else None,
                item.current_quantity,
                item.reconstruction_status.value,
            )
            for item in episodes
        ],
        "lots": [
            (
                item.lot_id,
                item.episode_id,
                item.account_id,
                item.opening_instrument_id,
                item.instrument_id,
                item.opening_trade_event_id,
                item.opened_at.isoformat(),
                item.evidence_provenance.value,
                item.effective_quantity,
                item.remaining_quantity,
                item.effective_unit_cost,
                item.currency,
                item.state_effective_at.isoformat(),
                item.cause_type,
                item.cause_ref,
            )
            for item in lots
        ],
        "allocations": [
            (
                item.allocation_id,
                item.sell_trade_event_id,
                item.episode_id,
                item.instrument_id,
                item.plan.method.value,
                item.plan.status.value,
                item.plan.requested_quantity,
                item.plan.allocated_quantity,
                item.plan.unallocated_quantity,
                tuple((piece.lot_id, piece.allocated_quantity) for piece in item.plan.slices),
                item.plan.review_required,
                item.plan.blockers,
            )
            for item in allocations
        ],
    }
    return hashlib.sha256(
        json.dumps(document, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def _decimal(value: Decimal | int | str, field: str) -> Decimal:
    try:
        result = value if isinstance(value, Decimal) else Decimal(str(value))
    except Exception as exc:  # pragma: no cover
        raise ReplayContractError(f"{field} must be a decimal") from exc
    if not result.is_finite():
        raise ReplayContractError(f"{field} must be finite")
    return result


def _optional_decimal(value: Decimal | int | str | None, field: str) -> Decimal | None:
    return None if value is None else _decimal(value, field)


def _to_fraction(value: Decimal) -> Fraction:
    return Fraction(value)


def _to_decimal(value: Fraction, field: str) -> Decimal:
    with localcontext() as context:
        context.prec = 50
        result = Decimal(value.numerator) / Decimal(value.denominator)
    if Fraction(result) != value:
        raise ReplayContractError(f"{field} is not exactly representable as a decimal")
    if result.as_tuple().exponent < -10:
        raise ReplayContractError(f"{field} exceeds the ten-decimal quantity contract")
    return result


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _sequence_key(value: str) -> tuple[int, int | str]:
    return (0, int(value)) if value.isdigit() else (1, value)


def _bundle_actions(
    request: ReplayRequest,
    effects: Iterable[ReplayCorporateActionEffect],
) -> tuple[_ActionBundle, ...]:
    grouped: dict[str, list[ReplayCorporateActionEffect]] = {}
    for effect in effects:
        if effect.input_instrument_id not in request.lineage_instrument_ids:
            raise ReplayContractError("corporate-action input is outside the governed lineage")
        if effect.output_instrument_id and effect.output_instrument_id not in request.lineage_instrument_ids:
            raise ReplayContractError("corporate-action output is outside the governed lineage")
        if effect.knowledge_at > request.cutoff_at:
            raise ReplayContractError("future-known corporate-action effect cannot enter replay")
        if not request.start_at <= effect.effective_at <= request.cutoff_at:
            raise ReplayContractError("corporate-action effect is outside the replay window")
        grouped.setdefault(effect.corporate_action_revision_id, []).append(effect)

    bundles: list[_ActionBundle] = []
    for revision_id, items in grouped.items():
        effective_times = {item.effective_at for item in items}
        knowledge_times = {item.knowledge_at for item in items}
        input_ids = {item.input_instrument_id for item in items}
        if len(effective_times) != 1 or len(knowledge_times) != 1 or len(input_ids) != 1:
            raise ReplayContractError("one corporate-action revision must share time and input identity")
        by_type = {item.effect_type: item for item in items}
        if len(by_type) != len(items):
            raise ReplayContractError("duplicate effect type in one corporate-action revision")
        quantity = by_type.get("quantity_multiplier")
        price = by_type.get("price_multiplier")
        successor = by_type.get("instrument_successor")
        quantity_factor = Fraction(1)
        if quantity:
            quantity_factor = Fraction(quantity.factor_numerator) / Fraction(quantity.factor_denominator)
        price_factor = Decimal("1")
        if price:
            price_factor = price.factor_numerator / price.factor_denominator
        bundles.append(
            _ActionBundle(
                revision_id,
                items[0].input_instrument_id,
                successor.output_instrument_id if successor else None,
                items[0].effective_at,
                items[0].knowledge_at,
                quantity_factor,
                price_factor,
            )
        )
    return tuple(sorted(bundles, key=lambda item: (item.effective_at, item.revision_id)))


def _validate_trades(request: ReplayRequest, trades: Iterable[ReplayTrade]) -> tuple[ReplayTrade, ...]:
    values = tuple(trades)
    identities: set[str] = set()
    for trade in values:
        if trade.trade_event_id in identities:
            raise ReplayContractError("duplicate trade event identity")
        identities.add(trade.trade_event_id)
        if trade.account_id != request.account_id:
            raise ReplayContractError("trade account is outside the replay scope")
        if trade.instrument_id not in request.lineage_instrument_ids:
            raise ReplayContractError("trade instrument is outside the governed lineage")
        if not request.start_at <= trade.executed_at <= request.cutoff_at:
            raise ReplayContractError("trade is outside the replay window")
    return tuple(
        sorted(
            values,
            key=lambda item: (
                item.executed_at,
                _sequence_key(item.execution_sequence),
                item.trade_event_id,
            ),
        )
    )


def _ambiguous_order(trades: tuple[ReplayTrade, ...], actions: tuple[_ActionBundle, ...]) -> bool:
    trade_times = {item.executed_at for item in trades}
    if trade_times & {item.effective_at for item in actions}:
        return True
    actions_by_time: dict[datetime, int] = {}
    for action in actions:
        actions_by_time[action.effective_at] = actions_by_time.get(action.effective_at, 0) + 1
    if any(count > 1 for count in actions_by_time.values()):
        return True
    grouped: dict[tuple[datetime, str], set[str]] = {}
    for trade in trades:
        grouped.setdefault((trade.executed_at, trade.execution_sequence), set()).add(trade.side)
    return any(len(sides) > 1 for sides in grouped.values())


def _events(
    trades: tuple[ReplayTrade, ...],
    actions: tuple[_ActionBundle, ...],
) -> tuple[tuple[str, ReplayTrade | _ActionBundle], ...]:
    items = [("trade", item) for item in trades] + [("action", item) for item in actions]
    return tuple(
        sorted(
            items,
            key=lambda item: (
                item[1].executed_at if item[0] == "trade" else item[1].effective_at,
                0 if item[0] == "action" else 1,
                item[1].trade_event_id if item[0] == "trade" else item[1].revision_id,
            ),
        )
    )


def _reverse_opening_requirement(
    request: ReplayRequest,
    events: tuple[tuple[str, ReplayTrade | _ActionBundle], ...],
) -> tuple[Fraction, str]:
    quantity = _to_fraction(request.current_quantity)
    instrument_id = request.target_instrument_id
    for kind, event in reversed(events):
        if kind == "trade":
            trade = event
            assert isinstance(trade, ReplayTrade)
            if trade.instrument_id != instrument_id:
                raise ReplayContractError("trade instrument does not match the governed successor chain")
            trade_quantity = _to_fraction(trade.quantity)
            quantity = quantity - trade_quantity if trade.side == "buy" else quantity + trade_quantity
            if quantity < 0:
                raise ReplayContractError("reverse replay produces a negative opening requirement")
        else:
            action = event
            assert isinstance(action, _ActionBundle)
            if action.output_instrument_id:
                if instrument_id != action.output_instrument_id:
                    raise ReplayContractError("corporate-action successor does not match the replay instrument")
                instrument_id = action.input_instrument_id
            elif instrument_id != action.input_instrument_id and quantity != 0:
                raise ReplayContractError("corporate-action input does not match the replay instrument")
            quantity /= action.quantity_factor
    return quantity, instrument_id


def _blocked_plan(
    request: ReplayRequest,
    partition_key: str,
    replay_hash: str,
    assessment: ReconstructionAssessment,
    trade_count: int,
    action_count: int,
) -> PositionReplayPlan:
    projection_hash = _projection_hash(
        replay_hash=replay_hash,
        assessment=assessment,
        episodes=(),
        lots=(),
        allocations=(),
    )
    return PositionReplayPlan(
        partition_key,
        replay_hash,
        projection_hash,
        assessment,
        request.coverage_quality_result_id,
        (),
        (),
        (),
        trade_count,
        action_count,
    )


def _exception_assessment(request: ReplayRequest, reason: str) -> ReconstructionAssessment:
    return ReconstructionAssessment(
        ReconstructionStatus.RECONCILIATION_EXCEPTION,
        request.current_quantity,
        ZERO,
        None,
        None,
        (reason,),
        False,
    )


def _input_hash(
    request: ReplayRequest,
    trades: tuple[ReplayTrade, ...],
    actions: tuple[_ActionBundle, ...],
) -> str:
    document = {
        "version": REPLAY_VERSION,
        "scope": {
            "account": request.account_id,
            "target": request.target_instrument_id,
            "lineage": request.lineage_instrument_ids,
            "start": request.start_at.isoformat(),
            "cutoff": request.cutoff_at.isoformat(),
            "current_quantity": str(request.current_quantity),
            "coverage": request.corporate_action_coverage.value,
            "coverage_ref": request.coverage_quality_result_id,
            "gaps": request.source_gap_reasons,
        },
        "trades": [
            (
                item.trade_event_id,
                item.instrument_id,
                item.side,
                item.executed_at.isoformat(),
                item.execution_sequence,
                str(item.quantity),
                str(item.price),
                item.currency,
            )
            for item in trades
        ],
        "actions": [
            (
                item.revision_id,
                item.input_instrument_id,
                item.output_instrument_id,
                item.effective_at.isoformat(),
                item.knowledge_at.isoformat(),
                str(item.quantity_factor),
                str(item.price_factor),
            )
            for item in actions
        ],
    }
    return hashlib.sha256(
        json.dumps(document, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def replay_position(
    request: ReplayRequest,
    trades: Iterable[ReplayTrade],
    corporate_action_effects: Iterable[ReplayCorporateActionEffect] = (),
) -> PositionReplayPlan:
    """Build a deterministic candidate reconstruction without persisting it."""

    canonical_trades = _validate_trades(request, trades)
    actions = _bundle_actions(request, corporate_action_effects)
    partition_key = reconstruction_partition_key(
        request.account_id,
        request.target_instrument_id,
        request.start_at,
        request.cutoff_at,
    )
    replay_hash = _input_hash(request, canonical_trades, actions)
    action_count = len(actions)

    ambiguous = _ambiguous_order(canonical_trades, actions)
    preliminary = assess_reconstruction(
        current_quantity=request.current_quantity,
        replayed_quantity=request.current_quantity,
        corporate_action_coverage=request.corporate_action_coverage,
        source_gap_reasons=request.source_gap_reasons,
        ambiguous_event_order=ambiguous,
    )
    if not preliminary.eligible_for_reconciled_projection:
        return _blocked_plan(
            request, partition_key, replay_hash, preliminary, len(canonical_trades), action_count
        )

    ordered_events = _events(canonical_trades, actions)
    try:
        opening_fraction, opening_instrument = _reverse_opening_requirement(request, ordered_events)
        opening_quantity = _to_decimal(opening_fraction, "inferred opening quantity")
    except ReplayContractError as exc:
        return _blocked_plan(
            request,
            partition_key,
            replay_hash,
            _exception_assessment(request, str(exc)),
            len(canonical_trades),
            action_count,
        )

    episodes: list[_MutableEpisode] = []
    lots: list[_MutableLot] = []
    allocations: list[ReplayAllocationCandidate] = []
    active: _MutableEpisode | None = None

    def open_episode(
        instrument_id: str,
        opened_at: datetime,
        seed_ref: str,
    ) -> _MutableEpisode:
        episode_id = _hash(f"position-episode|{partition_key}|{seed_ref}")
        episode = _MutableEpisode(
            episode_id,
            request.account_id,
            instrument_id,
            instrument_id,
            opened_at,
        )
        episodes.append(episode)
        return episode

    if opening_fraction > 0:
        active = open_episode(opening_instrument, request.start_at, "inferred-opening")
        lots.append(
            _MutableLot(
                _hash(f"purchase-lot|{partition_key}|inferred-opening"),
                active.episode_id,
                request.account_id,
                opening_instrument,
                opening_instrument,
                None,
                request.start_at,
                EvidenceProvenance.INFERRED_OPENING,
                opening_fraction,
                opening_fraction,
                None,
                "UNKNOWN",
                request.start_at,
                "inferred_opening",
                partition_key,
            )
        )

    blocker: str | None = None
    for kind, event in ordered_events:
        if kind == "trade":
            trade = event
            assert isinstance(trade, ReplayTrade)
            if trade.side == "buy":
                if active is None:
                    active = open_episode(trade.instrument_id, trade.executed_at, trade.trade_event_id)
                if active.instrument_id != trade.instrument_id:
                    blocker = "buy instrument does not match the open episode"
                    break
                quantity = _to_fraction(trade.quantity)
                lots.append(
                    _MutableLot(
                        _hash(f"purchase-lot|{trade.trade_event_id}"),
                        active.episode_id,
                        request.account_id,
                        trade.instrument_id,
                        trade.instrument_id,
                        trade.trade_event_id,
                        trade.executed_at,
                        EvidenceProvenance.ACTUAL,
                        quantity,
                        quantity,
                        trade.price,
                        trade.currency,
                        trade.executed_at,
                        "buy_trade",
                        trade.trade_event_id,
                    )
                )
            else:
                if active is None or active.instrument_id != trade.instrument_id:
                    blocker = "sell has no matching open position episode"
                    break
                candidates = [
                    OpenLot(
                        item.lot_id,
                        item.account_id,
                        item.instrument_id,
                        item.episode_id,
                        item.opened_at,
                        _to_decimal(item.remaining_quantity, "open lot quantity"),
                    )
                    for item in lots
                    if item.episode_id == active.episode_id and item.remaining_quantity > 0
                ]
                allocation = plan_sell_allocation(
                    SellAllocationRequest(
                        trade.trade_event_id,
                        request.account_id,
                        trade.instrument_id,
                        active.episode_id,
                        trade.quantity,
                    ),
                    candidates,
                )
                if allocation.status is not AllocationStatus.COMPLETE:
                    blocker = "insufficient_open_lot_quantity"
                    break
                allocation_id = _hash(f"sell-allocation|{trade.trade_event_id}")
                by_id = {item.lot_id: item for item in lots}
                for item in allocation.slices:
                    lot = by_id[item.lot_id]
                    lot.remaining_quantity -= _to_fraction(item.allocated_quantity)
                    lot.state_effective_at = trade.executed_at
                    lot.cause_type = "sell_allocation"
                    lot.cause_ref = allocation_id
                allocations.append(
                    ReplayAllocationCandidate(
                        allocation_id,
                        trade.trade_event_id,
                        active.episode_id,
                        trade.instrument_id,
                        allocation,
                    )
                )
                if not any(
                    item.remaining_quantity > 0 for item in lots if item.episode_id == active.episode_id
                ):
                    active.closed_at = trade.executed_at
                    active = None
        else:
            action = event
            assert isinstance(action, _ActionBundle)
            if active is None:
                continue
            if active.instrument_id != action.input_instrument_id:
                blocker = "corporate-action input does not match the open episode"
                break
            for lot in lots:
                if lot.episode_id != active.episode_id or lot.remaining_quantity == 0:
                    continue
                lot.effective_quantity *= action.quantity_factor
                lot.remaining_quantity *= action.quantity_factor
                if lot.effective_unit_cost is not None:
                    lot.effective_unit_cost *= action.price_factor
                if action.output_instrument_id:
                    lot.instrument_id = action.output_instrument_id
                lot.state_effective_at = action.effective_at
                lot.cause_type = "corporate_action"
                lot.cause_ref = action.revision_id
            if action.output_instrument_id:
                active.instrument_id = action.output_instrument_id

    if blocker:
        return _blocked_plan(
            request,
            partition_key,
            replay_hash,
            _exception_assessment(request, blocker),
            len(canonical_trades),
            action_count,
        )

    current_fraction = sum((item.remaining_quantity for item in lots), Fraction(0))
    try:
        current = _to_decimal(current_fraction, "replayed current quantity")
    except ReplayContractError as exc:
        return _blocked_plan(
            request,
            partition_key,
            replay_hash,
            _exception_assessment(request, str(exc)),
            len(canonical_trades),
            action_count,
        )
    if current != request.current_quantity:
        return _blocked_plan(
            request,
            partition_key,
            replay_hash,
            _exception_assessment(request, "replayed lot quantity does not match current position"),
            len(canonical_trades),
            action_count,
        )
    if current > ZERO and (active is None or active.instrument_id != request.target_instrument_id):
        return _blocked_plan(
            request,
            partition_key,
            replay_hash,
            _exception_assessment(request, "replayed instrument does not match current position"),
            len(canonical_trades),
            action_count,
        )

    actual_remaining = sum(
        (
            item.remaining_quantity
            for item in lots
            if item.evidence_provenance is EvidenceProvenance.ACTUAL
        ),
        Fraction(0),
    )
    status = (
        ReconstructionStatus.INFERRED_OPENING
        if opening_fraction > 0
        else ReconstructionStatus.RECONSTRUCTED
    )
    assessment = ReconstructionAssessment(
        status,
        request.current_quantity,
        _to_decimal(actual_remaining, "actual replayed quantity"),
        opening_quantity if opening_fraction > 0 else None,
        EvidenceProvenance.INFERRED_OPENING
        if opening_fraction > 0
        else EvidenceProvenance.ACTUAL,
        (),
        True,
    )
    immutable_lots = tuple(
        ReplayLot(
            item.lot_id,
            item.episode_id,
            item.account_id,
            item.opening_instrument_id,
            item.instrument_id,
            item.opening_trade_event_id,
            item.opened_at,
            item.evidence_provenance,
            _to_decimal(item.effective_quantity, "effective lot quantity"),
            _to_decimal(item.remaining_quantity, "remaining lot quantity"),
            item.effective_unit_cost,
            item.currency,
            item.state_effective_at,
            item.cause_type,
            item.cause_ref,
        )
        for item in lots
    )
    immutable_episodes = tuple(
        ReplayEpisode(
            item.episode_id,
            item.account_id,
            item.opening_instrument_id,
            item.instrument_id,
            item.opened_at,
            item.closed_at,
            sum(
                (
                    lot.remaining_quantity
                    for lot in immutable_lots
                    if lot.episode_id == item.episode_id
                ),
                ZERO,
            ),
            ReconstructionStatus.INFERRED_OPENING
            if any(
                lot.episode_id == item.episode_id
                and lot.evidence_provenance is EvidenceProvenance.INFERRED_OPENING
                for lot in immutable_lots
            )
            else ReconstructionStatus.RECONSTRUCTED,
        )
        for item in episodes
    )
    projection_hash = _projection_hash(
        replay_hash=replay_hash,
        assessment=assessment,
        episodes=immutable_episodes,
        lots=immutable_lots,
        allocations=tuple(allocations),
    )
    return PositionReplayPlan(
        partition_key,
        replay_hash,
        projection_hash,
        assessment,
        request.coverage_quality_result_id,
        immutable_episodes,
        immutable_lots,
        tuple(allocations),
        len(canonical_trades),
        action_count,
    )
