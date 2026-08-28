from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from kis_portfolio.modules.portfolio.reconstruction import (
    CorporateActionCoverage,
    EvidenceProvenance,
    ReconstructionStatus,
)
from kis_portfolio.services.position_replay import (
    ReplayContractError,
    ReplayCorporateActionEffect,
    ReplayRequest,
    ReplayTrade,
    replay_position,
)


START = datetime(2023, 1, 1, tzinfo=UTC)
CUTOFF = datetime(2026, 1, 1, tzinfo=UTC)


def _request(
    quantity: str,
    *,
    target: str = "KRX:005930",
    lineage: tuple[str, ...] = ("KRX:005930",),
    coverage: CorporateActionCoverage = CorporateActionCoverage.PASS,
    gaps: tuple[str, ...] = (),
) -> ReplayRequest:
    return ReplayRequest(
        account_id="account-ria",
        target_instrument_id=target,
        lineage_instrument_ids=lineage,
        start_at=START,
        cutoff_at=CUTOFF,
        current_quantity=Decimal(quantity),
        corporate_action_coverage=coverage,
        coverage_quality_result_id="quality-actions-20260101",
        source_gap_reasons=gaps,
    )


def _trade(
    event_id: str,
    day: int,
    sequence: str,
    side: str,
    quantity: str,
    price: str,
    *,
    instrument: str = "KRX:005930",
) -> ReplayTrade:
    return ReplayTrade(
        trade_event_id=event_id,
        account_id="account-ria",
        instrument_id=instrument,
        side=side,
        executed_at=START + timedelta(days=day),
        execution_sequence=sequence,
        quantity=Decimal(quantity),
        price=Decimal(price),
        currency="KRW",
    )


def _effect(
    revision_id: str,
    effect_type: str,
    day: int,
    *,
    input_instrument: str = "KRX:005930",
    output_instrument: str | None = None,
    numerator: str | None = None,
    denominator: str | None = None,
) -> ReplayCorporateActionEffect:
    effective_at = START + timedelta(days=day)
    return ReplayCorporateActionEffect(
        corporate_action_revision_id=revision_id,
        effect_type=effect_type,
        input_instrument_id=input_instrument,
        output_instrument_id=output_instrument,
        factor_numerator=Decimal(numerator) if numerator is not None else None,
        factor_denominator=Decimal(denominator) if denominator is not None else None,
        effective_at=effective_at,
        knowledge_at=effective_at + timedelta(hours=1),
    )


def test_replay_is_deterministic_and_allocates_fifo() -> None:
    trades = (
        _trade("buy-a", 1, "1", "buy", "5", "100"),
        _trade("buy-b", 2, "1", "buy", "4", "110"),
        _trade("sell-a", 3, "1", "sell", "6", "120"),
    )

    first = replay_position(_request("3"), trades)
    second = replay_position(_request("3"), reversed(trades))

    assert first == second
    assert first.assessment.status is ReconstructionStatus.RECONSTRUCTED
    assert first.side_effects == "none"
    assert len(first.episodes) == 1
    assert [lot.remaining_quantity for lot in first.lots] == [Decimal("0"), Decimal("3")]
    assert [item.allocated_quantity for item in first.allocations[0].plan.slices] == [
        Decimal("5"),
        Decimal("1"),
    ]


def test_inferred_opening_closes_and_later_buy_starts_actual_episode() -> None:
    plan = replay_position(
        _request("5"),
        (
            _trade("sell-old", 1, "1", "sell", "10", "90"),
            _trade("buy-new", 2, "1", "buy", "5", "100"),
        ),
    )

    assert plan.assessment.status is ReconstructionStatus.INFERRED_OPENING
    assert plan.assessment.inferred_opening_quantity == Decimal("10")
    assert len(plan.episodes) == 2
    assert plan.episodes[0].closed_at == START + timedelta(days=1)
    assert plan.episodes[0].current_quantity == Decimal("0")
    assert plan.episodes[0].reconstruction_status is ReconstructionStatus.INFERRED_OPENING
    assert plan.episodes[1].closed_at is None
    assert plan.episodes[1].current_quantity == Decimal("5")
    assert plan.episodes[1].reconstruction_status is ReconstructionStatus.RECONSTRUCTED
    assert plan.lots[0].evidence_provenance is EvidenceProvenance.INFERRED_OPENING
    assert plan.lots[0].effective_unit_cost is None
    assert plan.lots[0].currency == "UNKNOWN"


def test_inferred_opening_is_reverse_adjusted_across_split() -> None:
    effects = (
        _effect("split-1", "quantity_multiplier", 2, numerator="2", denominator="1"),
        _effect("split-1", "price_multiplier", 2, numerator="1", denominator="2"),
    )

    plan = replay_position(
        _request("5"),
        (_trade("sell-after-split", 3, "1", "sell", "1", "55"),),
        effects,
    )

    assert plan.assessment.inferred_opening_quantity == Decimal("3")
    assert plan.lots[0].effective_quantity == Decimal("6")
    assert plan.lots[0].remaining_quantity == Decimal("5")
    assert plan.lots[0].effective_unit_cost is None


def test_split_adjusts_actual_lot_quantity_and_unit_cost() -> None:
    effects = (
        _effect("split-1", "quantity_multiplier", 2, numerator="2", denominator="1"),
        _effect("split-1", "price_multiplier", 2, numerator="1", denominator="2"),
    )

    plan = replay_position(
        _request("5"),
        (
            _trade("buy-before-split", 1, "1", "buy", "3", "100"),
            _trade("sell-after-split", 3, "1", "sell", "1", "55"),
        ),
        effects,
    )

    assert plan.assessment.status is ReconstructionStatus.RECONSTRUCTED
    assert plan.lots[0].effective_quantity == Decimal("6")
    assert plan.lots[0].remaining_quantity == Decimal("5")
    assert plan.lots[0].effective_unit_cost == Decimal("50")


def test_governed_successor_carries_open_episode_and_lot() -> None:
    old = "KRX:OLD"
    new = "KRX:NEW"
    effects = (
        _effect(
            "merger-1",
            "instrument_successor",
            2,
            input_instrument=old,
            output_instrument=new,
        ),
    )
    plan = replay_position(
        _request("3", target=new, lineage=(old, new)),
        (_trade("buy-old", 1, "1", "buy", "3", "100", instrument=old),),
        effects,
    )

    assert plan.assessment.status is ReconstructionStatus.RECONSTRUCTED
    assert plan.episodes[0].opening_instrument_id == old
    assert plan.episodes[0].instrument_id == new
    assert plan.lots[0].opening_instrument_id == old
    assert plan.lots[0].instrument_id == new


@pytest.mark.parametrize(
    ("coverage", "gaps", "expected_status", "expected_blocker"),
    [
        (
            CorporateActionCoverage.NOT_ASSESSED,
            (),
            ReconstructionStatus.NOT_ASSESSED,
            "corporate_action_coverage_not_assessed",
        ),
        (
            CorporateActionCoverage.PASS,
            ("broker_history_gap",),
            ReconstructionStatus.PROVISIONAL,
            "broker_history_gap",
        ),
    ],
)
def test_incomplete_evidence_fails_closed_without_candidate_facts(
    coverage: CorporateActionCoverage,
    gaps: tuple[str, ...],
    expected_status: ReconstructionStatus,
    expected_blocker: str,
) -> None:
    plan = replay_position(_request("5", coverage=coverage, gaps=gaps), ())

    assert plan.assessment.status is expected_status
    assert expected_blocker in plan.assessment.blockers
    assert plan.episodes == ()
    assert plan.lots == ()
    assert plan.allocations == ()


def test_same_time_trade_and_action_is_an_ambiguous_order_exception() -> None:
    action = _effect("split-1", "quantity_multiplier", 1, numerator="2", denominator="1")
    plan = replay_position(
        _request("10"),
        (_trade("buy-a", 1, "1", "buy", "5", "100"),),
        (action,),
    )

    assert plan.assessment.status is ReconstructionStatus.RECONCILIATION_EXCEPTION
    assert plan.assessment.blockers == ("ambiguous_event_order",)
    assert plan.episodes == ()


def test_negative_reverse_opening_requirement_fails_closed() -> None:
    plan = replay_position(
        _request("5"),
        (_trade("buy-too-many", 1, "1", "buy", "10", "100"),),
    )

    assert plan.assessment.status is ReconstructionStatus.RECONCILIATION_EXCEPTION
    assert "negative opening requirement" in plan.assessment.blockers[0]
    assert plan.lots == ()


def test_future_known_corporate_action_is_rejected_at_contract_boundary() -> None:
    action = ReplayCorporateActionEffect(
        corporate_action_revision_id="future-split",
        effect_type="quantity_multiplier",
        input_instrument_id="KRX:005930",
        output_instrument_id=None,
        factor_numerator=Decimal("2"),
        factor_denominator=Decimal("1"),
        effective_at=START + timedelta(days=2),
        knowledge_at=CUTOFF + timedelta(days=1),
    )

    with pytest.raises(ReplayContractError, match="future-known"):
        replay_position(_request("0"), (), (action,))
